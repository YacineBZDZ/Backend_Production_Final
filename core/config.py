import os
from pydantic_settings import BaseSettings
from dotenv import load_dotenv
from functools import lru_cache
from typing import List

# Load .env file
load_dotenv()

class Settings(BaseSettings):
    # Database settings
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://tabibmeet_user:tHKThyPS0pp549rxnEuKbCs8fa6wiqG4@dpg-cvscbteuk2gs739rua10-a.oregon-postgres.render.com/tabibmeet")
    
    # Application settings
    PROJECT_NAME: str = "TabibMeet API"
    API_VERSION: str = "v1"
    DEBUG: bool = os.getenv("DEBUG", "False").lower() in ("true", "1", "t")
    
    # Security settings
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your-secret-key-here")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
    ALGORITHM: str = "HS256"
    
    # JWT Settings
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "61e16bf371dc9f01c48fc89d...9d0586932ab33793240680a")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))
    
    # Email settings
    EMAIL_HOST: str = os.getenv("EMAIL_HOST", "smtp.gmail.com")
    EMAIL_PORT: int = int(os.getenv("EMAIL_PORT", "587"))
    EMAIL_USER: str = os.getenv("EMAIL_USER", "adminyacine@tabibmeet.com")
    EMAIL_PASSWORD: str = os.getenv("EMAIL_PASSWORD", "tylqttmkfronojit")
    EMAIL_FROM: str = os.getenv("EMAIL_FROM", "jakmca3@gmail.com")
    EMAIL_USE_TLS: bool = os.getenv("EMAIL_USE_TLS", "True").lower() in ("true", "1", "t")
    ADMIN_EMAIL: str = os.getenv("ADMIN_EMAIL", "admin@tabibmeet.com")  # Added admin email
    
    # Frontend URL
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://tabibmeet.com")
    
    # CORS settings
    ALLOWED_ORIGINS: List[str] = ["*"]  # In production, specify your domains
    
    model_config = {
        "env_file": ".env",
        "case_sensitive": True,
        "extra": "ignore"  # Add this to ignore extra fields
    }

@lru_cache()
def get_settings() -> Settings:
    """Return cached settings"""
    return Settings()
