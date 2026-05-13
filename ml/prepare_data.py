"""
Build the ML training dataset without PostgreSQL.

The pipeline reads static GTFS tables from ml/extract/GTFS (folder or zip),
fetches historical bus location CSV from the API (or reads a local CSV),
writes normalized source Parquet files, then joins pings to upcoming GTFS stops
and writes the final training Parquet used by train.py.

Examples:
    python prepare_data.py --extract-only
    python prepare_data.py --training-only --limit 10000
    python prepare_data.py --gtfs extract/GTFS/GTFSExport.zip
"""

from __future__ import annotations

import argparse
import csv
import io
import os
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import httpx
import pandas as pd

from features import build_features, parse_gtfs_time


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ML_ROOT = Path(__file__).resolve().parent
DEFAULT_GTFS_PATH = ML_ROOT / "extract" / "GTFS"
DEFAULT_DATA_DIR = ML_ROOT / "data"
DEFAULT_GTFS_OUT_DIR = DEFAULT_DATA_DIR / "gtfs"
DEFAULT_RAW_OUT_PATH = DEFAULT_DATA_DIR / "realtime.parquet"
DEFAULT_TRAINING_OUT_PATH = DEFAULT_DATA_DIR / "training.parquet"
DEFAULT_URL = (
    "https://bus.ajay.app/api/locationExport"
    "?auth=FQ0Iav5l5gP8Xim2DHhqvGOQ1NOD&date=2026-03-25"
)
DEFAULT_START_DATE = "2026-01-08"
DEFAULT_END_DATE = "2026-01-30"
DAY_COLUMNS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


load_env_file(PROJECT_ROOT / ".env")
load_env_file(PROJECT_ROOT / "backend" / ".env")


def parse_datetime(value: object) -> datetime | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    parsed = pd.to_datetime(text, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.to_pydatetime()


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def to_float(value: object) -> float | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def to_int(value: object) -> int | None:
    if value is None or pd.isna(value):
        return None
    try:
        return int(float(str(value).strip()))
    except ValueError:
        return None


def bool_from_gtfs(value: object) -> bool:
    return str(value).strip().lower() in {"1", "true", "t", "yes", "y"}


def get_url_date(url: str) -> date | None:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    date_value = (query.get("date") or [None])[0]
    return parse_date(date_value) if date_value else None


def set_url_date(url: str, date_value: date) -> str:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    query["date"] = [date_value.strftime("%Y-%m-%d")]
    new_query = urlencode(query, doseq=True)
    return urlunparse(parsed._replace(query=new_query))


def date_range(start: date, end: date):
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def fetch_text(url: str, timeout: int = 30) -> str:
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.text


def read_csv_from_gtfs(gtfs_path: Path, filename: str, **kwargs) -> pd.DataFrame:
    if gtfs_path.is_file():
        with zipfile.ZipFile(gtfs_path) as zf:
            with zf.open(filename) as fh:
                return pd.read_csv(fh, dtype=str, **kwargs)

    if gtfs_path.is_dir():
        direct_file = gtfs_path / filename
        if direct_file.exists():
            return pd.read_csv(direct_file, dtype=str, **kwargs)

        zip_files = sorted(gtfs_path.glob("*.zip"))
        if zip_files:
            return read_csv_from_gtfs(zip_files[-1], filename, **kwargs)

    raise FileNotFoundError(f"Could not find {filename} in GTFS path: {gtfs_path}")


def load_gtfs(gtfs_path: Path) -> dict[str, pd.DataFrame]:
    print(f"Loading static GTFS from {gtfs_path}")

    stops = read_csv_from_gtfs(gtfs_path, "stops.txt")
    trips = read_csv_from_gtfs(gtfs_path, "trips.txt")
    stop_times = read_csv_from_gtfs(gtfs_path, "stop_times.txt")

    try:
        calendar = read_csv_from_gtfs(gtfs_path, "calendar.txt")
    except FileNotFoundError:
        calendar = pd.DataFrame(columns=["service_id", *DAY_COLUMNS])

    stops = stops[["stop_id", "stop_lat", "stop_lon"]].copy()
    stops["stop_lat"] = pd.to_numeric(stops["stop_lat"], errors="coerce")
    stops["stop_lon"] = pd.to_numeric(stops["stop_lon"], errors="coerce")

    trips = trips[["trip_id", "route_id", "service_id", "direction_id"]].copy()
    trips["direction_id"] = pd.to_numeric(trips["direction_id"], errors="coerce").fillna(0).astype(int)

    stop_times = stop_times[["trip_id", "arrival_time", "departure_time", "stop_id", "stop_sequence"]].copy()
    stop_times["stop_sequence"] = pd.to_numeric(stop_times["stop_sequence"], errors="coerce")
    stop_times = stop_times.dropna(subset=["trip_id", "stop_id", "stop_sequence"])
    stop_times["stop_sequence"] = stop_times["stop_sequence"].astype(int)

    if not calendar.empty:
        calendar = calendar[["service_id", *[c for c in DAY_COLUMNS if c in calendar.columns]]].copy()
        for day in DAY_COLUMNS:
            if day not in calendar.columns:
                calendar[day] = False
            else:
                calendar[day] = calendar[day].map(bool_from_gtfs)

    return {
        "stops": stops,
        "trips": trips,
        "stop_times": stop_times,
        "calendar": calendar,
    }


def write_gtfs_parquet(gtfs: dict[str, pd.DataFrame], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for table_name, df in gtfs.items():
        if df.empty:
            continue
        write_parquet(df, out_dir / f"{table_name}.parquet")


def load_gtfs_parquet(in_dir: Path) -> dict[str, pd.DataFrame]:
    required = ["stops", "trips", "stop_times"]
    missing = [name for name in required if not (in_dir / f"{name}.parquet").exists()]
    if missing:
        raise FileNotFoundError(
            f"Missing GTFS Parquet files in {in_dir}: "
            + ", ".join(f"{name}.parquet" for name in missing)
        )

    print(f"Loading static GTFS Parquet files from {in_dir}")
    calendar_path = in_dir / "calendar.parquet"
    calendar = pd.read_parquet(calendar_path) if calendar_path.exists() else pd.DataFrame()
    return {
        "stops": pd.read_parquet(in_dir / "stops.parquet"),
        "trips": pd.read_parquet(in_dir / "trips.parquet"),
        "stop_times": pd.read_parquet(in_dir / "stop_times.parquet"),
        "calendar": calendar,
    }


def parse_location_export(text: str) -> pd.DataFrame:
    reader = csv.DictReader(io.StringIO(text))
    parsed = []

    for row in reader:
        parsed.append(
            {
                "observed_at": parse_datetime(row.get("time") or row.get("Time")),
                "trip_id": (row.get("trip_id") or "").strip() or None,
                "delay_min": to_float(row.get("delay_min")),
                "bus_lat": to_float(row.get("latitude")),
                "bus_lon": to_float(row.get("longitude")),
                "speed_kmh": to_float(row.get("speed")),
                "recorded_timestamp": (row.get("recorded_timestamp") or "").strip() or None,
                "next_stop_id": (row.get("next_stop_id") or "").strip() or None,
                "api_stop_sequence": to_int(row.get("stop_sequence")),
            }
        )

    if not parsed:
        return pd.DataFrame()

    pings = pd.DataFrame(parsed)
    pings = pings.dropna(subset=["observed_at", "trip_id", "delay_min", "bus_lat", "bus_lon"])
    pings = pings.sort_values(["trip_id", "observed_at"]).reset_index(drop=True)
    pings["ping_id"] = range(1, len(pings) + 1)
    pings["fallback_stop_sequence"] = pings.groupby("trip_id").cumcount() + 1
    return pings


def load_realtime_from_file(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".parquet":
        df = pd.read_parquet(path)
        if "observed_at" in df.columns:
            df["observed_at"] = pd.to_datetime(df["observed_at"], errors="coerce")
        if "ping_id" not in df.columns:
            df = df.sort_values(["trip_id", "observed_at"]).reset_index(drop=True)
            df["ping_id"] = range(1, len(df) + 1)
        if "fallback_stop_sequence" not in df.columns:
            df["fallback_stop_sequence"] = df.groupby("trip_id").cumcount() + 1
        return df

    print(f"Reading location export CSV from {path}")
    return parse_location_export(path.read_text(encoding="utf-8"))


def load_realtime_from_api(url: str, start_date: date | None, end_date: date | None) -> pd.DataFrame:
    url_date = get_url_date(url)
    if start_date or end_date:
        start_date = start_date or url_date
        end_date = end_date or url_date
        if not start_date or not end_date:
            raise ValueError("Provide --start-date and --end-date or include date=YYYY-MM-DD in --url")
        if start_date > end_date:
            raise ValueError("--start-date must be <= --end-date")

        frames = []
        for day in date_range(start_date, end_date):
            day_url = set_url_date(url, day)
            print(f"Fetching location export for {day.isoformat()}")
            frames.append(parse_location_export(fetch_text(day_url)))
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    print("Fetching location export")
    return parse_location_export(fetch_text(url))


def infer_current_stop_sequence(pings: pd.DataFrame, stop_times: pd.DataFrame) -> pd.DataFrame:
    next_stop_sequences = stop_times[["trip_id", "stop_id", "stop_sequence"]].rename(
        columns={"stop_id": "next_stop_id", "stop_sequence": "next_stop_sequence"}
    )
    pings = pings.merge(next_stop_sequences, on=["trip_id", "next_stop_id"], how="left")
    api_stop_sequence = (
        pings["api_stop_sequence"]
        if "api_stop_sequence" in pings.columns
        else pd.Series(index=pings.index, dtype="float64")
    )
    pings["current_stop_seq"] = (
        pings["next_stop_sequence"]
        .combine_first(api_stop_sequence)
        .combine_first(pings["fallback_stop_sequence"])
    )
    pings["current_stop_seq"] = pd.to_numeric(pings["current_stop_seq"], errors="coerce")
    return pings.dropna(subset=["current_stop_seq"])


def service_matches_observed_day(row: pd.Series) -> bool:
    calendar_day = DAY_COLUMNS[row["observed_at"].weekday()]
    if calendar_day not in row or pd.isna(row[calendar_day]):
        return True
    return bool(row[calendar_day])


def build_training_rows(
    pings: pd.DataFrame,
    gtfs: dict[str, pd.DataFrame],
    lookahead_stops: int,
    limit: int | None,
    ping_limit: int | None,
) -> list[dict]:
    if ping_limit:
        pings = pings.head(ping_limit).copy()
        print(f"  Using first {len(pings):,} pings for this training build")

    pings = infer_current_stop_sequence(pings, gtfs["stop_times"])
    pings = pings.merge(gtfs["trips"], on="trip_id", how="inner")

    future = pings.merge(gtfs["stop_times"], on="trip_id", how="inner")
    future = future[future["stop_sequence"] > future["current_stop_seq"]].copy()
    future["stops_remaining"] = future["stop_sequence"] - future["current_stop_seq"]
    future = future[future["stops_remaining"].between(1, lookahead_stops)]
    future = future.merge(gtfs["stops"], on="stop_id", how="inner")

    calendar = gtfs["calendar"]
    if not calendar.empty:
        future = future.merge(calendar, on="service_id", how="left")
        future = future[future.apply(service_matches_observed_day, axis=1)]

    future = future.sort_values(["ping_id", "stop_sequence"])
    if limit:
        future = future.head(limit)

    print(f"  Joined ping/future-stop rows: {len(future):,}")

    records = []
    for _, row in future.iterrows():
        try:
            sched_sec = parse_gtfs_time(str(row["arrival_time"]))
            observed_at = parse_datetime(row["observed_at"])
            if observed_at is None:
                continue

            day_of_week = observed_at.weekday()
            feats = build_features(
                observed_at=observed_at,
                bus_lat=float(row["bus_lat"]),
                bus_lon=float(row["bus_lon"]),
                speed_kmh=float(row["speed_kmh"]) if pd.notna(row["speed_kmh"]) else None,
                current_delay_min=float(row["delay_min"]),
                target_stop_lat=float(row["stop_lat"]),
                target_stop_lon=float(row["stop_lon"]),
                scheduled_arrival_sec=sched_sec,
                stop_sequence=int(row["stop_sequence"]),
                stops_remaining=int(row["stops_remaining"]),
                route_id=str(row["route_id"]),
                direction_id=int(row["direction_id"]),
                day_of_week=day_of_week,
                is_weekend=day_of_week >= 5,
            )
        except (TypeError, ValueError):
            continue

        feats["label_delay_min"] = float(row["delay_min"])
        feats["target_stop_id"] = row["stop_id"]
        feats["trip_id"] = row["trip_id"]
        feats["ping_id"] = int(row["ping_id"])
        records.append(feats)

    return records


def write_parquet(df: pd.DataFrame, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, index=False)
    print(f"  Saved -> {out_path}")


def main(
    out_path: str,
    gtfs_path: str,
    file_path: str | None,
    url: str | None,
    start_date: str | None,
    end_date: str | None,
    raw_out_path: str | None,
    gtfs_out_dir: str | None,
    limit: int | None,
    ping_limit: int | None,
    lookahead_stops: int,
    extract_only: bool,
    training_only: bool,
) -> None:
    gtfs_cache_dir = Path(gtfs_out_dir) if gtfs_out_dir else None

    if training_only and gtfs_cache_dir and gtfs_cache_dir.exists():
        gtfs = load_gtfs_parquet(gtfs_cache_dir)
    else:
        gtfs = load_gtfs(Path(gtfs_path))

    if gtfs_cache_dir and not training_only:
        print("Writing static GTFS Parquet files")
        write_gtfs_parquet(gtfs, gtfs_cache_dir)

    if training_only:
        cached_realtime = Path(file_path or raw_out_path or DEFAULT_RAW_OUT_PATH)
        pings = load_realtime_from_file(cached_realtime)
    elif file_path:
        pings = load_realtime_from_file(Path(file_path))
    else:
        source_url = url or os.getenv("LOCATION_EXPORT_URL") or DEFAULT_URL
        pings = load_realtime_from_api(source_url, parse_date(start_date), parse_date(end_date))

    print(f"  Raw pings loaded: {len(pings):,}")

    if raw_out_path and not training_only:
        print("Writing historical bus ping Parquet")
        write_parquet(pings, Path(raw_out_path))

    if extract_only:
        print("Extract-only run complete. Use --training-only to build the training Parquet from cached files.")
        return

    if ping_limit is None and limit:
        ping_limit = max(1_000, limit * 10)

    records = build_training_rows(
        pings,
        gtfs,
        lookahead_stops=lookahead_stops,
        limit=limit,
        ping_limit=ping_limit,
    )
    df = pd.DataFrame(records)
    print(f"  Feature rows built: {len(df):,}")

    if df.empty:
        raise RuntimeError("No training rows were built. Check GTFS path, API dates, and trip_id overlap.")

    write_parquet(df, Path(out_path))

    print("\nLabel stats (delay_min):")
    print(df["label_delay_min"].describe().round(2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build ML Parquet files from static GTFS and location-export data")
    parser.add_argument("--out", default=str(DEFAULT_TRAINING_OUT_PATH), help="Training Parquet output path")
    parser.add_argument(
        "--raw-out",
        default=str(DEFAULT_RAW_OUT_PATH),
        help="Raw API/location pings Parquet output path. Use an empty string to skip.",
    )
    parser.add_argument(
        "--gtfs-out-dir",
        default=str(DEFAULT_GTFS_OUT_DIR),
        help="Directory for normalized static GTFS Parquet files. Use an empty string to skip.",
    )
    parser.add_argument("--gtfs", default=str(DEFAULT_GTFS_PATH), help="GTFS folder or GTFS zip path")
    parser.add_argument("--file", help="Local location-export CSV or raw Parquet file")
    parser.add_argument("--url", help="Location-export API URL")
    parser.add_argument("--start-date", default=DEFAULT_START_DATE, help="Start date (YYYY-MM-DD) for URL fetch")
    parser.add_argument("--end-date", default=DEFAULT_END_DATE, help="End date (YYYY-MM-DD) for URL fetch")
    parser.add_argument("--limit", type=int, default=None, help="Feature row limit for quick tests")
    parser.add_argument(
        "--ping-limit",
        type=int,
        default=None,
        help="Limit raw pings before the GTFS join. Defaults to limit * 10 for limited quick tests.",
    )
    parser.add_argument("--lookahead-stops", type=int, default=20, help="Future stops to train against per ping")
    parser.add_argument(
        "--extract-only",
        action="store_true",
        help="Only save static GTFS and historical API/location pings as Parquet; do not build training rows.",
    )
    parser.add_argument(
        "--training-only",
        action="store_true",
        help="Build training rows from cached GTFS and realtime Parquet; do not fetch the API.",
    )
    args = parser.parse_args()

    if args.extract_only and args.training_only:
        parser.error("--extract-only and --training-only cannot be used together")

    main(
        out_path=args.out,
        gtfs_path=args.gtfs,
        file_path=args.file,
        url=args.url,
        start_date=args.start_date,
        end_date=args.end_date,
        raw_out_path=args.raw_out or None,
        gtfs_out_dir=args.gtfs_out_dir or None,
        limit=args.limit,
        ping_limit=args.ping_limit,
        lookahead_stops=args.lookahead_stops,
        extract_only=args.extract_only,
        training_only=args.training_only,
    )
