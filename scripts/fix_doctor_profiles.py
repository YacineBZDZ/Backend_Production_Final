#!/usr/bin/env python
"""
Database repair script to fix doctor profiles with missing user_id.

This script looks for doctor profiles with NULL user_id values and either:
1. Links them to existing users where possible
2. Creates placeholder user accounts and links them if no matching user exists

Usage:
python fix_doctor_profiles.py
"""

import sys
import os
import logging
from datetime import datetime
import argparse
import time

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Add the project root to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import after adding to path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, joinedload
from sqlalchemy.exc import OperationalError
from passlib.context import CryptContext

# Import models via absolute imports to avoid circular imports
from models.user import User, DoctorProfile, UserRole

# Set up password context for creating placeholder users if needed
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_session_with_retry(max_retries=5, delay=5, ssl_mode="prefer"):
    """Create a database session with retry logic and custom SSL mode"""
    from core.config import get_settings
    
    settings = get_settings()
    retry_count = 0
    last_error = None
    
    while retry_count < max_retries:
        try:
            logger.info(f"Connecting to database (attempt {retry_count + 1}/{max_retries})...")
            
            # Get database URL from settings
            db_url = settings.get_database_url()
            
            # Add SSL mode parameter if needed
            if "postgresql" in db_url:
                # Add sslmode parameter if not present
                if "sslmode" not in db_url:
                    separator = "&" if "?" in db_url else "?"
                    db_url = f"{db_url}{separator}sslmode={ssl_mode}"
                logger.info(f"Using SSL mode: {ssl_mode}")
            
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
            SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
            session = SessionLocal()
            
            # Test the connection
            session.execute("SELECT 1")
            logger.info("Database connection successful")
            
            return session
            
        except OperationalError as e:
            retry_count += 1
            last_error = e
            logger.warning(f"Database connection failed: {str(e)}")
            
            if retry_count < max_retries:
                logger.info(f"Retrying in {delay} seconds...")
                time.sleep(delay)
                
                # Try different SSL mode on retry
                if "SSL connection has been closed" in str(e) or "sslmode" in str(e):
                    if ssl_mode == "prefer":
                        ssl_mode = "require"
                    elif ssl_mode == "require":
                        ssl_mode = "verify-ca"
                    elif ssl_mode == "verify-ca":
                        ssl_mode = "verify-full"
                    else:
                        ssl_mode = "disable"  # Last resort
                    
                    logger.info(f"Trying different SSL mode: {ssl_mode}")
            else:
                logger.error(f"Max retries exceeded. Last error: {str(last_error)}")
                raise
        except Exception as e:
            logger.error(f"Unexpected error connecting to database: {str(e)}")
            raise

def fix_doctor_profiles(args):
    """Fix doctor profiles with missing user_id"""
    try:
        # Get session with retry logic
        db = get_session_with_retry(ssl_mode=args.ssl_mode)
        
        try:
            # Find all doctor profiles with null user_id
            broken_profiles = db.query(DoctorProfile).filter(
                DoctorProfile.user_id.is_(None)
            ).all()
            
            if not broken_profiles:
                logger.info("No doctor profiles with missing user_id found.")
                return
            
            logger.info(f"Found {len(broken_profiles)} doctor profiles with missing user_id")
            
            for profile in broken_profiles:
                logger.info(f"Processing doctor profile id={profile.id}")
                
                # Try to find an existing user that could be linked to this doctor
                possible_user = db.query(User).filter(
                    (User.role == UserRole.DOCTOR) &
                    (User.email.ilike(f"%doctor{profile.id}%") | 
                     User.email.ilike(f"%dr{profile.id}%"))
                ).first()
                
                if possible_user:
                    logger.info(f"  Found potential matching user id={possible_user.id}, email={possible_user.email}")
                    
                    # Check if this user is already linked to another doctor profile
                    existing_profile = db.query(DoctorProfile).filter(
                        DoctorProfile.user_id == possible_user.id
                    ).first()
                    
                    if existing_profile and existing_profile.id != profile.id:
                        logger.warning(f"  Warning: User already linked to another doctor profile id={existing_profile.id}")
                        # Create a new placeholder user instead
                        new_user = create_placeholder_user(db, profile)
                        profile.user_id = new_user.id
                    else:
                        # Link this user to the doctor profile
                        profile.user_id = possible_user.id
                        logger.info(f"  Linked doctor profile to existing user id={possible_user.id}")
                else:
                    # No matching user found, create a placeholder user
                    new_user = create_placeholder_user(db, profile)
                    profile.user_id = new_user.id
                
                db.commit()
                logger.info(f"  Updated doctor profile id={profile.id} with user_id={profile.user_id}")
            
            logger.info("\nDoctor profile repair completed successfully!")
            
        except Exception as e:
            db.rollback()
            logger.error(f"Error fixing doctor profiles: {str(e)}")
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Failed to connect to database: {str(e)}")

def create_placeholder_user(db, profile):
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
        password=hashed_password,  # Field name might be 'password' instead of 'hashed_password'
        salt=salt,                 # Add salt if your model uses it
        first_name=first_name,
        last_name=last_name,
        is_active=True,
        role=UserRole.DOCTOR,
        phone=profile.phone if hasattr(profile, 'phone') else None,
        created_at=datetime.now()
    )
    
    db.add(new_user)
    db.flush()  # Get the ID without committing
    
    logger.info(f"  Created placeholder user id={new_user.id}, email={email}")
    return new_user

def parse_args():
    parser = argparse.ArgumentParser(description='Fix doctor profiles with missing user_id')
    parser.add_argument('--ssl-mode', choices=['prefer', 'require', 'verify-ca', 'verify-full', 'disable'],
                       default='prefer', help='PostgreSQL SSL mode')
    return parser.parse_args()

if __name__ == "__main__":
    logger.info("Running doctor profile repair script...")
    args = parse_args()
    fix_doctor_profiles(args)