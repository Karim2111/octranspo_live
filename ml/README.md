# ml-service - OC Transpo Arrival Predictor

XGBoost model that predicts how many minutes late a bus will arrive at an upcoming stop, given the bus's current GPS position, speed, and current delay.

## How It Works

**Label**: `delay_min` at a future stop, measured in minutes late versus the GTFS schedule. Negative values mean early.

**Key features**:

| Feature | Why it matters |
|---|---|
| `current_delay_min` | Strongest signal because delays propagate |
| `dist_to_stop_m` | How far the bus still has to travel |
| `sched_sec_remaining` | Whether the bus is ahead of or behind the schedule clock |
| `tod_sin / tod_cos` | Rush hour versus off-peak, encoded cyclically |
| `stops_remaining` | Uncertainty grows with distance |
| `speed_kmh` | Low speed can indicate traffic or dwell time |
| `route_id` | Routes have different punctuality profiles |
| `day_of_week` | Weekend and weekday patterns differ |

## Setup

```bash
cd ml
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Workflow

### 1. Build the training dataset

`prepare_data.py` no longer needs PostgreSQL. It reads static GTFS files from `extract/GTFS`, fetches historical location-export CSV data from the API, stores the normalized source data as Parquet, then writes the model-ready training Parquet.

Default run:

```bash
python prepare_data.py
```

Two-step run, useful for large historical exports:

```bash
python prepare_data.py --extract-only
python prepare_data.py --training-only --limit 10000
```

The first command saves GTFS and historical API pings. The second command reuses those cached Parquet files and builds `data/training.parquet` without calling the API again.

That produces:

```text
data/
|-- gtfs/
|   |-- stops.parquet
|   |-- trips.parquet
|   |-- stop_times.parquet
|   `-- calendar.parquet
|-- realtime.parquet
`-- training.parquet
```

Use a local CSV export instead of the API:

```bash
python prepare_data.py --file data/location_export_2026-03-25.csv
```

Fetch a date range from the API:

```bash
python prepare_data.py --start-date 2026-01-08 --end-date 2026-01-30
```

Quick test on a subset:

```bash
python prepare_data.py --training-only --limit 10000
```

When `--limit` is set, the script also limits raw pings before the GTFS join so quick checks do not process the full historical export. Override that with `--ping-limit` if you want a larger or smaller pre-join sample.

Override the source/output folders:

```bash
python prepare_data.py --gtfs extract/GTFS/GTFS_octranspo_2026-01-08_1919.zip --gtfs-out-dir data/gtfs --raw-out data/realtime.parquet --out data/training.parquet
```

You can set `LOCATION_EXPORT_URL` in `backend/.env` to override the default location-export API URL.

### 2. Train the model

```bash
python train.py --data data/training.parquet --out models/delay_model.pkl
```

The script prints MAE, RMSE, R2, and top feature importances on the held-out test set. A good result is MAE under about 2 minutes on OC Transpo data.

### 3. Start the prediction API

```bash
uvicorn server:app --port 8090 --reload
```

### 4. Test it

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

## Integrating With The Main Backend

Copy `ml_client.py` into `backend/` and call it from your stop-times endpoint:

```python
from ml_client import predict_arrivals_for_trip

@app.get("/api/stops/{stop_id}/arrivals")
async def stop_arrivals(stop_id: str, db: Session = Depends(get_db)):
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

## Re-Training

Run `prepare_data.py` and `train.py` again as you accumulate more historical API data. The more pings you have, the better the model learns route-specific delay patterns.

## File Structure

```text
ml/
|-- features.py        # Feature engineering shared by training and inference
|-- prepare_data.py    # Static GTFS + API/location CSV -> Parquet training dataset
|-- train.py           # Train XGBoost and save the pipeline
|-- server.py          # FastAPI prediction API
|-- ml_client.py       # Async client for the main backend
|-- requirements.txt
|-- extract/GTFS/      # Static GTFS zip input
|-- data/              # Parquet outputs
`-- models/            # Saved model artifacts
```
