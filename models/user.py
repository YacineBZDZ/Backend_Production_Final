# backend/models/user.py
import enum
from sqlalchemy import Column, Integer, String, Boolean, Enum, DateTime, ForeignKey, Date
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.types import Time

#from models.base import engine, Base
from database.base import Base, engine
#Base.metadata.create_all(engine)


class UserRole(enum.Enum):
    ADMIN = "admin"
    DOCTOR = "doctor"
    PATIENT = "patient"

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    phone = Column(String, unique=True, index=True, nullable=True)
    password = Column(String, nullable=False)
    salt = Column(String, nullable=False)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    role = Column(Enum(UserRole), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Privacy policy tracking fields
    privacy_policy_accepted = Column(Boolean, default=False)
    privacy_policy_version = Column(String, nullable=True)
    privacy_policy_accepted_date = Column(DateTime(timezone=True), nullable=True)
    
    # Relationship with other tables based on role
    admin_profile = relationship("AdminProfile", back_populates="user", uselist=False)
    doctor_profile = relationship("DoctorProfile", back_populates="user", uselist=False)
    patient_profile = relationship("PatientProfile", back_populates="user", uselist=False)
    
    # Two-factor authentication
    two_factor_enabled = Column(Boolean, default=False)
    two_factor_secret = Column(String, nullable=True)
    
    # Email verification fields
    pending_email = Column(String, nullable=True)
    email_verification_code = Column(String, nullable=True)
    
    # Phone verification fields
    pending_phone = Column(String, nullable=True)
    phone_verification_code = Column(String, nullable=True)
    
    # Failed login attempts tracking
    login_attempts = Column(Integer, default=0)
    last_login_attempt = Column(DateTime(timezone=True), nullable=True)
    locked_until = Column(DateTime(timezone=True), nullable=True)
    
    # Session data
    refresh_token = Column(String, nullable=True)
    last_login = Column(DateTime(timezone=True), nullable=True)
    last_ip = Column(String, nullable=True)
    
    # Password reset
    reset_token = Column(String, nullable=True)
    reset_token_expires = Column(DateTime(timezone=True), nullable=True)
    
    # Phone carrier
    #phone_carrier = Column(String, nullable=True)  # Store the user's carrier

class AdminProfile(Base):
    __tablename__ = "admin_profiles"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)
    department = Column(String, nullable=True)
    permissions = Column(String, nullable=True)  # JSON string of permissions
    #address = Column(String, nullable=True)  # Added address field
    
    user = relationship("User", back_populates="admin_profile")

class DoctorProfile(Base):
    __tablename__ = "doctor_profiles"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)
    specialty = Column(String, nullable=False)
    license_number = Column(String, nullable=False, unique=True)
    bio = Column(String, nullable=True)
    education = Column(String, nullable=True)
    years_experience = Column(Integer, nullable=True)
    is_verified = Column(Boolean, default=False)  # Add verification status
    verification_notes = Column(String, nullable=True)  # Admin notes about verification
    address = Column(String, nullable=True)  # Address field
    city = Column(String, nullable=True)  # City field
    state = Column(String, nullable=True)  # State/Province field
    postal_code = Column(String, nullable=True)  # Postal code field
    country = Column(String, nullable=True)  # Country field
    
    user = relationship("User", back_populates="doctor_profile")
    availability = relationship("DoctorAvailability", back_populates="doctor")
    appointments = relationship("Appointment", back_populates="doctor")
    
    # Add a direct relationship to FeaturedDoctor
    featured = relationship("FeaturedDoctor", back_populates="doctor", uselist=False)

class PatientProfile(Base):
    __tablename__ = "patient_profiles"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)
    date_of_birth = Column(DateTime, nullable=True)
    gender = Column(String, nullable=True)
    address = Column(String, nullable=True)
    medical_history = Column(String, nullable=True)  # JSON string or text
    insurance_info = Column(String, nullable=True)  # JSON string
    emergency_contact_name = Column(String, nullable=True)
    emergency_contact_phone = Column(String, nullable=True)
    
    user = relationship("User", back_populates="patient_profile")
    appointments = relationship("Appointment", back_populates="patient")

class DoctorAvailability(Base):
    __tablename__ = "doctor_availability"
    
    id = Column(Integer, primary_key=True, index=True)
    doctor_id = Column(Integer, ForeignKey("doctor_profiles.id"))
    availability_date = Column(Date, nullable=False)
    start_time = Column(Time(timezone=False), nullable=False)
    end_time = Column(Time(timezone=False), nullable=False)
    is_available = Column(Boolean, default=True)
    # New optional additional intervals
    start_time2 = Column(Time(timezone=False), nullable=True)
    end_time2 = Column(Time(timezone=False), nullable=True)
    start_time3 = Column(Time(timezone=False), nullable=True)
    end_time3 = Column(Time(timezone=False), nullable=True)
    
    doctor = relationship("DoctorProfile", back_populates="availability")

class Appointment(Base):
    __tablename__ = "appointments"
    
    id = Column(Integer, primary_key=True, index=True)
    doctor_id = Column(Integer, ForeignKey("doctor_profiles.id"))
    patient_id = Column(Integer, ForeignKey("patient_profiles.id"))
    start_time = Column(Time, nullable=False)         # Changed from DateTime to Time
    end_time = Column(Time, nullable=False)           # Changed from DateTime to Time
    appointment_date = Column(Date, nullable=False)   # Remains separate
    status = Column(String, nullable=False)           # "scheduled", etc.
    reason = Column(String, nullable=True)
    notes = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    is_updated = Column(Boolean, default=False)        # New field to track updates
    update_date = Column(DateTime(timezone=True), nullable=True)  # New field to store update date
    
    doctor = relationship("DoctorProfile", back_populates="appointments")
    patient = relationship("PatientProfile", back_populates="appointments")

class FeaturedDoctor(Base):
    __tablename__ = "featured_doctors"
    id = Column(Integer, primary_key=True, index=True)
    doctor_id = Column(Integer, ForeignKey("doctor_profiles.id"), unique=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=True)  # Add direct user reference
    start_date = Column(DateTime, nullable=True)
    end_date = Column(DateTime, nullable=True)
    feature_enabled = Column(Boolean, default=False)

    # Improve the relationship with better back_populates
    doctor = relationship("DoctorProfile", back_populates="featured", lazy="joined")
    # Direct relationship to User
    user = relationship("User", foreign_keys=[user_id], lazy="joined")
    
    # Helper property to access user if only doctor is available
    @property
    def get_user(self):
        if self.user:
            return self.user
        elif self.doctor and self.doctor.user:
            return self.doctor.user
        return None

class PrivacyPolicy(Base):
    """Model to track different versions of privacy policies"""
    __tablename__ = "privacy_policies"
    
    id = Column(Integer, primary_key=True, index=True)
    version = Column(String, nullable=False, unique=True)
    content = Column(String, nullable=False)  # The full policy text
    summary = Column(String, nullable=True)   # Optional summary of changes
    effective_date = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    is_active = Column(Boolean, default=True)
    
    # Relationship with accepted records
    acceptance_records = relationship("UserPrivacyAcceptance", back_populates="policy")

class UserPrivacyAcceptance(Base):
    """Model to track each time a user accepts a privacy policy"""
    __tablename__ = "user_privacy_acceptances"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    policy_id = Column(Integer, ForeignKey("privacy_policies.id"), nullable=False)
    accepted_at = Column(DateTime(timezone=True), server_default=func.now())
    ip_address = Column(String, nullable=True)  # Store IP for audit purposes
    user_agent = Column(String, nullable=True)  # Store browser/device info
    
    # Define relationships
    user = relationship("User")
    policy = relationship("PrivacyPolicy", back_populates="acceptance_records")

class HomeDisplaySettings(Base):
    """Settings for the home page display"""
    __tablename__ = "home_display_settings"
    
    id = Column(Integer, primary_key=True, index=True)
    show_verified_doctors = Column(Boolean, default=False)
    max_doctors = Column(Integer, default=10)
    
    # Add a timestamp for when settings were last updated
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

Base.metadata.create_all(engine)