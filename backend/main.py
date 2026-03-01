from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import List, Optional

from database import get_db, init_db
from models import Stop, Route, Trip, StopTime, Calendar
from schemas import StopResponse, RouteResponse, TripResponse, StopTimeResponse, CalendarResponse
from gtfs_processor import GTFSProcessor
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

gtfs_processor = GTFSProcessor()


@app.on_event("startup")
async def startup_event():
    """Create tables on startup (does not load GTFS data automatically)."""
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
    rows = (
        db.query(StopTime)
        .filter(StopTime.stop_id == stop_id)
        .limit(limit)
        .all()
    )
    return rows


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
async def get_route_stops(route_id: str, db: Session = Depends(get_db)):
    """Return ordered stops (with coordinates) for the first available trip on this route."""
    route = db.query(Route).filter(Route.route_id == route_id).first()
    if not route:
        raise HTTPException(status_code=404, detail="Route not found")

    trip = db.query(Trip).filter(Trip.route_id == route_id).first()
    if not trip:
        raise HTTPException(status_code=404, detail="No trips found for route")

    stop_times = (
        db.query(StopTime)
        .filter(StopTime.trip_id == trip.trip_id)
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
        if stop and stop.stop_lat and stop.stop_lon:
            result.append({
                "stop_id": stop.stop_id,
                "name": stop.name,
                "stop_lat": stop.stop_lat,
                "stop_lon": stop.stop_lon,
                "stop_sequence": st.stop_sequence,
                "arrival_time": st.arrival_time,
                "departure_time": st.departure_time,
            })

    return {
        "route_id": route.route_id,
        "name": route.name,
        "route_color": route.route_color,
        "trip_id": trip.trip_id,
        "trip_headsign": trip.trip_headsign,
        "stops": result,
    }


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
# Admin
# ---------------------------------------------------------------------------

@app.post("/api/admin/reload-gtfs")
async def reload_gtfs(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Trigger a fresh download and import of the GTFS zip in the background."""
    async def _reload():
        await gtfs_processor.load_static_gtfs(db)

    background_tasks.add_task(_reload)
    return {"message": "GTFS reload started in the background"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
