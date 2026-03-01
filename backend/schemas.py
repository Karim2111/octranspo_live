from pydantic import BaseModel
from typing import Optional
from datetime import date


class StopResponse(BaseModel):
    stop_id: str
    name: Optional[str]
    stop_lat: Optional[float]
    stop_lon: Optional[float]
    platform_code: Optional[str]

    class Config:
        from_attributes = True


class RouteResponse(BaseModel):
    route_id: str
    name: Optional[str]
    route_color: Optional[str]
    route_text_color: Optional[str]
    route_sort_order: Optional[int]

    class Config:
        from_attributes = True


class CalendarResponse(BaseModel):
    service_id: str
    monday: Optional[bool]
    tuesday: Optional[bool]
    wednesday: Optional[bool]
    thursday: Optional[bool]
    friday: Optional[bool]
    saturday: Optional[bool]
    sunday: Optional[bool]
    start_date: Optional[date]
    end_date: Optional[date]

    class Config:
        from_attributes = True


class TripResponse(BaseModel):
    trip_id: str
    route_id: Optional[str]
    service_id: Optional[str]
    shape_id: Optional[str]
    trip_headsign: Optional[str]
    direction_id: Optional[int]

    class Config:
        from_attributes = True


class StopTimeResponse(BaseModel):
    trip_id: str
    stop_sequence: int
    stop_id: Optional[str]
    arrival_time: Optional[str]
    departure_time: Optional[str]

    class Config:
        from_attributes = True


class ShapePointResponse(BaseModel):
    shape_id: str
    shape_pt_sequence: int
    shape_pt_lat: float
    shape_pt_lon: float

    class Config:
        from_attributes = True
