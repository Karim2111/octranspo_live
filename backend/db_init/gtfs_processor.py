import zipfile
import io
import csv
from pathlib import Path
from datetime import datetime, date
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert as pg_insert

from db_init.models import Route, Calendar, Stop, Trip, StopTime, Shape


class GTFSProcessor:
    def __init__(self):
        self.static_data_loaded = False

    async def load_static_gtfs(self, db: Session):
        """Load GTFS zip files from backend/GTFS into the database."""
        gtfs_dir = Path(__file__).resolve().parent.parent / "GTFS"
        if not gtfs_dir.exists() or not gtfs_dir.is_dir():
            raise FileNotFoundError(f"GTFS folder not found: {gtfs_dir}")

        zip_paths = sorted(gtfs_dir.glob("*.zip"))
        if not zip_paths:
            raise FileNotFoundError(f"No GTFS zip files found in: {gtfs_dir}")

        for zip_path in zip_paths:
            print(f"Loading GTFS file: {zip_path.name}")
            try:
                with zipfile.ZipFile(zip_path) as zip_data:
                    with db.begin():
                        self._load_stops(zip_data, db)
                        print("Stops complete")
                        self._load_routes(zip_data, db)
                        print("Routes complete")
                        self._load_calendar(zip_data, db)
                        print("Calendar complete")
                        self._load_trips(zip_data, db)
                        print("Trips complete")
                        self._load_shapes(zip_data, db)
                        print("Shapes complete")
                        self._load_stop_times(zip_data, db)
                        print("Stop times complete")
            except Exception:
                db.rollback()
                raise

        self.static_data_loaded = True

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_date(date_str: str) -> Optional[date]:
        """Convert GTFS YYYYMMDD string to a Python date."""
        if not date_str or not date_str.strip():
            return None
        try:
            return datetime.strptime(date_str.strip(), "%Y%m%d").date()
        except ValueError:
            return None

    @staticmethod
    def _bulk_insert_ignore(db: Session, model, rows):
        if not rows:
            return
        index_elements = [col.name for col in model.__table__.primary_key.columns]
        stmt = pg_insert(model.__table__).values(rows)
        stmt = stmt.on_conflict_do_nothing(index_elements=index_elements)
        db.execute(stmt)

    # ------------------------------------------------------------------
    # Loaders
    # ------------------------------------------------------------------

    def _load_stops(self, zip_data: zipfile.ZipFile, db: Session):
        with zip_data.open("stops.txt") as f:
            reader = csv.DictReader(io.TextIOWrapper(f, "utf-8"))
            batch = []
            for row in reader:
                batch.append(
                    dict(
                        stop_id=row["stop_id"],
                        name=row.get("stop_name"),
                        stop_lat=float(row["stop_lat"]) if row.get("stop_lat") else None,
                        stop_lon=float(row["stop_lon"]) if row.get("stop_lon") else None,
                        platform_code=row.get("platform_code") or None,
                    )
                )
                if len(batch) >= 1000:
                    self._bulk_insert_ignore(db, Stop, batch)
                    batch = []
            if batch:
                self._bulk_insert_ignore(db, Stop, batch)

    def _load_routes(self, zip_data: zipfile.ZipFile, db: Session):
        with zip_data.open("routes.txt") as f:
            reader = csv.DictReader(io.TextIOWrapper(f, "utf-8"))
            batch = []
            for row in reader:
                sort_order = row.get("route_sort_order")
                batch.append(
                    dict(
                        route_id=row["route_id"],
                        name=row.get("route_long_name") or row.get("route_short_name"),
                        route_color=row.get("route_color") or None,
                        route_text_color=row.get("route_text_color") or None,
                        route_sort_order=int(sort_order) if sort_order else None,
                    )
                )
            if batch:
                self._bulk_insert_ignore(db, Route, batch)

    def _load_calendar(self, zip_data: zipfile.ZipFile, db: Session):
        with zip_data.open("calendar.txt") as f:
            reader = csv.DictReader(io.TextIOWrapper(f, "utf-8"))
            batch = []
            for row in reader:
                batch.append(
                    dict(
                        service_id=row["service_id"],
                        monday=bool(int(row.get("monday", 0))),
                        tuesday=bool(int(row.get("tuesday", 0))),
                        wednesday=bool(int(row.get("wednesday", 0))),
                        thursday=bool(int(row.get("thursday", 0))),
                        friday=bool(int(row.get("friday", 0))),
                        saturday=bool(int(row.get("saturday", 0))),
                        sunday=bool(int(row.get("sunday", 0))),
                        start_date=self._parse_date(row.get("start_date")),
                        end_date=self._parse_date(row.get("end_date")),
                    )
                )
            if batch:
                self._bulk_insert_ignore(db, Calendar, batch)

    def _load_trips(self, zip_data: zipfile.ZipFile, db: Session):
        with zip_data.open("trips.txt") as f:
            reader = csv.DictReader(io.TextIOWrapper(f, "utf-8"))
            batch = []
            for row in reader:
                direction = row.get("direction_id")
                batch.append(
                    dict(
                        trip_id=row["trip_id"],
                        route_id=row["route_id"],
                        service_id=row.get("service_id"),
                        shape_id=row.get("shape_id") or None,
                        trip_headsign=row.get("trip_headsign"),
                        direction_id=int(direction) if direction else None,
                    )
                )
                if len(batch) >= 5000:
                    self._bulk_insert_ignore(db, Trip, batch)
                    batch = []
            if batch:
                self._bulk_insert_ignore(db, Trip, batch)

    def _load_shapes(self, zip_data: zipfile.ZipFile, db: Session):
        if "shapes.txt" not in zip_data.namelist():
            return
        with zip_data.open("shapes.txt") as f:
            reader = csv.DictReader(io.TextIOWrapper(f, "utf-8"))
            batch = []
            for row in reader:
                batch.append(
                    dict(
                        shape_id=row["shape_id"],
                        shape_pt_sequence=int(row["shape_pt_sequence"]),
                        shape_pt_lat=float(row["shape_pt_lat"]),
                        shape_pt_lon=float(row["shape_pt_lon"]),
                    )
                )
                if len(batch) >= 10000:
                    self._bulk_insert_ignore(db, Shape, batch)
                    batch = []
            if batch:
                self._bulk_insert_ignore(db, Shape, batch)

    def _load_stop_times(self, zip_data: zipfile.ZipFile, db: Session):
        with zip_data.open("stop_times.txt") as f:
            reader = csv.DictReader(io.TextIOWrapper(f, "utf-8"))
            batch = []
            for row in reader:
                batch.append(
                    dict(
                        trip_id=row["trip_id"],
                        stop_sequence=int(row["stop_sequence"]),
                        stop_id=row["stop_id"],
                        arrival_time=row.get("arrival_time"),
                        departure_time=row.get("departure_time"),
                    )
                )
                if len(batch) >= 10000:
                    self._bulk_insert_ignore(db, StopTime, batch)
                    batch = []
            if batch:
                self._bulk_insert_ignore(db, StopTime, batch)

