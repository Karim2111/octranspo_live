from sqlalchemy import Column, String, Float, Integer, DateTime, Boolean, ForeignKey, Text
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime

class Stop(Base):
    __tablename__ = "stops"
    
    id = Column(Integer, primary_key=True, index=True)
    stop_id = Column(String, unique=True, index=True, nullable=False)
    code = Column(String, index=True)
    name = Column(String, nullable=False)
    lat = Column(Float, nullable=False)
    lon = Column(Float, nullable=False)
    location_type = Column(Integer, default=0)
    parent_station = Column(String, nullable=True)
    
    schedules = relationship("Schedule", back_populates="stop")
    predictions = relationship("Prediction", back_populates="stop")

class Route(Base):
    __tablename__ = "routes"
    
    id = Column(Integer, primary_key=True, index=True)
    route_id = Column(String, unique=True, index=True, nullable=False)
    short_name = Column(String)
    long_name = Column(String)
    route_type = Column(Integer)
    color = Column(String)
    text_color = Column(String)
    
    schedules = relationship("Schedule", back_populates="route")
    predictions = relationship("Prediction", back_populates="route")

class Schedule(Base):
    __tablename__ = "schedules"
    
    id = Column(Integer, primary_key=True, index=True)
    stop_id = Column(String, ForeignKey("stops.stop_id"), nullable=False)
    route_id = Column(String, ForeignKey("routes.route_id"), nullable=False)
    trip_id = Column(String, nullable=False)
    arrival_time = Column(String)
    departure_time = Column(String)
    stop_sequence = Column(Integer)
    service_id = Column(String)
    direction_id = Column(Integer)
    
    stop = relationship("Stop", back_populates="schedules")
    route = relationship("Route", back_populates="schedules")

class Prediction(Base):
    __tablename__ = "predictions"
    
    id = Column(Integer, primary_key=True, index=True)
    stop_id = Column(String, ForeignKey("stops.stop_id"), nullable=False)
    route_id = Column(String, ForeignKey("routes.route_id"), nullable=False)
    trip_id = Column(String)
    arrival_time = Column(DateTime)
    scheduled_arrival = Column(DateTime)
    delay_seconds = Column(Integer, default=0)
    predicted_arrival = Column(DateTime)  # ML-enhanced prediction
    confidence = Column(Float)
    vehicle_id = Column(String)
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    stop = relationship("Stop", back_populates="predictions")
    route = relationship("Route", back_populates="predictions")

class GTFSCache(Base):
    __tablename__ = "gtfs_cache"
    
    id = Column(Integer, primary_key=True, index=True)
    feed_type = Column(String, index=True)  # 'static' or 'realtime'
    last_updated = Column(DateTime, default=datetime.utcnow)
    data = Column(Text)  # JSON data
