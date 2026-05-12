import httpx
import zipfile
import io
import csv
from datetime import datetime, date
from typing import Optional
from sqlalchemy import text
from sqlalchemy.orm import Session

from models import Route, Calendar, Stop, Trip, StopTime, Shape
from config import settings


class GTFSProcessor:
    def __init__(self):
        self.static_data_loaded = False

    async def load_static_gtfs(self, db: Session):
        """Download GTFSExport.zip and load all tables into the database."""
        print(f"Downloading GTFS data from {settings.GTFS_STATIC_URL} ...")

        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.get(settings.GTFS_STATIC_URL, timeout=120.0)

        if response.status_code != 200:
            raise Exception(f"Failed to download GTFS data: {response.status_code}")

        zip_data = zipfile.ZipFile(io.BytesIO(response.content))

        try:
            with db.begin():
                print("  Clearing existing data...")
                # Truncate in FK-safe order (children first)
                db.execute(
                    text(
                        "TRUNCATE stop_times, shapes, trips, calendar, stops, routes RESTART IDENTITY CASCADE"
                    )
                )

                print("  Loading stops...")
                self._load_stops(zip_data, db)

                print("  Loading routes...")
                self._load_routes(zip_data, db)

                print("  Loading calendar...")
                self._load_calendar(zip_data, db)

                print("  Loading trips...")
                self._load_trips(zip_data, db)

                print("  Loading shapes...")
                self._load_shapes(zip_data, db)

                print("  Loading stop_times (this may take a while)...")
                self._load_stop_times(zip_data, db)
        except Exception:
            db.rollback()
            raise

        self.static_data_loaded = True
        print("Static GTFS data loaded successfully.")

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
                    db.bulk_insert_mappings(Stop, batch)
                    db.flush()
                    batch = []
            if batch:
                db.bulk_insert_mappings(Stop, batch)
                db.flush()

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
                db.bulk_insert_mappings(Route, batch)
                db.flush()

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
                db.bulk_insert_mappings(Calendar, batch)
                db.flush()

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
                    db.bulk_insert_mappings(Trip, batch)
                    db.flush()
                    batch = []
            if batch:
                db.bulk_insert_mappings(Trip, batch)
                db.flush()

    def _load_shapes(self, zip_data: zipfile.ZipFile, db: Session):
        if "shapes.txt" not in zip_data.namelist():
            print("  shapes.txt not found in zip, skipping.")
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
                    db.bulk_insert_mappings(Shape, batch)
                    db.flush()
                    batch = []
            if batch:
                db.bulk_insert_mappings(Shape, batch)
                db.flush()

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
                    db.bulk_insert_mappings(StopTime, batch)
                    db.flush()
                    batch = []
            if batch:
                db.bulk_insert_mappings(StopTime, batch)
                db.flush()

