from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    PROJECT_NAME: str = "Dynamic Safety Heatmap API"
    API_V1_STR: str = "/api/v1"
    
    # Database
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "safety_heatmap"
    POSTGRES_PORT: str = "5432"

    @property
    def SQLALCHEMY_DATABASE_URI(self) -> str:
        return f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    # Reddit — uses public JSON API (no key required)
    # REDDIT_CLIENT_ID: Optional[str] = None
    # REDDIT_CLIENT_SECRET: Optional[str] = None
    
    # YouTube API
    YOUTUBE_API_KEY: Optional[str] = None
    
    # Apify API
    APIFY_API_TOKEN: Optional[str] = None
    
    # Google Maps API
    GOOGLE_MAPS_API_KEY: Optional[str] = None

    class Config:
        env_file = ".env"

settings = Settings()
