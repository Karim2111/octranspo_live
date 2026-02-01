from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import List, Optional
import httpx
from datetime import datetime, timedelta
import asyncio

from database import get_db, init_db
from models import Stop, Route, Schedule, Prediction
from schemas import StopResponse, RouteResponse, ArrivalPrediction
from gtfs_processor import GTFSProcessor
from config import settings

app = FastAPI(title="OC Transpo Live API", version="1.0.0")

# CORS middleware for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize GTFS processor
gtfs_processor = GTFSProcessor()

@app.on_event("startup")
async def startup_event():
    """Initialize database and start background tasks"""
    init_db()
    # Background real-time data refresh disabled (requires OC Transpo API access)
    # asyncio.create_task(refresh_realtime_data())

@app.get("/")
async def root():
    return {"message": "OC Transpo Live API", "status": "running"}

@app.get("/api/stops", response_model=List[StopResponse])
async def get_stops(
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    radius: Optional[float] = 500,
    search: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get transit stops, optionally filtered by location or search query"""
    query = db.query(Stop)
    
    if search:
        query = query.filter(
            (Stop.name.ilike(f"%{search}%")) | 
            (Stop.code.ilike(f"%{search}%"))
        )
    
    if lat and lon:
        # Filter by radius (simplified - in production use PostGIS)
        query = query.filter(
            ((Stop.lat - lat) ** 2 + (Stop.lon - lon) ** 2) <= (radius / 111000) ** 2
        )
    
    stops = query.limit(50).all()
    return stops

@app.get("/api/stops/{stop_id}", response_model=StopResponse)
async def get_stop(stop_id: str, db: Session = Depends(get_db)):
    """Get details for a specific stop"""
    stop = db.query(Stop).filter(Stop.stop_id == stop_id).first()
    if not stop:
        raise HTTPException(status_code=404, detail="Stop not found")
    return stop

@app.get("/api/stops/{stop_id}/arrivals", response_model=List[ArrivalPrediction])
async def get_arrivals(
    stop_id: str, 
    db: Session = Depends(get_db)
):
    """Get real-time arrival predictions for a stop"""
    stop = db.query(Stop).filter(Stop.stop_id == stop_id).first()
    if not stop:
        raise HTTPException(status_code=404, detail="Stop not found")
    
    # Get predictions from cache or generate new ones
    predictions = await gtfs_processor.get_predictions_for_stop(stop_id, db)
    
    # Enhance predictions with ML model
    ml_predictions = await enhance_with_ml_predictions(predictions)
    
    return ml_predictions

@app.get("/api/routes", response_model=List[RouteResponse])
async def get_routes(db: Session = Depends(get_db)):
    """Get all available routes"""
    routes = db.query(Route).all()
    return routes

@app.get("/api/routes/{route_id}", response_model=RouteResponse)
async def get_route(route_id: str, db: Session = Depends(get_db)):
    """Get details for a specific route"""
    route = db.query(Route).filter(Route.route_id == route_id).first()
    if not route:
        raise HTTPException(status_code=404, detail="Route not found")
    return route

async def refresh_realtime_data():
    """Background task to refresh GTFS-RT data every 30 seconds"""
    while True:
        try:
            await gtfs_processor.fetch_realtime_updates()
        except Exception as e:
            print(f"Error refreshing real-time data: {e}")
        await asyncio.sleep(30)

async def enhance_with_ml_predictions(predictions: List[dict]) -> List[dict]:
    """Call ML service to enhance predictions"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{settings.ML_SERVICE_URL}/predict",
                json={"predictions": predictions},
                timeout=5.0
            )
            if response.status_code == 200:
                return response.json()["enhanced_predictions"]
    except Exception as e:
        print(f"ML service error: {e}")
    
    # Return original predictions if ML service fails
    return predictions

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
