# OC Transpo Live

A real-time Ottawa transit map built with FastAPI, PostgreSQL, and React-Leaflet. Loads OC Transpo GTFS static data into a local database and displays routes and nearby stops on an interactive dark map.

---

## Features

- Interactive dark map (Carto) centered on user's current location
- Sidebar lists bus routes within 800 m of the user, sorted by distance
- Click any nearby route card to draw the full route polyline on the map
- Search by route number (e.g. `10`, `95`) to display that route's stops and timing
- Search by stop name when a route match is not found
- Click any stop on the map or in the sidebar to see its arrival time

---

## Stack

| Layer | Tech |
|---|---|
| Backend | FastAPI · SQLAlchemy · PostgreSQL |
| GTFS pipeline | httpx · bulk `INSERT` via SQLAlchemy |
| Frontend | React 18 · react-leaflet · Tailwind CSS |
| Map tiles | Carto Dark Matter |

---

## Project Structure

```
octranspo_live/
├── backend/
│   ├── main.py            # FastAPI app + all REST endpoints
│   ├── models.py          # SQLAlchemy ORM (5 GTFS tables)
│   ├── schemas.py         # Pydantic response models
│   ├── gtfs_processor.py  # Downloads + bulk-loads GTFS zip
│   ├── database.py        # Engine + session factory
│   ├── config.py          # Settings (DATABASE_URL, GTFS_STATIC_URL, …)
│   ├── init_db.py         # One-shot: create tables + load GTFS data
│   └── print_route.py     # CLI: print a route's current active trip 
├── frontend/
│   ├── src/
│   │   ├── App.js         # Main React app
│   │   └── index.js
│   └── package.json
└── ml-service/            # (in progress) prediction service
```

---

## Database Schema

```
routes          stops
──────────      ──────────
route_id  PK    stop_id   PK
name            name
route_color     stop_lat
route_text_color stop_lon
route_sort_order platform_code

trips                    stop_times
──────────────           ────────────────────────
trip_id       PK         trip_id       PK (composite)
route_id      FK→routes  stop_sequence PK (composite)
service_id               stop_id       FK→stops
trip_headsign            arrival_time
direction_id             departure_time

calendar
────────────
service_id  PK
monday … sunday (boolean)
start_date
end_date
```

---

## Setup

### Prerequisites

- Python 3.11+
- Node.js 18+
- PostgreSQL running locally

### 1 — Database

Create the database and user:

```sql
CREATE USER octranspo WITH PASSWORD 'octranspo';
CREATE DATABASE octranspo_live OWNER octranspo;
```

### 2 — Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt

# Create env file from template
copy .env.example .env

# Create tables and load GTFS data (~2–3 min first run)
python init_db.py
```

Start the API server (port 8080):

```bash
uvicorn main:app --reload --port 8080
```

### 3 — Frontend

```bash
cd frontend
npm install
copy .env.example .env
npm start          # http://localhost:3000
```

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/routes` | All routes |
| GET | `/api/routes/{id}` | Single route |
| GET | `/api/routes/{id}/trips` | Trips for a route |
| GET | `/api/routes/{id}/stops?direction_id=0|1` | Ordered stops for nearest scheduled trip in a direction |
| GET | `/api/stops` | Stops (filter by `search`, `lat`/`lon`/`radius`) |
| GET | `/api/stops/{id}` | Single stop |
| GET | `/api/stops/{id}/stop_times` | Stop times at a stop |
| GET | `/api/trips/{id}/stop_times` | Stop times for a trip |
| GET | `/api/calendar` | All calendar entries |
| GET | `/api/nearby-routes` | Routes near `lat`/`lon` within `radius` metres |
| POST | `/api/admin/reload-gtfs` | Re-download and reload GTFS data (requires `x-admin-key`) |

### Nearby routes example

```
GET /api/nearby-routes?lat=45.4215&lon=-75.6972&radius=800&limit=12
```

```json
[
  {
    "route_id": "10",
    "name": "Hurdman / Carleton U",
    "route_color": "CE1126",
    "nearest_stop": "BANK / LISGAR",
    "nearest_m": 142
  }
]
```

---

## CLI Tool

Print the currently active trip for a route (uses local time):

```bash
cd backend
python print_route.py 10
```

---

## Configuration

Create `backend/.env` to override defaults (or copy from `.env.example`):

```env
DATABASE_URL=postgresql://octranspo:octranspo@localhost:5432/octranspo_live
GTFS_STATIC_URL=https://oct-gtfs-emasagcnfmcgeham.z01.azurefd.net/public-access/GTFSExport.zip
GTFS_RT_VEHICLE_POSITIONS_URL=https://nextrip-public-api.azure-api.net/octranspo/gtfs-rt-vp/beta/v1/VehiclePositions
GTFS_PRIMARY_KEY=
ADMIN_API_KEY=change-me
DEBUG=True
```

Create `frontend/.env` (or copy from `.env.example`):

```env
REACT_APP_API_BASE_URL=http://localhost:8080/api
```
