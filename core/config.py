import os
from pydantic_settings import BaseSettings
from dotenv import load_dotenv
from functools import lru_cache
from typing import List, Dict

# Load environment variables from .env file
load_dotenv(override=True)

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
    
    # Email settings - Required - Explicitly set default values for debugging
    EMAIL_HOST: str = os.environ.get("EMAIL_HOST", "mail.privateemail.com")
    EMAIL_PORT: int = int(os.environ.get("EMAIL_PORT", "587"))
    EMAIL_USER: str = os.environ.get("EMAIL_USER", "no-reply@tabibmeet.com")
    EMAIL_PASSWORD: str = os.environ.get("EMAIL_PASSWORD", "")
    EMAIL_FROM: str = os.environ.get("EMAIL_FROM", "no-reply@tabibmeet.com")
    EMAIL_USE_TLS: bool = os.environ.get("EMAIL_USE_TLS", "True").lower() in ("true", "1", "t")
    EMAIL_USE_SSL: bool = os.environ.get("EMAIL_USE_SSL", "False").lower() in ("true", "1", "t")
    ADMIN_EMAIL: str = os.environ.get("ADMIN_EMAIL", "adminyacine@tabibmeet.com")
    
    # Email signature settings
    EMAIL_SIGNATURE_ENABLED: bool = os.environ.get("EMAIL_SIGNATURE_ENABLED", "False").lower() in ("true", "1", "t")
    USE_PROVIDER_SIGNATURE: bool = os.environ.get("USE_PROVIDER_SIGNATURE", "True").lower() in ("true", "1", "t")
    
    # CORS settings
    ALLOWED_ORIGINS: List[str] = os.environ.get("ALLOWED_ORIGINS", "*").split(",")
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"
        env_file_encoding = 'utf-8'
        env_nested_delimiter = '__'

@lru_cache()
def get_settings() -> Settings:
    """Return cached settings for performance."""
    return Settings()
