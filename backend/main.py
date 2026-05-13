from datetime import date, datetime
from typing import List, Optional

import httpx
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from db.database import get_db, init_db
from db.models import Stop, Route, Trip, StopTime, Calendar, Shape
from schemas import StopResponse, RouteResponse, TripResponse, StopTimeResponse, CalendarResponse, ShapePointResponse
from config import settings

app = FastAPI(title="OC Transpo Live API", version="1.0.0")

# CORS middleware for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

WEEKDAY_TO_FIELD = {
    0: "monday",
    1: "tuesday",
    2: "wednesday",
    3: "thursday",
    4: "friday",
    5: "saturday",
    6: "sunday",
}


def _gtfs_time_to_seconds(value: Optional[str]) -> Optional[int]:
    if not value:
        return None
    try:
        h, m, s = map(int, value.strip().split(":"))
    except (ValueError, AttributeError):
        return None
    return h * 3600 + m * 60 + s


def _seconds_since_midnight() -> int:
    now = datetime.now()
    return now.hour * 3600 + now.minute * 60 + now.second


def _next_occurrence_delta(gtfs_seconds: Optional[int], now_seconds: int) -> int:
    if gtfs_seconds is None:
        return 10**9
    delta = gtfs_seconds - now_seconds
    return delta if delta >= 0 else delta + 24 * 3600


@app.on_event("startup")
async def startup_event():
    """Create missing database tables on startup."""
    init_db()


@app.get("/")
async def root():
    return {"message": "OC Transpo Live API", "status": "running"}


# ---------------------------------------------------------------------------
# Stops
# ---------------------------------------------------------------------------

@app.get("/api/stops", response_model=List[StopResponse])
async def get_stops(
    search: Optional[str] = None,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    radius: Optional[float] = 500,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    """List stops, optionally filtered by name search or bounding radius."""
    query = db.query(Stop)
    if search:
        query = query.filter(Stop.name.ilike(f"%{search}%"))
    if lat is not None and lon is not None:
        # Simple Euclidean distance filter (use PostGIS for production)
        deg = radius / 111_000
        query = query.filter(
            ((Stop.stop_lat - lat) ** 2 + (Stop.stop_lon - lon) ** 2) <= deg ** 2
        )
    return query.limit(limit).all()


@app.get("/api/stops/{stop_id}", response_model=StopResponse)
async def get_stop(stop_id: str, db: Session = Depends(get_db)):
    stop = db.query(Stop).filter(Stop.stop_id == stop_id).first()
    if not stop:
        raise HTTPException(status_code=404, detail="Stop not found")
    return stop


@app.get("/api/stops/{stop_id}/stop_times", response_model=List[StopTimeResponse])
async def get_stop_times_for_stop(
    stop_id: str,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    """Return upcoming stop_times entries for a given stop."""
    now_seconds = _seconds_since_midnight()
    scan_limit = min(max(limit * 6, 200), 2500)
    rows = (
        db.query(StopTime)
        .filter(StopTime.stop_id == stop_id)
        .limit(scan_limit)
        .all()
    )

    rows_sorted = sorted(
        rows,
        key=lambda st: (
            _next_occurrence_delta(
                _gtfs_time_to_seconds(st.departure_time or st.arrival_time),
                now_seconds,
            ),
            _gtfs_time_to_seconds(st.departure_time or st.arrival_time) or 10**9,
        ),
    )
    return rows_sorted[:limit]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/api/routes", response_model=List[RouteResponse])
async def get_routes(db: Session = Depends(get_db)):
    return db.query(Route).order_by(Route.route_sort_order).all()


@app.get("/api/routes/{route_id}", response_model=RouteResponse)
async def get_route(route_id: str, db: Session = Depends(get_db)):
    route = db.query(Route).filter(Route.route_id == route_id).first()
    if not route:
        raise HTTPException(status_code=404, detail="Route not found")
    return route


@app.get("/api/routes/{route_id}/trips", response_model=List[TripResponse])
async def get_trips_for_route(
    route_id: str,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    trips = db.query(Trip).filter(Trip.route_id == route_id).limit(limit).all()
    return trips


@app.get("/api/routes/{route_id}/stops")
async def get_route_stops(
    route_id: str,
    direction_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """Return ordered stops for the nearest scheduled trip on this route."""
    route = db.query(Route).filter(Route.route_id == route_id).first()
    if not route:
        raise HTTPException(status_code=404, detail="Route not found")

    today = date.today()
    weekday_field = WEEKDAY_TO_FIELD[today.weekday()]

    trip_query = (
        db.query(Trip)
        .outerjoin(Calendar, Trip.service_id == Calendar.service_id)
        .filter(Trip.route_id == route_id)
        .filter(
            or_(
                Calendar.service_id.is_(None),
                and_(
                    Calendar.start_date <= today,
                    Calendar.end_date >= today,
                    getattr(Calendar, weekday_field).is_(True),
                ),
            )
        )
    )

    if direction_id is not None:
        trip_query = trip_query.filter(Trip.direction_id == direction_id)

    trips = trip_query.limit(2000).all()
    if not trips:
        raise HTTPException(status_code=404, detail="No trips found for route")

    trip_ids = [t.trip_id for t in trips]
    first_stops_subq = (
        db.query(
            StopTime.trip_id.label("trip_id"),
            func.min(StopTime.stop_sequence).label("min_seq"),
        )
        .filter(StopTime.trip_id.in_(trip_ids))
        .group_by(StopTime.trip_id)
        .subquery()
    )
    first_departures = (
        db.query(StopTime.trip_id, StopTime.departure_time)
        .join(
            first_stops_subq,
            and_(
                StopTime.trip_id == first_stops_subq.c.trip_id,
                StopTime.stop_sequence == first_stops_subq.c.min_seq,
            ),
        )
        .all()
    )

    departure_map = {row.trip_id: row.departure_time for row in first_departures}
    now_seconds = _seconds_since_midnight()
    best_trip = min(
        trips,
        key=lambda t: (
            _next_occurrence_delta(
                _gtfs_time_to_seconds(departure_map.get(t.trip_id)),
                now_seconds,
            ),
            t.trip_id,
        ),
    )

    stop_times = (
        db.query(StopTime)
        .filter(StopTime.trip_id == best_trip.trip_id)
        .order_by(StopTime.stop_sequence)
        .all()
    )

    stop_ids = [st.stop_id for st in stop_times if st.stop_id]
    stops_by_id = {
        s.stop_id: s
        for s in db.query(Stop).filter(Stop.stop_id.in_(stop_ids)).all()
    }

    result = []
    for st in stop_times:
        stop = stops_by_id.get(st.stop_id)
        if stop and stop.stop_lat is not None and stop.stop_lon is not None:
            result.append({
                "stop_id": stop.stop_id,
                "name": stop.name,
                "stop_lat": stop.stop_lat,
                "stop_lon": stop.stop_lon,
                "stop_sequence": st.stop_sequence,
                "arrival_time": st.arrival_time,
                "departure_time": st.departure_time,
            })

    # Load shape geometry for road-following polyline
    shape = []
    if best_trip.shape_id:
        shape_rows = (
            db.query(Shape)
            .filter(Shape.shape_id == best_trip.shape_id)
            .order_by(Shape.shape_pt_sequence)
            .all()
        )
        shape = [[s.shape_pt_lat, s.shape_pt_lon] for s in shape_rows]

    return {
        "route_id": route.route_id,
        "name": route.name,
        "route_color": route.route_color,
        "trip_id": best_trip.trip_id,
        "trip_headsign": best_trip.trip_headsign,
        "direction_id": best_trip.direction_id,
        "stops": result,
        "shape": shape,
    }


# ---------------------------------------------------------------------------
# Shapes
# ---------------------------------------------------------------------------

@app.get("/api/shapes/{shape_id}", response_model=List[ShapePointResponse])
async def get_shape(shape_id: str, db: Session = Depends(get_db)):
    """Return all points for a shape, ordered by sequence."""
    points = (
        db.query(Shape)
        .filter(Shape.shape_id == shape_id)
        .order_by(Shape.shape_pt_sequence)
        .all()
    )
    if not points:
        raise HTTPException(status_code=404, detail="Shape not found")
    return points


# ---------------------------------------------------------------------------
# Trips
# ---------------------------------------------------------------------------

@app.get("/api/trips/{trip_id}", response_model=TripResponse)
async def get_trip(trip_id: str, db: Session = Depends(get_db)):
    trip = db.query(Trip).filter(Trip.trip_id == trip_id).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    return trip


@app.get("/api/trips/{trip_id}/stop_times", response_model=List[StopTimeResponse])
async def get_stop_times_for_trip(
    trip_id: str,
    db: Session = Depends(get_db),
):
    return (
        db.query(StopTime)
        .filter(StopTime.trip_id == trip_id)
        .order_by(StopTime.stop_sequence)
        .all()
    )


# ---------------------------------------------------------------------------
# Calendar
# ---------------------------------------------------------------------------

@app.get("/api/calendar", response_model=List[CalendarResponse])
async def get_calendar(db: Session = Depends(get_db)):
    return db.query(Calendar).all()


@app.get("/api/calendar/{service_id}", response_model=CalendarResponse)
async def get_service(service_id: str, db: Session = Depends(get_db)):
    cal = db.query(Calendar).filter(Calendar.service_id == service_id).first()
    if not cal:
        raise HTTPException(status_code=404, detail="Service not found")
    return cal


# ---------------------------------------------------------------------------
# Nearby routes
# ---------------------------------------------------------------------------

@app.get("/api/nearby-routes")
async def get_nearby_routes(
    lat: float,
    lon: float,
    radius: float = 800,
    limit: int = 15,
    db: Session = Depends(get_db),
):
    """
    Return routes whose stops fall within `radius` metres of (lat, lon),
    ordered by distance to the nearest stop.
    """
    from sqlalchemy import text as sqlt
    rows = db.execute(
        sqlt("""
            SELECT
                r.route_id,
                r.name,
                r.route_color,
                r.route_text_color,
                r.route_sort_order,
                MIN(SQRT(POWER(s.stop_lat - :lat, 2) + POWER(s.stop_lon - :lon, 2)) * 111000) AS nearest_m,
                (array_agg(s.name ORDER BY
                    SQRT(POWER(s.stop_lat - :lat, 2) + POWER(s.stop_lon - :lon, 2))))[1] AS nearest_stop
            FROM stops s
            JOIN stop_times st ON st.stop_id = s.stop_id
            JOIN trips t      ON t.trip_id  = st.trip_id
            JOIN routes r     ON r.route_id = t.route_id
            WHERE SQRT(POWER(s.stop_lat - :lat, 2) + POWER(s.stop_lon - :lon, 2)) * 111000 <= :radius
            GROUP BY r.route_id, r.name, r.route_color, r.route_text_color, r.route_sort_order
            ORDER BY nearest_m
            LIMIT :limit
        """),
        {"lat": lat, "lon": lon, "radius": radius, "limit": limit},
    ).fetchall()

    return [
        {
            "route_id": row.route_id,
            "name": row.name,
            "route_color": row.route_color,
            "route_text_color": row.route_text_color,
            "nearest_stop": row.nearest_stop,
            "nearest_m": round(row.nearest_m),
        }
        for row in rows
    ]


# ---------------------------------------------------------------------------
# Predictions (ML service proxy)
# ---------------------------------------------------------------------------

class PredictRequest(BaseModel):
    observed_at: Optional[datetime] = None
    bus_lat: float
    bus_lon: float
    speed_kmh: Optional[float] = None
    current_delay_min: float = 0.0
    target_stop_lat: float
    target_stop_lon: float
    scheduled_arrival: str
    stop_sequence: int
    stops_remaining: int
    route_id: str
    direction_id: int


@app.post("/api/predict")
async def predict_stop(req: PredictRequest):
    if not settings.ML_SERVICE_URL:
        raise HTTPException(status_code=503, detail="ML service not configured")

    observed_at = req.observed_at or datetime.utcnow()
    payload = req.dict()
    payload["observed_at"] = observed_at.isoformat()
    payload["day_of_week"] = observed_at.weekday()

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(f"{settings.ML_SERVICE_URL}/predict", json=payload)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"ML service error {exc.response.status_code}: {exc.response.text[:300]}",
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"ML service error: {exc}")


# ---------------------------------------------------------------------------
# GTFS-RT — live vehicle positions
# ---------------------------------------------------------------------------

@app.get("/api/debug/gtfs-rt")
async def debug_gtfs_rt():
    """Test the GTFS-RT vehicle positions connection."""
    if not settings.DEBUG:
        raise HTTPException(status_code=404, detail="Not found")

    key = (settings.GTFS_PRIMARY_KEY or "").strip()
    url = settings.GTFS_RT_VEHICLE_POSITIONS_URL
    headers = {"Ocp-Apim-Subscription-Key": key}

    result = {"url": url, "key_loaded": bool(key)}

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url, headers=headers, follow_redirects=True)
            result["status_code"] = r.status_code
            result["bytes"] = len(r.content)
            result["content_type"] = r.headers.get("content-type")
            if r.status_code != 200:
                result["response_body"] = r.text[:500]
    except Exception as exc:
        result["error"] = str(exc)

    return result


@app.get("/api/routes/{route_id}/vehicles")
async def get_route_vehicles(route_id: str, db: Session = Depends(get_db)):
    """
    Fetch live vehicle positions for a route from the OC Transpo GTFS-RT feed.
    Returns a list of vehicles with lat/lon/bearing/speed/direction_id.
    """
    from google.transit import gtfs_realtime_pb2

    key = (settings.GTFS_PRIMARY_KEY or "").strip()
    if not key:
        raise HTTPException(status_code=503, detail="GTFS_PRIMARY_KEY not configured")

    url = settings.GTFS_RT_VEHICLE_POSITIONS_URL
    headers = {"Ocp-Apim-Subscription-Key": key}

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, headers=headers, follow_redirects=True)
            resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Upstream returned {exc.response.status_code}: {exc.response.text[:300]}"
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"GTFS-RT fetch failed: {exc}")

    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(resp.content)

    # Collect matching vehicles
    raw = []
    for entity in feed.entity:
        if not entity.HasField("vehicle"):
            continue
        v = entity.vehicle
        if v.trip.route_id != route_id:
            continue
        pos = v.position
        raw.append({
            "vehicle_id": v.vehicle.id or entity.id,
            "label": v.vehicle.label or v.vehicle.id or entity.id,
            "lat": pos.latitude,
            "lon": pos.longitude,
            "bearing": pos.bearing if pos.bearing else None,
            "speed_kmh": round(pos.speed * 3.6) if pos.speed else None,
            "trip_id": v.trip.trip_id,
            "status": ["Incoming", "Stopped", "In Transit"][v.current_status] if v.current_status in (0, 1, 2) else str(v.current_status),
            "direction_id": None,
        })

    # Look up direction_id from static DB.
    # Live feed trip_ids often have a numeric suffix appended (e.g. "24805130" vs "24805"),
    # so try exact match first, then strip the last 3 digits for unmatched ones.
    trip_ids = [r["trip_id"] for r in raw]
    dir_map = {}
    if trip_ids:
        rows = db.query(Trip.trip_id, Trip.direction_id).filter(Trip.trip_id.in_(trip_ids)).all()
        dir_map = {row.trip_id: row.direction_id for row in rows}

        unmatched = [t for t in trip_ids if t not in dir_map]
        if unmatched:
            stripped = {t: t[:-3] for t in unmatched if len(t) > 3}
            fallback_rows = db.query(Trip.trip_id, Trip.direction_id).filter(
                Trip.trip_id.in_(list(stripped.values()))
            ).all()
            fallback_map = {row.trip_id: row.direction_id for row in fallback_rows}
            for orig, short in stripped.items():
                if short in fallback_map:
                    dir_map[orig] = fallback_map[short]

    for r in raw:
        r["direction_id"] = dir_map.get(r["trip_id"])

    return raw

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
