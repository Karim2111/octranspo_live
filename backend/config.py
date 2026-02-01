from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql://octranspo:octranspo@localhost:5432/octranspo_live"
    
    # OC Transpo API (you'll need to get an API key from OC Transpo)
    OC_TRANSPO_APP_ID: Optional[str] = None
    OC_TRANSPO_API_KEY: Optional[str] = None
    
    # GTFS URLs
    GTFS_STATIC_URL: str = "https://www.octranspo.com/files/google_transit.zip"
    GTFS_RT_VEHICLE_URL: str = "https://gtfs.octranspo.com/gtfs-rt/vehiclepositions"
    GTFS_RT_TRIP_URL: str = "https://gtfs.octranspo.com/gtfs-rt/tripupdates"
    
    # ML Service
    ML_SERVICE_URL: str = "http://localhost:8001"
    
    # App Settings
    DEBUG: bool = True
    CACHE_TTL: int = 300  # 5 minutes
    
    class Config:
        env_file = ".env"

settings = Settings()
