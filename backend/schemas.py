from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class StopBase(BaseModel):
    stop_id: str
    code: Optional[str]
    name: str
    lat: float
    lon: float

class StopResponse(StopBase):
    id: int
    
    class Config:
        from_attributes = True

class RouteBase(BaseModel):
    route_id: str
    short_name: Optional[str]
    long_name: Optional[str]
    route_type: int
    color: Optional[str]
    text_color: Optional[str]

class RouteResponse(RouteBase):
    id: int
    
    class Config:
        from_attributes = True

class ArrivalPrediction(BaseModel):
    route_short_name: str
    route_long_name: str
    route_id: str
    headsign: str
    scheduled_arrival: datetime
    predicted_arrival: Optional[datetime]
    delay_seconds: int
    minutes_until_arrival: int
    confidence: Optional[float]
    is_realtime: bool
    vehicle_id: Optional[str]
    
    class Config:
        from_attributes = True

class ScheduleResponse(BaseModel):
    trip_id: str
    route_id: str
    arrival_time: str
    departure_time: str
    stop_sequence: int
    
    class Config:
        from_attributes = True
