# database/base.py

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import text
from core.config import get_settings

# Get settings
settings = get_settings()

# Use database URL from settings
SQLALCHEMY_DATABASE_URL = settings.DATABASE_URL

# Create the SQLAlchemy engine which will manage connections to your PostgreSQL database.
engine = create_engine(SQLALCHEMY_DATABASE_URL)

# Test connection and print version
with engine.connect() as connection:
    result = connection.execute(text("SELECT version();"))
    version = result.fetchone()
    print("PostgreSQL version:", version[0])

# Create a configured "SessionLocal" class for session creation.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)

# Create a Base class from which all of your ORM models should inherit.
Base = declarative_base()
