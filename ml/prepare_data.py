"""
prepare_data.py
───────────────
Joins real_time pings with GTFS static tables to produce a training dataset.

Each row = one (bus ping → future stop) pair.
Label = actual delay at that stop (minutes late vs schedule).

Run:
    python prepare_data.py --out data/training.parquet
"""

import argparse
import os
from datetime import datetime
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine

from features import (
    build_features,
    parse_gtfs_time,
    seconds_since_midnight,
    haversine,
)

def load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


project_root = Path(__file__).resolve().parents[1]
load_env_file(project_root / "backend" / ".env")

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://octranspo:octranspo@localhost:5432/octranspo_live",
)


# ── SQL ───────────────────────────────────────────────────────────────────────

# Pull every real_time ping that has the essential fields populated.
# For each ping we join forward to all future stops on that trip so the model
# can predict delay to *any* upcoming stop, not just the next one.
QUERY = """
WITH pings AS (
    SELECT
        rt.id                   AS ping_id,
        rt.time                 AS observed_at,
        rt.trip_id,
        rt.delay_min,
        rt.latitude             AS bus_lat,
        rt.longitude            AS bus_lon,
        rt.speed                AS speed_kmh,
        rt.next_stop_id,
        rt.stop_sequence        AS current_stop_seq,
        t.route_id,
        t.direction_id,
        t.service_id
    FROM real_time rt
    JOIN trips t ON t.trip_id = rt.trip_id
    WHERE rt.trip_id IS NOT NULL
      AND rt.delay_min IS NOT NULL
      AND rt.latitude IS NOT NULL
      AND rt.longitude IS NOT NULL
),
future_stops AS (
    -- For each ping, get all stops that come AFTER the bus's current position
    SELECT
        p.ping_id,
        p.observed_at,
        p.trip_id,
        p.delay_min             AS current_delay_min,
        p.bus_lat,
        p.bus_lon,
        p.speed_kmh,
        p.current_stop_seq,
        p.route_id,
        p.direction_id,
        p.service_id,
        st.stop_id              AS target_stop_id,
        st.stop_sequence        AS target_stop_seq,
        st.arrival_time         AS scheduled_arrival,
        s.stop_lat              AS target_lat,
        s.stop_lon              AS target_lon,
        (st.stop_sequence - p.current_stop_seq) AS stops_remaining
    FROM pings p
    JOIN stop_times st ON st.trip_id = p.trip_id
                       AND st.stop_sequence > p.current_stop_seq
    JOIN stops s ON s.stop_id = st.stop_id
)
SELECT
    fs.*,
    -- Calendar info to compute day_of_week
    c.monday, c.tuesday, c.wednesday, c.thursday,
    c.friday, c.saturday, c.sunday
FROM future_stops fs
JOIN calendar c ON c.service_id = fs.service_id
-- Limit look-ahead to 20 stops to keep dataset manageable
WHERE fs.stops_remaining BETWEEN 1 AND 20
ORDER BY fs.ping_id, fs.target_stop_seq
"""


def day_of_week_from_calendar(row) -> int:
    """Return 0=Mon … 6=Sun from the observed_at timestamp."""
    return row["observed_at"].weekday()


def is_weekend(dow: int) -> bool:
    return dow >= 5


def build_row(row: pd.Series) -> dict | None:
    try:
        sched_sec = parse_gtfs_time(row["scheduled_arrival"])
    except Exception:
        return None

    obs_at: datetime = row["observed_at"]
    if not isinstance(obs_at, datetime):
        return None

    dow = day_of_week_from_calendar(row)

    feats = build_features(
        observed_at=obs_at,
        bus_lat=float(row["bus_lat"]),
        bus_lon=float(row["bus_lon"]),
        speed_kmh=float(row["speed_kmh"]) if pd.notna(row["speed_kmh"]) else None,
        current_delay_min=float(row["current_delay_min"]),
        target_stop_lat=float(row["target_lat"]),
        target_stop_lon=float(row["target_lon"]),
        scheduled_arrival_sec=sched_sec,
        stop_sequence=int(row["target_stop_seq"]),
        stops_remaining=int(row["stops_remaining"]),
        route_id=str(row["route_id"]),
        direction_id=int(row["direction_id"]),
        day_of_week=dow,
        is_weekend=is_weekend(dow),
    )

    # Label: we use the *current* delay as the proxy label.
    # In a richer dataset you'd join the next real_time ping at the target stop.
    # For now, delay propagation is our best approximation.
    feats["label_delay_min"] = float(row["current_delay_min"])
    feats["target_stop_id"] = row["target_stop_id"]
    feats["trip_id"] = row["trip_id"]
    feats["ping_id"] = row["ping_id"]

    return feats


def main(out_path: str, limit: int | None = None):
    engine = create_engine(DATABASE_URL)
    print("Fetching data from PostgreSQL…")
    query = QUERY
    if limit:
        query += f" LIMIT {limit}"

    df_raw = pd.read_sql(query, engine)

    print(f"  Raw rows fetched: {len(df_raw):,}")

    records = []
    for _, row in df_raw.iterrows():
        r = build_row(row)
        if r:
            records.append(r)

    df = pd.DataFrame(records)
    print(f"  Feature rows built: {len(df):,}")

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    df.to_parquet(out_path, index=False)
    print(f"  Saved → {out_path}")

    # Quick sanity check
    print("\nLabel stats (delay_min):")
    print(df["label_delay_min"].describe().round(2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="data/training.parquet")
    parser.add_argument("--limit", type=int, default=None, help="Row limit for quick tests")
    args = parser.parse_args()
    main(args.out, args.limit)
