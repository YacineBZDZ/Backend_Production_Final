import os
from pydantic_settings import BaseSettings
from dotenv import load_dotenv
from functools import lru_cache
from typing import List

# Load environment variables from .env file (only in development)
# In production (Render), environment variables are set in the dashboard
# This will have no effect when running on Render since .env file won't exist
load_dotenv()

class Settings(BaseSettings):
    # Application settings
    PROJECT_NAME: str = "TabibMeet API"
    API_VERSION: str = "v1"
    DEBUG: bool = os.environ.get("DEBUG", "False").lower() in ("true", "1", "t")
    
    # Database settings - Required
    DATABASE_URL: str = os.environ.get("DATABASE_URL")
    
    # Security settings - Required
    SECRET_KEY: str = os.environ.get("SECRET_KEY")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))
    ALGORITHM: str = "HS256"
    
    # JWT Settings - Required
    JWT_SECRET_KEY: str = os.environ.get("JWT_SECRET_KEY")
    JWT_ALGORITHM: str = os.environ.get("JWT_ALGORITHM", "HS256")
    REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.environ.get("REFRESH_TOKEN_EXPIRE_DAYS", "7"))
    
    # Email settings - Required
    EMAIL_HOST: str = os.environ.get("EMAIL_HOST")
    EMAIL_PORT: int = int(os.environ.get("EMAIL_PORT"))
    EMAIL_USER: str = os.environ.get("EMAIL_USER")
    EMAIL_PASSWORD: str = os.environ.get("EMAIL_PASSWORD")
    EMAIL_FROM: str = os.environ.get("EMAIL_FROM")
    EMAIL_USE_TLS: bool = os.environ.get("EMAIL_USE_TLS", "True").lower() in ("true", "1", "t")
    ADMIN_EMAIL: str = os.environ.get("ADMIN_EMAIL")
    
    # Frontend URL - Required
    FRONTEND_URL: str = os.environ.get("FRONTEND_URL")
    
    # CORS settings
    ALLOWED_ORIGINS: List[str] = os.environ.get("ALLOWED_ORIGINS", "*").split(",")
    
    # Validate required fields
    @classmethod
    def validate_settings(cls, settings):
        required_fields = [
            "DATABASE_URL", "SECRET_KEY", "JWT_SECRET_KEY", 
            "EMAIL_HOST", "EMAIL_PORT", "EMAIL_USER", 
            "EMAIL_PASSWORD", "EMAIL_FROM", "ADMIN_EMAIL",
            "FRONTEND_URL"
        ]
        
        missing = []
        for field in required_fields:
            if not getattr(settings, field, None):
                missing.append(field)
                
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")
        
        return settings
    
    class Config:
        # These settings only apply when loading from .env file
        # Render will use system environment variables directly
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"

@lru_cache()
def get_settings() -> Settings:
    """Return cached settings for performance."""
    settings = Settings()
    settings = Settings.validate_settings(settings)
    return settings
