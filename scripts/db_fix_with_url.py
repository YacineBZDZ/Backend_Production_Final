#!/usr/bin/env python3
"""
Database repair script with direct URL input support.
This script avoids environment variable issues by allowing direct DB URL input.
"""

import sys
import os
import logging
import time
import urllib.parse
from datetime import datetime
import argparse

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

def main():
    parser = argparse.ArgumentParser(description='Fix doctor profiles with direct database URL')
    parser.add_argument('--db-url', required=True, help='Full database URL including credentials')
    parser.add_argument('--ssl-mode', default='disable', choices=['prefer', 'require', 'verify-ca', 'verify-full', 'disable'],
                        help='PostgreSQL SSL mode')
    args = parser.parse_args()
    
    # Import here to avoid circular imports
    from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, ForeignKey, text
    from sqlalchemy.orm import sessionmaker, relationship, declarative_base
    from sqlalchemy.exc import OperationalError
    import enum
    from passlib.context import CryptContext
    
    # Set up password context
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    
    # Define minimal model classes
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
    
    # Process the database URL
    db_url = args.db_url
    
    # Add SSL mode if not already in URL
    if "postgresql" in db_url and "sslmode" not in db_url:
        separator = "&" if "?" in db_url else "?"
        db_url = f"{db_url}{separator}sslmode={args.ssl_mode}"
    
    # Mask password for logging
    masked_url = db_url
    if '@' in db_url:
        parts = db_url.split('@')
        protocol_user = parts[0].split(':')
        if len(protocol_user) > 2:  # Has password
            masked_url = f"{protocol_user[0]}:{protocol_user[1]}:******@{parts[1]}"
    
    logger.info(f"Connecting to database with URL: {masked_url}")
    
    try:
        # Create engine with appropriate options
        engine_kwargs = {
            "pool_pre_ping": True,
            "pool_recycle": 1800,
            "connect_args": {"connect_timeout": 10}
        }
        
        engine = create_engine(db_url, **engine_kwargs)
        Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        session = Session()
        
        # Test connection
        try:
            logger.info("Testing connection...")
            session.execute(text("SELECT 1"))
            logger.info("Connection successful!")
        except Exception as e:
            logger.error(f"Connection test failed: {str(e)}")
            return
        
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
                    new_user = create_placeholder_user(session, profile, pwd_context, User, UserRole)
                    profile.user_id = new_user.id
                else:
                    # Link this user to the doctor profile
                    profile.user_id = possible_user.id
                    logger.info(f"  Linked doctor profile to existing user id={possible_user.id}")
            else:
                # No matching user found, create a placeholder user
                new_user = create_placeholder_user(session, profile, pwd_context, User, UserRole)
                profile.user_id = new_user.id
            
            session.commit()
            logger.info(f"  Updated doctor profile id={profile.id} with user_id={profile.user_id}")
        
        logger.info("\nDoctor profile repair completed successfully!")
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        sys.exit(1)

def create_placeholder_user(session, profile, pwd_context, User, UserRole):
    """Create a placeholder user for a doctor profile with missing user_id"""
    email = f"doctor{profile.id}@placeholder.com"
    hashed_password = pwd_context.hash("Placeholder123!")
    salt = os.urandom(16).hex()
    
    # Create the new user
    new_user = User(
        email=email,
        password=hashed_password,
        salt=salt,
        first_name=f"Doctor{profile.id}",
        last_name="Placeholder",
        is_active=True,
        role=UserRole.DOCTOR.value,
        phone=None,
        created_at=datetime.now()
    )
    
    session.add(new_user)
    session.flush()
    logger.info(f"  Created placeholder user id={new_user.id}, email={email}")
    return new_user

if __name__ == "__main__":
    main()