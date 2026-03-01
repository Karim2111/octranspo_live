"""
print_route.py
--------------
Usage:
    python print_route.py <route_id>

Example:
    python print_route.py 10
"""

import sys
import logging

# Must suppress logging BEFORE importing database/models so the engine
# echo never fires.
logging.disable(logging.INFO)

from datetime import datetime
from sqlalchemy import text
from database import SessionLocal, engine
from models import Route, Trip, StopTime, Stop

# Also disable the SQLAlchemy engine echo at runtime
engine.echo = False


def gtfs_time_to_seconds(t: str) -> int:
    """Convert a GTFS HH:MM:SS string (may exceed 24:00:00) to total seconds since midnight."""
    h, m, s = map(int, t.strip().split(":"))
    return h * 3600 + m * 60 + s


def seconds_to_hhmm(secs: int) -> str:
    """Format total seconds since midnight as HH:MM (handles >24h GTFS times)."""
    h = secs // 3600
    m = (secs % 3600) // 60
    return f"{h:02d}:{m:02d}"


def now_seconds() -> int:
    now = datetime.now()
    return now.hour * 3600 + now.minute * 60 + now.second


def find_active_trip(db, route_id: str):
    """
    Find the best trip for the current time using a single SQL query.

    Strategy: for every trip on the route, get the departure_time of its
    first stop (min stop_sequence).  Pick the trip whose first departure is
    closest to now — preferring one that has already started over one that
    hasn't yet.
    """
    # One query: join trips → stop_times, keep only the first stop per trip
    rows = db.execute(
        text("""
            SELECT t.trip_id,
                   st.departure_time AS first_departure
            FROM trips t
            JOIN stop_times st ON st.trip_id = t.trip_id
            WHERE t.route_id = :route_id
              AND st.stop_sequence = (
                  SELECT MIN(s2.stop_sequence)
                  FROM stop_times s2
                  WHERE s2.trip_id = t.trip_id
              )
              AND st.departure_time IS NOT NULL
        """),
        {"route_id": route_id},
    ).fetchall()

    if not rows:
        return None, None

    current_secs = now_seconds()
    best_trip_id = None
    best_diff = None

    for trip_id, dep_time in rows:
        try:
            trip_start = gtfs_time_to_seconds(dep_time)
        except Exception:
            continue

        diff = trip_start - current_secs  # negative = already started

        if best_diff is None:
            best_trip_id, best_diff = trip_id, diff
        else:
            # Prefer already-started over upcoming
            if best_diff > 0 and diff <= 0:
                best_trip_id, best_diff = trip_id, diff
            elif best_diff <= 0 and diff > 0:
                pass
            elif abs(diff) < abs(best_diff):
                best_trip_id, best_diff = trip_id, diff

    if best_trip_id is None:
        return None, None

    trip = db.query(Trip).filter(Trip.trip_id == best_trip_id).first()
    return trip, best_diff


def print_trip(db, trip: Trip, offset_secs: int):
    route = db.query(Route).filter(Route.route_id == trip.route_id).first()

    print("=" * 66)
    print(f"Route   : {route.route_id} — {route.name}" if route else f"Route   : {trip.route_id}")
    print(f"Trip    : {trip.trip_id}")
    print(f"Towards : {trip.trip_headsign or 'N/A'}")

    mins = abs(offset_secs) // 60
    if offset_secs <= 0:
        status = f"started {mins} min ago"
    else:
        status = f"starts in {mins} min"
    print(f"Status  : {status}")
    print(f"Time    : {datetime.now().strftime('%H:%M:%S')}")
    print("=" * 66)
    print(f"{'SEQ':>4}  {'STOP':<42}  {'ARRIVE':>6}  {'DEPART':>6}")
    print("-" * 66)

    # Load all stop_times for this trip in one query
    stop_times = (
        db.query(StopTime)
        .filter(StopTime.trip_id == trip.trip_id)
        .order_by(StopTime.stop_sequence)
        .all()
    )

    # Load all referenced stops in one query
    stop_ids = [st.stop_id for st in stop_times if st.stop_id]
    stops_by_id = {
        s.stop_id: s
        for s in db.query(Stop).filter(Stop.stop_id.in_(stop_ids)).all()
    }

    current_secs = now_seconds()

    for st in stop_times:
        stop = stops_by_id.get(st.stop_id)
        stop_name = (stop.name if stop else st.stop_id) or st.stop_id

        arr = seconds_to_hhmm(gtfs_time_to_seconds(st.arrival_time)) if st.arrival_time else "     "
        dep = seconds_to_hhmm(gtfs_time_to_seconds(st.departure_time)) if st.departure_time else "     "

        marker = ""
        if st.arrival_time:
            arr_secs = gtfs_time_to_seconds(st.arrival_time)
            marker = " ◄ NOW" if abs(arr_secs - current_secs) < 120 else ""

        print(f"{st.stop_sequence:>4}  {stop_name:<42}  {arr:>6}  {dep:>6}{marker}")

    print("=" * 66)


def main():
    route_id = sys.argv[1] if len(sys.argv) > 1 else None
    if not route_id:
        print("Usage: python print_route.py <route_id>")
        print("Example: python print_route.py 10")
        sys.exit(1)

    db = SessionLocal()
    try:
        route = db.query(Route).filter(Route.route_id == route_id).first()
        if not route:
            route = db.query(Route).filter(Route.route_id.ilike(f"%{route_id}%")).first()
            if not route:
                print(f"No route found matching '{route_id}'.")
                sys.exit(1)
            route_id = route.route_id
            print(f"(Using closest match: {route_id})")

        trip, offset = find_active_trip(db, route_id)
        if not trip:
            print(f"No trips with stop times found for route {route_id}.")
            sys.exit(1)

        print_trip(db, trip, offset)
    finally:
        db.close()


if __name__ == "__main__":
    main()
