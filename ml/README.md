# ml-service — OC Transpo Arrival Predictor

XGBoost model that predicts how many minutes late a bus will arrive at an upcoming stop, given the bus's current GPS position, speed, and current delay.

---

## How it works

**Label**: `delay_min` at a future stop (minutes late vs GTFS schedule; negative = early).

**Key features**:
| Feature | Why it matters |
|---|---|
| `current_delay_min` | Strongest signal — delays propagate |
| `dist_to_stop_m` | How far the bus still has to travel |
| `sched_sec_remaining` | Is the bus running ahead/behind the clock? |
| `tod_sin / tod_cos` | Rush hour vs off-peak (cyclic encoding) |
| `stops_remaining` | Uncertainty grows with distance |
| `speed_kmh` | Low speed = likely stuck in traffic |
| `route_id` | Routes have different punctuality profiles |
| `day_of_week` | Weekend/weekday patterns differ |

---

## Setup

```bash
cd ml-service
python -m venv .venv
.venv\Scripts\activate   # Windows
# or: source .venv/bin/activate   # Linux/Mac
pip install -r requirements.txt
```

---

## Workflow

### 1 — Build the training dataset

Pulls from your PostgreSQL database and writes a parquet file.

```bash
python prepare_data.py --out data/training.parquet
```

Quick test on a subset:
```bash
python prepare_data.py --out data/training.parquet --limit 100000
```

### 2 — Train the model

```bash
python train.py --data data/training.parquet --out models/delay_model.pkl
```

Prints MAE / RMSE / R² on the held-out test set and top feature importances.
A good result is MAE < 2 minutes on OC Transpo data.

### 3 — Start the prediction API

```bash
uvicorn server:app --port 8090 --reload
```

### 4 — Test it

```bash
curl -X POST http://localhost:8090/predict \
  -H "Content-Type: application/json" \
  -d '{
    "observed_at": "2026-03-24T07:00:00",
    "bus_lat": 45.3443,
    "bus_lon": -75.8135,
    "speed_kmh": 12.07,
    "current_delay_min": -1.75,
    "target_stop_lat": 45.3500,
    "target_stop_lon": -75.8000,
    "scheduled_arrival": "07:15:00",
    "stop_sequence": 12,
    "stops_remaining": 3,
    "route_id": "10",
    "direction_id": 0,
    "day_of_week": 0
  }'
```

Expected response:
```json
{
  "predicted_delay_min": -1.42,
  "predicted_arrival": "07:14",
  "scheduled_arrival": "07:15",
  "confidence_band_min": 2.08
}
```

---

## Integrating with the main backend

Copy `ml_client.py` into `backend/` and call it from your stop-times endpoint:

```python
# In backend/main.py
from ml_client import predict_arrivals_for_trip

@app.get("/api/stops/{stop_id}/arrivals")
async def stop_arrivals(stop_id: str, db: Session = Depends(get_db)):
    # ... get latest rt ping for each trip serving this stop ...
    predictions = await predict_arrivals_for_trip(
        trip_id=trip_id,
        rt_ping=latest_ping,
        upcoming_stops=future_stop_times,
        db=db,
    )
    return predictions
```

Set `ML_SERVICE_URL` in `backend/.env`:
```env
ML_SERVICE_URL=http://localhost:8090
```

---

## Re-training

Run `prepare_data.py` + `train.py` again as you accumulate more real_time rows.
The more historical pings you have, the better the model learns route-specific delay patterns.

---

## File structure

```
ml-service/
├── features.py        # Feature engineering (shared by training + inference)
├── prepare_data.py    # DB → parquet training dataset
├── train.py           # Train XGBoost + save pipeline
├── server.py          # FastAPI prediction API
├── ml_client.py       # Async client for the main backend
├── requirements.txt
├── data/              # training.parquet (gitignored)
└── models/            # delay_model.pkl (gitignored)
```
