"""
Database initialization script
Run this to set up the database schema and load initial data
"""
import asyncio
from database import init_db, SessionLocal
from gtfs_processor import GTFSProcessor

async def initialize_database():
    """Initialize database and load GTFS data"""
    print("Initializing database...")
    
    # Create tables
    init_db()
    print("✅ Database tables created")
    
    # Load GTFS data
    db = SessionLocal()
    try:
        processor = GTFSProcessor()
        await processor.load_static_gtfs(db)
        print("✅ GTFS static data loaded")
    except Exception as e:
        print(f"❌ Error loading GTFS data: {e}")
        print("You can load it later by running this script again")
    finally:
        db.close()
    
    print("🎉 Database initialization complete!")

if __name__ == "__main__":
    asyncio.run(initialize_database())
