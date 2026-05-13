"""
server.py
─────────
FastAPI micro-service that wraps the trained model.

Exposes:
  POST /predict          – predict delay for one (bus, stop) pair
  POST /predict/batch    – predict for multiple upcoming stops at once
  GET  /health           – liveness check + model metadata

Start:
    uvicorn server:app --port 8090 --reload
"""

import os
import pickle
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from features import build_features, parse_gtfs_time

MODEL_PATH = os.getenv("MODEL_PATH", "models/delay_model.pkl")

app = FastAPI(title="OC Transpo Arrival Predictor", version="0.1.0")

# ── Load model at startup ─────────────────────────────────────────────────────
_pipeline = None


@app.on_event("startup")
def load_model():
    global _pipeline
    if not os.path.exists(MODEL_PATH):
        print(f"WARNING: model not found at {MODEL_PATH}. Train first.")
        return
    with open(MODEL_PATH, "rb") as f:
        _pipeline = pickle.load(f)
    print(f"Model loaded from {MODEL_PATH}")


# ── Schemas ───────────────────────────────────────────────────────────────────

class PredictRequest(BaseModel):
    # Live bus state (from GTFS-RT or real_time table)
    observed_at: datetime = Field(..., description="UTC timestamp of the GPS ping")
    bus_lat: float
    bus_lon: float
    speed_kmh: Optional[float] = None
    current_delay_min: float = Field(..., description="Current delay in minutes (negative = early)")

    # Target stop (from stop_times + stops)
    target_stop_lat: float
    target_stop_lon: float
    scheduled_arrival: str = Field(..., description="GTFS time string, e.g. '08:34:00' or '25:12:00'")
    stop_sequence: int
    stops_remaining: int

    # Route context
    route_id: str
    direction_id: int = Field(..., ge=0, le=1)

    # Calendar
    day_of_week: int = Field(..., ge=0, le=6, description="0=Monday … 6=Sunday")


class PredictResponse(BaseModel):
    predicted_delay_min: float = Field(..., description="Predicted minutes late (negative = early)")
    predicted_arrival: str = Field(..., description="Predicted wall-clock arrival (HH:MM)")
    scheduled_arrival: str
    confidence_band_min: float = Field(..., description="±N minutes (rough 80% interval)")


class BatchPredictRequest(BaseModel):
    stops: list[PredictRequest]


class BatchPredictResponse(BaseModel):
    predictions: list[PredictResponse]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _predict_one(req: PredictRequest) -> PredictResponse:
    if _pipeline is None:
        raise HTTPException(status_code=503, detail="Model not loaded. Run train.py first.")

    feats = build_features(
        observed_at=req.observed_at,
        bus_lat=req.bus_lat,
        bus_lon=req.bus_lon,
        speed_kmh=req.speed_kmh,
        current_delay_min=req.current_delay_min,
        target_stop_lat=req.target_stop_lat,
        target_stop_lon=req.target_stop_lon,
        scheduled_arrival_sec=parse_gtfs_time(req.scheduled_arrival),
        stop_sequence=req.stop_sequence,
        stops_remaining=req.stops_remaining,
        route_id=req.route_id,
        direction_id=req.direction_id,
        day_of_week=req.day_of_week,
        is_weekend=req.day_of_week >= 5,
    )

    import pandas as pd
    X = pd.DataFrame([feats])

    delay = float(_pipeline["model"].predict(_pipeline["prep"].transform(X))[0])

    # Compute predicted wall-clock arrival
    sched_sec = parse_gtfs_time(req.scheduled_arrival)
    predicted_sec = sched_sec + int(delay * 60)
    predicted_sec = max(0, predicted_sec)
    pred_h = (predicted_sec // 3600) % 24
    pred_m = (predicted_sec % 3600) // 60
    predicted_arrival_str = f"{pred_h:02d}:{pred_m:02d}"

    sched_h = (sched_sec // 3600) % 24
    sched_m = (sched_sec % 3600) // 60
    scheduled_arrival_str = f"{sched_h:02d}:{sched_m:02d}"

    # Rough confidence band: grows with stops_remaining and current delay magnitude
    base_band = 1.5
    band = base_band + 0.15 * req.stops_remaining + 0.05 * abs(delay)

    return PredictResponse(
        predicted_delay_min=round(delay, 2),
        predicted_arrival=predicted_arrival_str,
        scheduled_arrival=scheduled_arrival_str,
        confidence_band_min=round(band, 2),
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {
        "status": "ok" if _pipeline is not None else "model_not_loaded",
        "model_path": MODEL_PATH,
    }


@app.post("/predict", response_model=PredictResponse)
def predict(req: PredictRequest):
    return _predict_one(req)


@app.post("/predict/batch", response_model=BatchPredictResponse)
def predict_batch(req: BatchPredictRequest):
    if not req.stops:
        raise HTTPException(status_code=400, detail="stops list is empty")
    return BatchPredictResponse(predictions=[_predict_one(s) for s in req.stops])
