from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql://octranspo:octranspo@localhost:5432/octranspo_live"
    
    # OC Transpo API (you'll need to get an API key from OC Transpo)
    OC_TRANSPO_APP_ID: Optional[str] = None
    OC_TRANSPO_API_KEY: Optional[str] = None
    
    # GTFS Schedules
    # GTFS static data Downloads GTFSEXPORT.zip
    GTFS_STATIC_URL: str = "https://oct-gtfs-emasagcnfmcgeham.z01.azurefd.net/public-access/GTFSExport.zip"
    
    
    # ML Service
    ML_SERVICE_URL: str = "http://localhost:8001"
    
    # App Settings
    DEBUG: bool = True
    CACHE_TTL: int = 300  # 5 minutes
    
    class Config:
        env_file = ".env"

settings = Settings()
