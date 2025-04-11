from sqlalchemy import create_engine
from database.base import Base
from core.config import get_settings
import models.user  # Import all models to ensure they are registered with Base

# Drop and recreate all tables
if __name__ == "__main__":
    settings = get_settings()
    engine = create_engine(settings.DATABASE_URL)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    print("Database tables dropped and recreated with new fields.")
