from sqlalchemy import Column, String, Float, Integer, Boolean, ForeignKey, Date
from database import Base


class Route(Base):
    __tablename__ = "routes"

    route_id = Column(String, primary_key=True, index=True)
    name = Column(String)
    route_color = Column(String)
    route_text_color = Column(String)
    route_sort_order = Column(Integer)


class Calendar(Base):
    __tablename__ = "calendar"

    service_id = Column(String, primary_key=True, index=True)
    monday = Column(Boolean)
    tuesday = Column(Boolean)
    wednesday = Column(Boolean)
    thursday = Column(Boolean)
    friday = Column(Boolean)
    saturday = Column(Boolean)
    sunday = Column(Boolean)
    start_date = Column(Date)
    end_date = Column(Date)


class Stop(Base):
    __tablename__ = "stops"

    stop_id = Column(String, primary_key=True, index=True)
    name = Column(String)
    stop_lat = Column(Float)
    stop_lon = Column(Float)
    platform_code = Column(String)


class Trip(Base):
    __tablename__ = "trips"

    trip_id = Column(String, primary_key=True, index=True)
    route_id = Column(String, ForeignKey("routes.route_id"), index=True)
    # service_id has no DB-level FK because OC Transpo trips reference service_ids
    # that may only exist in calendar_dates.txt, not calendar.txt
    service_id = Column(String, index=True)
    shape_id = Column(String, index=True, nullable=True)
    trip_headsign = Column(String)
    direction_id = Column(Integer)


class Shape(Base):
    __tablename__ = "shapes"

    shape_id = Column(String, primary_key=True)
    shape_pt_sequence = Column(Integer, primary_key=True)
    shape_pt_lat = Column(Float)
    shape_pt_lon = Column(Float)


class StopTime(Base):
    __tablename__ = "stop_times"

    trip_id = Column(String, ForeignKey("trips.trip_id"), primary_key=True)
    stop_sequence = Column(Integer, primary_key=True)
    stop_id = Column(String, ForeignKey("stops.stop_id"), index=True)
    arrival_time = Column(String)    # HH:MM:SS string (may exceed 24h in GTFS)
    departure_time = Column(String)
