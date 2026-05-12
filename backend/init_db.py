"""
Database initialization script
Run this to set up the database schema and load initial data
"""
import asyncio
from database import init_db, SessionLocal
from gtfs_processor import GTFSProcessor

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
