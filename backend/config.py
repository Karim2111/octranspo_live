from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str

    # GTFS static feed
    GTFS_STATIC_URL: str

    # GTFS-RT real-time feeds
    GTFS_RT_VEHICLE_POSITIONS_URL: str = "https://nextrip-public-api.azure-api.net/octranspo/gtfs-rt-vp/beta/v1/VehiclePositions"
    GTFS_PRIMARY_KEY: Optional[str] = None

    # App
    DEBUG: bool = False

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

settings = Settings()
