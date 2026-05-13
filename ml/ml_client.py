"""
ml_client.py  (place this in backend/)
───────────────────────────────────────
Thin async client so main.py can call the ML service when a stop's
arrival time is requested.

Usage in main.py:
    from ml_client import predict_arrivals_for_trip

    predictions = await predict_arrivals_for_trip(
        trip_id="19343020",
        rt_ping=latest_real_time_row,
        upcoming_stops=stop_time_rows,
        db=db,
    )
"""

import os
from datetime import datetime, timezone
from typing import Optional

import httpx
from sqlalchemy.orm import Session

from models import RealTime, StopTime, Stop, Trip

ML_SERVICE_URL = os.getenv("ML_SERVICE_URL", "http://localhost:8090")


async def predict_arrivals_for_trip(
    trip_id: str,
    rt_ping: RealTime,
    upcoming_stops: list[StopTime],
    db: Session,
    max_stops: int = 10,
) -> list[dict]:
    """
    Given the latest real_time ping for a trip and the upcoming stop_times,
    calls the ML service and returns enriched stop dicts with predicted arrivals.

    Returns list of:
      {
        stop_id, stop_name, stop_lat, stop_lon,
        scheduled_arrival, predicted_arrival,
        predicted_delay_min, confidence_band_min
      }
    """
    if not rt_ping or not upcoming_stops:
        return []

    observed_at = rt_ping.recorded_timestamp or rt_ping.time or datetime.now(timezone.utc)
    if isinstance(observed_at, str):
        observed_at = datetime.fromisoformat(observed_at)

    trip: Optional[Trip] = db.query(Trip).filter(Trip.trip_id == trip_id).first()
    if not trip:
        return []

    day_of_week = observed_at.weekday()

    stop_requests = []
    for i, st in enumerate(upcoming_stops[:max_stops]):
        stop: Optional[Stop] = db.query(Stop).filter(Stop.stop_id == st.stop_id).first()
        if not stop:
            continue

        stop_requests.append({
            "observed_at": observed_at.isoformat(),
            "bus_lat": float(rt_ping.latitude),
            "bus_lon": float(rt_ping.longitude),
            "speed_kmh": float(rt_ping.speed) if rt_ping.speed else None,
            "current_delay_min": float(rt_ping.delay_min) if rt_ping.delay_min else 0.0,
            "target_stop_lat": float(stop.stop_lat),
            "target_stop_lon": float(stop.stop_lon),
            "scheduled_arrival": st.arrival_time,
            "stop_sequence": st.stop_sequence,
            "stops_remaining": i + 1,
            "route_id": trip.route_id,
            "direction_id": trip.direction_id or 0,
            "day_of_week": day_of_week,
            # stop metadata for the response
            "_stop_id": stop.stop_id,
            "_stop_name": stop.name,
        })

    if not stop_requests:
        return []

    # Strip private keys before sending
    payload_stops = [
        {k: v for k, v in s.items() if not k.startswith("_")}
        for s in stop_requests
    ]

    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.post(
            f"{ML_SERVICE_URL}/predict/batch",
            json={"stops": payload_stops},
        )
        resp.raise_for_status()
        preds = resp.json()["predictions"]

    results = []
    for meta, pred in zip(stop_requests, preds):
        results.append({
            "stop_id": meta["_stop_id"],
            "stop_name": meta["_stop_name"],
            "stop_lat": meta["target_stop_lat"],
            "stop_lon": meta["target_stop_lon"],
            "scheduled_arrival": pred["scheduled_arrival"],
            "predicted_arrival": pred["predicted_arrival"],
            "predicted_delay_min": pred["predicted_delay_min"],
            "confidence_band_min": pred["confidence_band_min"],
        })

    return results
