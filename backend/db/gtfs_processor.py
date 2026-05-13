import argparse
import asyncio
import csv
import io
import os
import sys
import zipfile
from datetime import datetime, date
from pathlib import Path
from typing import Optional, Union

import httpx
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import Session

ROOT = os.path.dirname(os.path.dirname(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from config import settings
from db.database import SessionLocal, init_db
from db.models import Route, Calendar, Stop, Trip, StopTime, Shape


class GTFSProcessor:
    def __init__(self):
        self.static_data_loaded = False
        self.gtfs_dir = Path(__file__).resolve().parent / "GTFS"

    async def download_static_gtfs(
        self,
        url: str,
        force: bool = False,
        filename: Optional[str] = None,
    ) -> Path:
        """Download the configured GTFS static zip into backend/db/GTFS."""
        if not url:
            raise ValueError("GTFS_STATIC_URL is not configured")

        self.gtfs_dir.mkdir(parents=True, exist_ok=True)
        zip_name = filename or f"GTFSExport-{date.today().isoformat()}.zip"
        zip_path = self.gtfs_dir / zip_name

        if zip_path.exists() and not force:
            print(f"Using existing GTFS file for today: {zip_path}")
            return zip_path

        print(f"Downloading GTFS static feed: {url}")
        async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()

        self._validate_gtfs_zip(resp.content)

        zip_path.write_bytes(resp.content)
        print(f"Saved GTFS static feed to: {zip_path}")
        return zip_path

    async def fetch_static_gtfs(self, url: str) -> bytes:
        """Download and validate the configured GTFS static zip without saving it."""
        if not url:
            raise ValueError("GTFS_STATIC_URL is not configured")

        print(f"Downloading GTFS static feed: {url}")
        async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()

        self._validate_gtfs_zip(resp.content)
        return resp.content

    async def load_static_gtfs(
        self,
        db: Session,
        zip_path: Optional[Union[Path, bytes]] = None,
        replace: bool = False,
    ):
        """Load GTFS zip data into the database."""
        if isinstance(zip_path, bytes):
            print("Loading GTFS feed from memory")
            with zipfile.ZipFile(io.BytesIO(zip_path)) as zip_data:
                with db.begin():
                    if replace:
                        self._clear_static_tables(db)
                    self._load_zip_data(zip_data, db)
            self._verify_static_tables_loaded(db)
            self.static_data_loaded = True
            return

        gtfs_dir = self.gtfs_dir
        if not gtfs_dir.exists() or not gtfs_dir.is_dir():
            raise FileNotFoundError(f"GTFS folder not found: {gtfs_dir}")

        zip_paths = [Path(zip_path)] if zip_path else sorted(gtfs_dir.glob("*.zip"))
        if not zip_paths:
            raise FileNotFoundError(f"No GTFS zip files found in: {gtfs_dir}")

        for index, zip_path in enumerate(zip_paths):
            print(f"Loading GTFS file: {zip_path.name}")
            try:
                with zipfile.ZipFile(zip_path) as zip_data:
                    with db.begin():
                        if replace and index == 0:
                            self._clear_static_tables(db)
                        self._load_zip_data(zip_data, db)
            except Exception:
                db.rollback()
                raise

        self._verify_static_tables_loaded(db)
        self.static_data_loaded = True

    async def refresh_today_gtfs(
        self,
        force_download: bool = False,
        replace: bool = True,
        save_zip: bool = False,
    ):
        """Download today's configured GTFS feed, wipe static tables, and import it."""
        init_db()
        print(f"Refreshing GTFS into database: {_safe_database_target()}")

        zip_data_or_path = (
            await self.download_static_gtfs(
                settings.GTFS_STATIC_URL,
                force=force_download,
            )
            if save_zip
            else await self.fetch_static_gtfs(settings.GTFS_STATIC_URL)
        )

        db = SessionLocal()
        try:
            await self.load_static_gtfs(
                db,
                zip_path=zip_data_or_path,
                replace=replace,
            )
        finally:
            db.close()

        print("Today's GTFS refresh complete.")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_gtfs_zip(content: bytes):
        with zipfile.ZipFile(io.BytesIO(content)) as zip_data:
            required_files = {"stops.txt", "routes.txt", "calendar.txt", "trips.txt", "stop_times.txt"}
            missing = required_files.difference(zip_data.namelist())
            if missing:
                raise ValueError(f"GTFS zip is missing required files: {', '.join(sorted(missing))}")

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

    @staticmethod
    def _clear_static_tables(db: Session):
        """Clear static GTFS tables in dependency order before a fresh import."""
        for model in (StopTime, Shape, Trip, Calendar, Route, Stop):
            db.query(model).delete(synchronize_session=False)

    @staticmethod
    def _verify_static_tables_loaded(db: Session):
        counts = {
            "stops": db.query(Stop).count(),
            "routes": db.query(Route).count(),
            "calendar": db.query(Calendar).count(),
            "trips": db.query(Trip).count(),
            "stop_times": db.query(StopTime).count(),
            "shapes": db.query(Shape).count(),
        }
        print(f"GTFS table counts after import: {counts}")

        required_empty = [
            name for name in ("stops", "routes", "trips", "stop_times")
            if counts[name] == 0
        ]
        if required_empty:
            raise RuntimeError(
                "GTFS import finished but required tables are empty: "
                + ", ".join(required_empty)
            )

    def _load_zip_data(self, zip_data: zipfile.ZipFile, db: Session):
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


def _safe_database_target() -> str:
    url = make_url(settings.DATABASE_URL)
    database = url.database or ""
    host = url.host or "local"
    port = f":{url.port}" if url.port else ""
    return f"{host}{port}/{database}"


async def refresh_today_gtfs(
    force_download: bool = False,
    replace: bool = True,
    save_zip: bool = False,
):
    processor = GTFSProcessor()
    await processor.refresh_today_gtfs(
        force_download=force_download,
        replace=replace,
        save_zip=save_zip,
    )


def main():
    parser = argparse.ArgumentParser(
        description="Download today's GTFS static feed and store it in the database."
    )
    parser.add_argument(
        "--force-download",
        action="store_true",
        help="Download the zip again even if today's file already exists.",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        default=True,
        help="Clear static GTFS tables before importing today's feed. Enabled by default.",
    )
    parser.add_argument(
        "--append",
        action="store_false",
        dest="replace",
        help="Append to existing static GTFS tables instead of clearing them first.",
    )
    parser.add_argument(
        "--save-zip",
        action="store_true",
        help="Save today's GTFS zip under backend/db/GTFS before importing it.",
    )
    args = parser.parse_args()

    asyncio.run(
        refresh_today_gtfs(
            force_download=args.force_download,
            replace=args.replace,
            save_zip=args.save_zip,
        )
    )


if __name__ == "__main__":
    main()

