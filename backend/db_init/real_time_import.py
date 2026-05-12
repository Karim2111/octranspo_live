"""
Import location-export CSV into `real_time` table.


Run from repo root as:
    python backend/real_time_import.py


Optional overrides:
    python backend/real_time_import.py --file data/location_export_2026-03-25.csv
    python backend/real_time_import.py --url "<FULL_URL>"
    python backend/real_time_import.py --url "<FULL_URL>" \
        --start-date 2026-01-08 --end-date 2026-05-12


The script ensures tables exist (calls `init_db()`), parses rows,
assigns `stop_sequence` per `trip_id` ordered by `time` (starting at 1),
and bulk-inserts into `real_time`.
"""
import argparse
import asyncio
import csv
import io
import os
import sys
from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse


# Ensure backend modules can be imported when running from repo root.
ROOT = os.path.dirname(os.path.dirname(__file__))
if ROOT and ROOT not in sys.path:
    sys.path.insert(0, ROOT)


import httpx
import pandas as pd
from sqlalchemy import insert
from sqlalchemy.dialects.postgresql import insert as pg_insert


from db_init.database import SessionLocal, init_db
from db_init.models import RealTime


# Defaults for no-arg runs (sequential daily fetch).
DEFAULT_URL = "https://bus.ajay.app/api/locationExport?auth=FQ0Iav5l5gP8Xim2DHhqvGOQ1NOD&date=2026-03-25"
DEFAULT_START_DATE = "2026-01-08"
DEFAULT_END_DATE = "2026-01-30"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Async fetch: all URLs fetched concurrently
# ---------------------------------------------------------------------------

async def _fetch_one(client: httpx.AsyncClient, url: str) -> tuple[str, str]:
    r = await client.get(url, follow_redirects=True)
    r.raise_for_status()
    return url, r.text


async def fetch_all_async(urls: list[str], timeout: int = 30) -> list[tuple[str, str]]:
    async with httpx.AsyncClient(timeout=timeout) as client:
        tasks = [_fetch_one(client, url) for url in urls]
        return await asyncio.gather(*tasks)


def fetch_text(url: str, timeout: int = 30) -> str:
    with httpx.Client(timeout=timeout) as client:
        r = client.get(url, follow_redirects=True)
        r.raise_for_status()
        return r.text


# ---------------------------------------------------------------------------
# Parsing + import
# ---------------------------------------------------------------------------

def parse_text_to_rows(text: str) -> list[dict]:
    """
    Parse CSV text into a list of dicts ready for bulk insert.
    Uses pandas for fast CSV parsing and vectorised stop_sequence assignment.
    """
    df = pd.read_csv(
        io.StringIO(text),
        dtype=str,          # read everything as str first; cast below
        keep_default_na=False,
    )

    # Normalise column names to lowercase
    df.columns = [c.strip().lower() for c in df.columns]

    # Parse time column (handles both "time" and "Time")
    time_col = "time" if "time" in df.columns else None
    if time_col:
        df["time"] = pd.to_datetime(df[time_col], errors="coerce")
    else:
        df["time"] = pd.NaT

    # Numeric casts
    for col in ("delay_min", "latitude", "longitude", "speed"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].str.strip().replace("", float("nan")), errors="coerce")
        else:
            df[col] = float("nan")

    # Nullable string columns
    for col in ("trip_id", "recorded_timestamp", "next_stop_id"):
        if col in df.columns:
            df[col] = df[col].str.strip().replace("", None)
        else:
            df[col] = None

    # Assign stop_sequence per trip_id ordered by time (vectorised, no Python loop)
    df["stop_sequence"] = None
    mask = df["trip_id"].notna()
    if mask.any():
        df.loc[mask, "stop_sequence"] = (
            df[mask]
            .sort_values("time")
            .groupby("trip_id")
            .cumcount() + 1
        ).astype("Int64")  # nullable int so rows without trip_id stay None

    # Replace NaN with None for SQLAlchemy
    df = df.where(df.notna(), other=None)

    return df[
        ["time", "trip_id", "delay_min", "latitude", "longitude",
         "speed", "recorded_timestamp", "next_stop_id", "stop_sequence"]
    ].to_dict("records")


def import_from_text(text: str) -> int:
    """Parse text and bulk-insert into real_time table. Returns row count."""
    rows = parse_text_to_rows(text)
    if not rows:
        print("No rows to import.")
        return 0

    init_db()
    session = SessionLocal()
    try:
        # Use SQLAlchemy Core insert (10-50x faster than bulk_save_objects)
        # ON CONFLICT DO NOTHING so reruns are safe
        stmt = pg_insert(RealTime).values(rows).on_conflict_do_nothing()
        session.execute(stmt)
        session.commit()
        count = len(rows)
        print(f"Import complete. Inserted up to {count} rows into real_time table.")
        return count
    finally:
        session.close()


def import_from_texts(url_text_pairs: list[tuple[str, str]]) -> int:
    """
    Bulk-insert rows from multiple CSV texts in a single DB session.
    All texts are parsed first, then inserted together in one transaction.
    """
    all_rows: list[dict] = []
    for url, text in url_text_pairs:
        print(f"Parsing: {url}")
        all_rows.extend(parse_text_to_rows(text))

    if not all_rows:
        print("No rows to import.")
        return 0

    init_db()
    session = SessionLocal()
    try:
        stmt = pg_insert(RealTime).values(all_rows).on_conflict_do_nothing()
        session.execute(stmt)
        session.commit()
        print(f"Import complete. Inserted up to {len(all_rows)} rows into real_time table.")
        return len(all_rows)
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

            urls = [set_url_date(args.url, d) for d in date_range(start_date, end_date)]
            print(f"Fetching {len(urls)} day(s) concurrently...")

            # Fetch all days in parallel, then insert everything in one transaction
            url_text_pairs = asyncio.run(fetch_all_async(urls))
            import_from_texts(url_text_pairs)
            return

        print(f"Fetching from URL: {args.url}")
        text = fetch_text(args.url)

    else:
        path = args.file
        print(f"Reading file: {path}")
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()

    import_from_text(text)


if __name__ == "__main__":
    main()