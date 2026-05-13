"""
Feature engineering for OC Transpo arrival delay prediction.

Input: a row from real_time joined with stop_times + trips + stops + shapes
Output: a flat feature dict ready for the model
"""

import math
from datetime import datetime, time
from typing import Optional


# ── Haversine distance (metres) ───────────────────────────────────────────────
def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ── Time helpers ──────────────────────────────────────────────────────────────
def parse_gtfs_time(t: str) -> int:
    """Convert GTFS time string (may exceed 24:00:00) to seconds since midnight."""
    h, m, s = map(int, t.split(":"))
    return h * 3600 + m * 60 + s


def seconds_since_midnight(dt: datetime) -> int:
    return dt.hour * 3600 + dt.minute * 60 + dt.second


def time_of_day_sin_cos(seconds: int):
    """Encode time cyclically so 23:59 is close to 00:00."""
    angle = 2 * math.pi * seconds / 86400
    return math.sin(angle), math.cos(angle)


DAY_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


# ── Main feature builder ──────────────────────────────────────────────────────
def build_features(
    # From real_time
    observed_at: datetime,          # timestamp of the GPS ping
    bus_lat: float,
    bus_lon: float,
    speed_kmh: Optional[float],
    current_delay_min: float,       # delay_min from the ping

    # From stop_times (the TARGET stop we're predicting)
    target_stop_lat: float,
    target_stop_lon: float,
    scheduled_arrival_sec: int,     # parse_gtfs_time(arrival_time)
    stop_sequence: int,             # position in trip
    stops_remaining: int,           # stops between bus and target

    # From trips / routes
    route_id: str,
    direction_id: int,              # 0 or 1

    # From calendar (today's service)
    day_of_week: int,               # 0=Monday … 6=Sunday
    is_weekend: bool,
) -> dict:
    """
    Returns a flat dict of numeric features.
    Categorical features (route_id) are kept as strings here;
    the pipeline wrapper handles encoding.
    """
    obs_sec = seconds_since_midnight(observed_at)
    tod_sin, tod_cos = time_of_day_sin_cos(obs_sec)

    dist_to_stop_m = haversine(bus_lat, bus_lon, target_stop_lat, target_stop_lon)

    # How many seconds until the stop is *scheduled* to be served
    sched_sec_remaining = scheduled_arrival_sec - obs_sec
    # Can be negative if the bus is already late passing that stop

    # ETA based on current speed (rough baseline)
    speed_ms = (speed_kmh / 3.6) if speed_kmh and speed_kmh > 0 else None
    naive_eta_sec = (dist_to_stop_m / speed_ms) if speed_ms else None

    return {
        # Time encoding
        "tod_sin": tod_sin,
        "tod_cos": tod_cos,
        "day_of_week": day_of_week,
        "is_weekend": int(is_weekend),
        "sched_sec_remaining": sched_sec_remaining,

        # Bus state
        "current_delay_min": current_delay_min,
        "speed_kmh": speed_kmh if speed_kmh is not None else 0.0,
        "naive_eta_sec": naive_eta_sec if naive_eta_sec is not None else -1.0,

        # Spatial
        "dist_to_stop_m": dist_to_stop_m,
        "stop_sequence": stop_sequence,
        "stops_remaining": stops_remaining,

        # Route context (categorical — pipeline will encode)
        "route_id": route_id,
        "direction_id": direction_id,
    }


NUMERIC_FEATURES = [
    "tod_sin", "tod_cos", "day_of_week", "is_weekend",
    "sched_sec_remaining", "current_delay_min", "speed_kmh", "naive_eta_sec",
    "dist_to_stop_m", "stop_sequence", "stops_remaining", "direction_id",
]

CATEGORICAL_FEATURES = ["route_id"]

ALL_FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES
