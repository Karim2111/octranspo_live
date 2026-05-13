"""
Database initialization script
Run this to set up the database schema and load initial data
"""
import asyncio
import os
import sys

ROOT = os.path.dirname(os.path.dirname(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from db.database import init_db, SessionLocal
from db.gtfs_processor import GTFSProcessor

async def initialize_database():
    """Initialize database and load GTFS data"""
    # Create tables
    init_db()

    # Load GTFS data
    db = SessionLocal()
    try:
        processor = GTFSProcessor()
        await processor.load_static_gtfs(db)
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(initialize_database())
