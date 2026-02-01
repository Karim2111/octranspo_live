import httpx
import zipfile
import io
import csv
from datetime import datetime, timedelta
from typing import List, Dict
from sqlalchemy.orm import Session
from google.transit import gtfs_realtime_pb2
import json

from models import Stop, Route, Schedule, Prediction, GTFSCache
from config import settings

class GTFSProcessor:
    def __init__(self):
        self.static_data_loaded = False
    
    async def load_static_gtfs(self, db: Session):
        """Download and load static GTFS data"""
        print("Loading static GTFS data...")
        
        async with httpx.AsyncClient() as client:
            response = await client.get(settings.GTFS_STATIC_URL, timeout=60.0)
            
            if response.status_code != 200:
                raise Exception(f"Failed to download GTFS data: {response.status_code}")
            
            # Extract zip file
            zip_data = zipfile.ZipFile(io.BytesIO(response.content))
            
            # Load stops
            await self._load_stops(zip_data, db)
            
            # Load routes
            await self._load_routes(zip_data, db)
            
            # Load stop times (schedules)
            await self._load_schedules(zip_data, db)
            
            db.commit()
            self.static_data_loaded = True
            print("Static GTFS data loaded successfully")
    
    async def _load_stops(self, zip_data: zipfile.ZipFile, db: Session):
        """Load stops from stops.txt"""
        with zip_data.open('stops.txt') as f:
            reader = csv.DictReader(io.TextIOWrapper(f, 'utf-8'))
            
            for row in reader:
                stop = db.query(Stop).filter(Stop.stop_id == row['stop_id']).first()
                if not stop:
                    stop = Stop(
                        stop_id=row['stop_id'],
                        code=row.get('stop_code'),
                        name=row['stop_name'],
                        lat=float(row['stop_lat']),
                        lon=float(row['stop_lon']),
                        location_type=int(row.get('location_type', 0)),
                        parent_station=row.get('parent_station')
                    )
                    db.add(stop)
            
            db.flush()
    
    async def _load_routes(self, zip_data: zipfile.ZipFile, db: Session):
        """Load routes from routes.txt"""
        with zip_data.open('routes.txt') as f:
            reader = csv.DictReader(io.TextIOWrapper(f, 'utf-8'))
            
            for row in reader:
                route = db.query(Route).filter(Route.route_id == row['route_id']).first()
                if not route:
                    route = Route(
                        route_id=row['route_id'],
                        short_name=row.get('route_short_name'),
                        long_name=row.get('route_long_name'),
                        route_type=int(row.get('route_type', 3)),
                        color=row.get('route_color'),
                        text_color=row.get('route_text_color')
                    )
                    db.add(route)
            
            db.flush()
    
    async def _load_schedules(self, zip_data: zipfile.ZipFile, db: Session):
        """Load schedules from stop_times.txt (sample only for performance)"""
        # In production, you'd want to filter by service_id for current day
        with zip_data.open('stop_times.txt') as f:
            reader = csv.DictReader(io.TextIOWrapper(f, 'utf-8'))
            
            count = 0
            for row in reader:
                # Sample every 10th record to avoid massive database
                if count % 10 == 0:
                    schedule = Schedule(
                        stop_id=row['stop_id'],
                        trip_id=row['trip_id'],
                        arrival_time=row['arrival_time'],
                        departure_time=row['departure_time'],
                        stop_sequence=int(row['stop_sequence'])
                    )
                    db.add(schedule)
                count += 1
            
            db.flush()
    
    async def fetch_realtime_updates(self):
        """Fetch GTFS-RT trip updates"""
        try:
            async with httpx.AsyncClient() as client:
                # Fetch trip updates
                response = await client.get(settings.GTFS_RT_TRIP_URL, timeout=10.0)
                
                if response.status_code == 200:
                    feed = gtfs_realtime_pb2.FeedMessage()
                    feed.ParseFromString(response.content)
                    
                    return self._parse_trip_updates(feed)
        except Exception as e:
            print(f"Error fetching real-time updates: {e}")
            return []
    
    def _parse_trip_updates(self, feed) -> List[Dict]:
        """Parse GTFS-RT trip updates"""
        updates = []
        
        for entity in feed.entity:
            if entity.HasField('trip_update'):
                trip_update = entity.trip_update
                
                for stop_time_update in trip_update.stop_time_update:
                    updates.append({
                        'trip_id': trip_update.trip.trip_id,
                        'route_id': trip_update.trip.route_id,
                        'stop_id': stop_time_update.stop_id,
                        'arrival_delay': stop_time_update.arrival.delay if stop_time_update.HasField('arrival') else 0,
                        'arrival_time': stop_time_update.arrival.time if stop_time_update.HasField('arrival') else None,
                        'vehicle_id': trip_update.vehicle.id if trip_update.HasField('vehicle') else None
                    })
        
        return updates
    
    async def get_predictions_for_stop(self, stop_id: str, db: Session) -> List[Dict]:
        """Get arrival predictions for a specific stop"""
        now = datetime.now()
        
        # Get scheduled arrivals for next 2 hours
        predictions = []
        
        # Query schedules
        schedules = db.query(Schedule).filter(
            Schedule.stop_id == stop_id
        ).limit(20).all()
        
        for schedule in schedules:
            route = db.query(Route).filter(Route.route_id == schedule.route_id).first()
            if not route:
                continue
            
            # Parse arrival time
            try:
                hours, minutes, seconds = map(int, schedule.arrival_time.split(':'))
                scheduled_time = now.replace(hour=hours % 24, minute=minutes, second=seconds, microsecond=0)
                
                # Adjust for next day if needed
                if scheduled_time < now:
                    scheduled_time += timedelta(days=1)
                
                minutes_until = int((scheduled_time - now).total_seconds() / 60)
                
                # Only include arrivals in next 120 minutes
                if 0 <= minutes_until <= 120:
                    predictions.append({
                        'route_short_name': route.short_name or route.route_id,
                        'route_long_name': route.long_name or '',
                        'route_id': route.route_id,
                        'headsign': route.long_name or '',
                        'scheduled_arrival': scheduled_time.isoformat(),
                        'predicted_arrival': scheduled_time.isoformat(),
                        'delay_seconds': 0,
                        'minutes_until_arrival': minutes_until,
                        'confidence': 0.8,
                        'is_realtime': False,
                        'vehicle_id': None
                    })
            except Exception as e:
                print(f"Error parsing time: {e}")
                continue
        
        # Sort by arrival time
        predictions.sort(key=lambda x: x['minutes_until_arrival'])
        
        return predictions[:10]  # Return top 10 upcoming arrivals
