"""
Import location-export CSV into `real_time` table.

Run from repo root as:
    python backend/real_time_import.py

Optional overrides:
    python backend/real_time_import.py --file data/location_export_2026-03-25.csv
    python backend/real_time_import.py --url "<FULL_URL>"
    python backend/real_time_import.py --url "<FULL_URL>" \
        --start-date 2026-01-08 --end-date 2026-05-12

The script clears `real_time`, ensures tables exist (calls `init_db()`),
parses rows, assigns `stop_sequence` per `trip_id` ordered by `time`
(starting at 1), and inserts each day's rows in small batches.
"""
import argparse
import csv
import io
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

# Ensure backend modules can be imported when running from repo root.
ROOT = os.path.dirname(os.path.dirname(__file__))
if ROOT and ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import httpx

from db.database import SessionLocal, init_db
from db.models import RealTime

# Defaults for no-arg runs (sequential daily fetch).
DEFAULT_URL = "https://bus.ajay.app/api/locationExport?auth=FQ0Iav5l5gP8Xim2DHhqvGOQ1NOD&date=2026-03-25"
DEFAULT_START_DATE = "2026-01-08"
DEFAULT_END_DATE = "2026-01-30"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_datetime(value: str):
    if not value:
        return None
    value = value.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value, fmt)
        except Exception:
            continue
    return None


def to_float(value: str):
    if value is None:
        return None
    value = value.strip()
    if value == "":
        return None
    try:
        return float(value)
    except Exception:
        return None


def parse_date(value: str):
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def get_url_date(url: str):
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    date_value = (query.get("date") or [None])[0]
    return parse_date(date_value) if date_value else None


def set_url_date(url: str, date_value):
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    query["date"] = [date_value.strftime("%Y-%m-%d")]
    new_query = urlencode(query, doseq=True)
    return urlunparse(parsed._replace(query=new_query))


def date_range(start, end):
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def fetch_text(url: str, timeout: int = 30) -> str:
    with httpx.Client(timeout=timeout) as client:
        r = client.get(url, follow_redirects=True)
        r.raise_for_status()
        return r.text


# ---------------------------------------------------------------------------
# Parsing + import
# ---------------------------------------------------------------------------

def clear_real_time_table():
    session = SessionLocal()
    try:
        session.query(RealTime).delete()
        session.commit()
        print("Cleared real_time table.")
    finally:
        session.close()


def parse_text_to_rows(text: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        return []

    groups = defaultdict(list)
    ungroupped = []
    parsed = []
    for r in rows:
        t = parse_datetime(r.get("time") or r.get("Time") or "")
        trip_id = (r.get("trip_id") or "").strip() or None
        delay_min = to_float(r.get("delay_min"))
        lat = to_float(r.get("latitude"))
        lon = to_float(r.get("longitude"))
        speed = to_float(r.get("speed"))
        recorded_ts = (r.get("recorded_timestamp") or "").strip() or None
        next_stop = (r.get("next_stop_id") or "").strip() or None

        item = {
            "time": t,
            "trip_id": trip_id,
            "delay_min": delay_min,
            "latitude": lat,
            "longitude": lon,
            "speed": speed,
            "recorded_timestamp": recorded_ts,
            "next_stop_id": next_stop,
        }
        parsed.append(item)
        if trip_id:
            groups[trip_id].append(item)
        else:
            ungroupped.append(item)

    for trip_id, items in groups.items():
        items.sort(key=lambda x: (x["time"] or datetime.min))
        for i, it in enumerate(items, start=1):
            it["stop_sequence"] = i

    for it in ungroupped:
        it["stop_sequence"] = None

    return parsed


def import_from_text(text: str, label: str = "", batch_size: int = 500) -> int:
    rows = parse_text_to_rows(text)
    if not rows:
        print(f"[{label}] No rows to import.")
        return 0

    session = SessionLocal()
    try:
        count = 0
        buffer = []
        for it in rows:
            buffer.append(RealTime(
                time=it["time"],
                trip_id=it["trip_id"],
                delay_min=it["delay_min"],
                latitude=it["latitude"],
                longitude=it["longitude"],
                speed=it["speed"],
                recorded_timestamp=it["recorded_timestamp"],
                next_stop_id=it["next_stop_id"],
                stop_sequence=it.get("stop_sequence"),
            ))
            if len(buffer) >= batch_size:
                session.bulk_save_objects(buffer)
                session.commit()
                count += len(buffer)
                buffer = []

        if buffer:
            session.bulk_save_objects(buffer)
            session.commit()
            count += len(buffer)

        print(f"[{label}] Inserted {count} rows.")
        return count
    finally:
        session.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser(description="Import location-export CSV into real_time table")
    p.add_argument("--file", help="Path to CSV file to import")
    p.add_argument("--url", help="URL to fetch CSV from")
    p.add_argument("--start-date", help="Start date (YYYY-MM-DD) for sequential URL fetch")
    p.add_argument("--end-date", help="End date (YYYY-MM-DD) for sequential URL fetch")
    args = p.parse_args()

    if not args.file and not args.url:
        args.url = DEFAULT_URL
        args.start_date = DEFAULT_START_DATE
        args.end_date = DEFAULT_END_DATE

    init_db()
    

    if args.url:
        start_date = parse_date(args.start_date) if args.start_date else None
        end_date = parse_date(args.end_date) if args.end_date else None
        url_date = get_url_date(args.url)

        if start_date or end_date:
            if not start_date:
                start_date = url_date
            if not end_date:
                end_date = url_date
            if not start_date or not end_date:
                print("Provide --start-date and --end-date or include date=YYYY-MM-DD in --url")
                return
            if start_date > end_date:
                print("--start-date must be <= --end-date")
                return

            total = 0
            for d in date_range(start_date, end_date):
                url = set_url_date(args.url, d)
                print(f"Fetching: {url}")
                text = fetch_text(url)
                total += import_from_text(text, label=d.isoformat())

            print(f"All done. Inserted {total} total rows.")
            return

        print(f"Fetching from URL: {args.url}")
        text = fetch_text(args.url)
        import_from_text(text, label=args.url)

    else:
        print(f"Reading file: {args.file}")
        with open(args.file, "r", encoding="utf-8") as f:
            text = f.read()
        import_from_text(text, label=args.file)


if __name__ == "__main__":
    main()