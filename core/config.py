import os
from pydantic_settings import BaseSettings
from dotenv import load_dotenv
from functools import lru_cache
from typing import List, Dict, Optional

# Load environment variables from .env file
load_dotenv(override=True)

class Settings(BaseSettings):
    # Application settings
    PROJECT_NAME: str = "TabibMeet API"
    API_VERSION: str = "v1"
    DEBUG: bool = os.environ.get("DEBUG", "False").lower() in ("true", "1", "t")
    
    # Database settings - Required
    DATABASE_URL: Optional[str] = os.environ.get("DATABASE_URL")
    
    # Google Cloud SQL settings
    DB_INSTANCE: Optional[str] = os.environ.get("DB_INSTANCE")  # Format: project-id:region:instance-name
    DB_NAME: Optional[str] = os.environ.get("DB_NAME")
    DB_USER: Optional[str] = os.environ.get("DB_USER")
    DB_PASSWORD: Optional[str] = os.environ.get("DB_PASSWORD")
    DB_HOST: Optional[str] = os.environ.get("DB_HOST")  # Can be IP or unix socket path
    DB_PORT: Optional[str] = os.environ.get("DB_PORT", "5432")
    DB_USE_PROXY: bool = os.environ.get("DB_USE_PROXY", "False").lower() in ("true", "1", "t")
    DB_SSL_MODE: str = os.environ.get("DB_SSL_MODE", "prefer")
    
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
    
    # Host validation settings
    ALLOWED_HOSTS: List[str] = os.environ.get("ALLOWED_HOSTS", "*").split(",")
    
    # Support email for security notifications
    SUPPORT_EMAIL: str = os.environ.get("SUPPORT_EMAIL", "support@tabibmeet.com")
    
    def get_database_url(self) -> str:
        """
        Constructs the database URL based on available settings.
        Prioritizes DATABASE_URL if provided, otherwise builds connection string
        from individual components.
        """
        # If full DATABASE_URL is provided, use it
        if self.DATABASE_URL:
            # Check if it's a Google Cloud SQL identifier format
            if self.DATABASE_URL.count(':') == 2 and '/' not in self.DATABASE_URL:
                # It looks like a Cloud SQL instance identifier
                if self.DB_USER and self.DB_PASSWORD and self.DB_NAME:
                    if self.DB_USE_PROXY:
                        # Use localhost when Cloud SQL Proxy is in use
                        return f"postgresql://{self.DB_USER}:{self.DB_PASSWORD}@localhost:{self.DB_PORT}/{self.DB_NAME}"
                    # Create URL using instance IP if available, otherwise assume proxy
                    elif self.DB_HOST:
                        return f"postgresql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
                    else:
                        return f"postgresql://{self.DB_USER}:{self.DB_PASSWORD}@localhost:{self.DB_PORT}/{self.DB_NAME}"
                else:
                    raise ValueError("DB_USER, DB_PASSWORD, and DB_NAME must be provided when using a Cloud SQL instance")
            # Regular URL format
            return self.DATABASE_URL
        
        # If we have Google Cloud SQL instance info and individual components
        if self.DB_INSTANCE:
            # For Cloud SQL with public IP connection
            if self.DB_USER and self.DB_PASSWORD and self.DB_NAME:
                # Get project ID, region, and instance from DB_INSTANCE
                parts = self.DB_INSTANCE.split(":")
                if len(parts) == 3:  # Ensure proper format
                    project_id, region, instance = parts
                    
                    # If using Cloud SQL Proxy
                    if self.DB_USE_PROXY:
                        return f"postgresql://{self.DB_USER}:{self.DB_PASSWORD}@localhost:{self.DB_PORT}/{self.DB_NAME}"
                    
                    # Create direct connection if host is available
                    if self.DB_HOST:
                        # Check if SSL mode is specified
                        ssl_part = f"?sslmode={self.DB_SSL_MODE}" if self.DB_SSL_MODE else ""
                        return f"postgresql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}{ssl_part}"
                    # Fall back to proxy
                    else:
                        return f"postgresql://{self.DB_USER}:{self.DB_PASSWORD}@localhost:{self.DB_PORT}/{self.DB_NAME}"
            
        # Build connection from components as fallback
        if self.DB_HOST and self.DB_USER and self.DB_PASSWORD and self.DB_NAME:
            ssl_part = f"?sslmode={self.DB_SSL_MODE}" if self.DB_SSL_MODE else ""
            return f"postgresql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}{ssl_part}"
        
        # Fallback to SQLite for development if no credentials
        if self.DEBUG:
            return "sqlite:///./test.db"
        
        # No valid configuration found
        raise ValueError("No valid database configuration provided. Please set DATABASE_URL or individual DB_* settings.")
    
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
