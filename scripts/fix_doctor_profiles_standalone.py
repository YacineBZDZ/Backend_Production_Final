#!/usr/bin/env python
"""
Standalone doctor profile repair script that bypasses automatic database connections.

This script fixes doctor profiles with missing user_id by:
1. Linking them to existing users where possible
2. Creating placeholder users when no matching user exists

Usage:
python fix_doctor_profiles_standalone.py [--ssl-mode=disable]
"""

import sys
import os
import logging
from datetime import datetime
import argparse
import time
import importlib

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Add the project root to the path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
sys.path.append(project_root)

# Import specific database connection components without triggering model imports
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, ForeignKey, Enum, text
from sqlalchemy.orm import sessionmaker, relationship, declarative_base
from sqlalchemy.exc import OperationalError
from passlib.context import CryptContext
import enum

# Set up password context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_db_url():
    """Get the database URL from settings without importing the full models"""
    # Import config directly to avoid circular imports
    sys.path.insert(0, os.path.join(project_root, 'core'))
    import config
    settings = config.get_settings()
    return settings.get_database_url()

def create_safe_session(db_url, ssl_mode="prefer", max_retries=5, delay=5):
    """Create a database session with custom SSL options and retry logic"""
    retry_count = 0
    last_error = None
    
    while retry_count < max_retries:
        try:
            logger.info(f"Connecting to database (attempt {retry_count + 1}/{max_retries})...")
            
            # Add SSL mode parameter if needed
            if "postgresql" in db_url and "sslmode" not in db_url:
                separator = "&" if "?" in db_url else "?"
                db_url = f"{db_url}{separator}sslmode={ssl_mode}"
            
            # Mask password in logs
            if '@' in db_url:
                parts = db_url.split('@')
                auth_part = parts[0].split(':')[0]
                host_part = parts[1]
                logger.info(f"Using database connection: {auth_part}:***@{host_part}")
                if ssl_mode:
                    logger.info(f"SSL mode: {ssl_mode}")
            
            # Create engine with appropriate connection parameters
            engine_kwargs = {
                "pool_pre_ping": True,
                "pool_recycle": 1800,
                "connect_args": {
                    "connect_timeout": 10,
                }
            }
            
            # Create engine and session
            engine = create_engine(db_url, **engine_kwargs)
            Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
            session = Session()
            
            # Test the connection using text() function for SQLAlchemy 2.0 compatibility
            session.execute(text("SELECT 1"))
            logger.info("Database connection successful")
            return session
            
        except OperationalError as e:
            retry_count += 1
            last_error = e
            logger.warning(f"Database connection failed: {str(e)}")
            
            if retry_count < max_retries:
                logger.info(f"Retrying in {delay} seconds...")
                time.sleep(delay)
                
                # Try different SSL mode on retry if SSL-related error
                if "SSL connection has been closed" in str(e) or "sslmode" in str(e):
                    if ssl_mode == "prefer":
                        ssl_mode = "require"
                    elif ssl_mode == "require":
                        ssl_mode = "verify-ca"
                    elif ssl_mode == "verify-ca":
                        ssl_mode = "verify-full"
                    elif ssl_mode == "verify-full":
                        ssl_mode = "disable"
                    else:
                        ssl_mode = None  # Try with no SSL mode
                    
                    logger.info(f"Trying different SSL mode: {ssl_mode or 'None'}")
            else:
                logger.error(f"Max retries exceeded. Last error: {str(e)}")
                raise
        except Exception as e:
            logger.error(f"Unexpected error connecting to database: {str(e)}")
            raise

# Define minimal model classes without importing the actual models
Base = declarative_base()

class UserRole(str, enum.Enum):
    ADMIN = "admin"
    DOCTOR = "doctor"
    PATIENT = "patient"

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    password = Column(String)
    salt = Column(String)
    first_name = Column(String)
    last_name = Column(String)
    phone = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    role = Column(String)
    created_at = Column(DateTime)
    doctor_profile = relationship("DoctorProfile", back_populates="user", uselist=False)

class DoctorProfile(Base):
    __tablename__ = "doctor_profiles"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    specialty = Column(String)
    license_number = Column(String)
    is_verified = Column(Boolean, default=False)
    verification_notes = Column(String, nullable=True)
    user = relationship("User", back_populates="doctor_profile")

def fix_doctor_profiles(session):
    """Fix doctor profiles with missing user_id"""
    try:
        # Find all doctor profiles with null user_id
        broken_profiles = session.query(DoctorProfile).filter(
            DoctorProfile.user_id.is_(None)
        ).all()
        
        if not broken_profiles:
            logger.info("No doctor profiles with missing user_id found.")
            return
        
        logger.info(f"Found {len(broken_profiles)} doctor profiles with missing user_id")
        
        for profile in broken_profiles:
            logger.info(f"Processing doctor profile id={profile.id}")
            
            # Try to find an existing user that could be linked to this doctor
            possible_user = session.query(User).filter(
                User.role == UserRole.DOCTOR.value,
                (User.email.ilike(f"%doctor{profile.id}%") | 
                 User.email.ilike(f"%dr{profile.id}%"))
            ).first()
            
            if possible_user:
                logger.info(f"  Found potential matching user id={possible_user.id}, email={possible_user.email}")
                
                # Check if this user is already linked to another doctor profile
                existing_profile = session.query(DoctorProfile).filter(
                    DoctorProfile.user_id == possible_user.id,
                    DoctorProfile.id != profile.id
                ).first()
                
                if existing_profile:
                    logger.warning(f"  Warning: User already linked to another doctor profile id={existing_profile.id}")
                    # Create a new placeholder user instead
                    new_user = create_placeholder_user(session, profile)
                    profile.user_id = new_user.id
                else:
                    # Link this user to the doctor profile
                    profile.user_id = possible_user.id
                    logger.info(f"  Linked doctor profile to existing user id={possible_user.id}")
            else:
                # No matching user found, create a placeholder user
                new_user = create_placeholder_user(session, profile)
                profile.user_id = new_user.id
            
            session.commit()
            logger.info(f"  Updated doctor profile id={profile.id} with user_id={profile.user_id}")
        
        logger.info("\nDoctor profile repair completed successfully!")
    except Exception as e:
        session.rollback()
        logger.error(f"Error fixing doctor profiles: {str(e)}")
        raise

def create_placeholder_user(session, profile):
    """Create a placeholder user for a doctor profile with missing user_id"""
    email = f"doctor{profile.id}@placeholder.com"
    hashed_password = pwd_context.hash("Placeholder123!")
    salt = os.urandom(16).hex()  # Generate salt for password
    
    # Create a random name based on the profile ID
    first_name = f"Doctor{profile.id}"
    last_name = "Placeholder"
    
    # Create the new user
    new_user = User(
        email=email,
        password=hashed_password,
        salt=salt,
        first_name=first_name,
        last_name=last_name,
        is_active=True,
        role=UserRole.DOCTOR.value,
        phone=None,  # No phone info in the minimal model
        created_at=datetime.now()
    )
    
    session.add(new_user)
    session.flush()  # Get the ID without committing
    
    logger.info(f"  Created placeholder user id={new_user.id}, email={email}")
    return new_user

def main():
    """Main entry point for the script"""
    parser = argparse.ArgumentParser(description='Fix doctor profiles with missing user_id')
    parser.add_argument('--ssl-mode', choices=['prefer', 'require', 'verify-ca', 'verify-full', 'disable', 'none'],
                       default='disable', help='PostgreSQL SSL mode')
    args = parser.parse_args()
    
    ssl_mode = None if args.ssl_mode == 'none' else args.ssl_mode
    
    logger.info("Running doctor profile repair script...")
    logger.info(f"Using SSL mode: {ssl_mode or 'None'}")
    
    try:
        # Get database URL without importing models
        db_url = get_db_url()
        
        # Create session with custom SSL settings
        session = create_safe_session(db_url, ssl_mode=ssl_mode)
        
        try:
            # Fix doctor profiles
            fix_doctor_profiles(session)
        finally:
            session.close()
    except Exception as e:
        logger.error(f"Script failed: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()