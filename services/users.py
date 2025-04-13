# backend/api/users.py
from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from pydantic import BaseModel, EmailStr
import random  # For generating a numeric verification code
import os
import smtplib
from email.message import EmailMessage
from sqlalchemy import or_
from core.config import get_settings
from database.session import get_db
from models.user import User, UserRole, DoctorProfile, AdminProfile, PatientProfile, FeaturedDoctor, HomeDisplaySettings
from models.authentication import get_current_active_user

from models.authentication import AuthHandler
import secrets
from datetime import datetime

router = APIRouter(tags=["Users"])
public_router = APIRouter(tags=["Public Users"])

# --- Pydantic models for request/response ---

class DoctorProfileResponse(BaseModel):
    doctor_id: int
    email: str
    phone: Optional[str] = None
    first_name: str
    last_name: str
    specialty: str
    license_number: str
    bio: Optional[str] = None
    education: Optional[str] = None
    years_experience: Optional[int] = None
    address: Optional[str] = None

    class Config:
        orm_mode = True

class DoctorIdOnlyResponse(BaseModel):
    phone: Optional[str]
    first_name: str
    last_name: str
    specialty: str
    license_number: str
    bio: Optional[str] = None
    education: Optional[str] = None
    years_experience: Optional[int] = None
    #address: Optional[str] = None

    class Config:
        orm_mode = True


class UserProfile(BaseModel):
    id: int
    email: str
    first_name: str
    last_name: str
    phone: Optional[str] = None
    role: str
    is_active: bool
    two_factor_enabled: bool
    profile_data: Optional[dict] = None

class DoctorProfileUpdate(BaseModel):
    specialty: Optional[str] = None
    bio: Optional[str] = None
    education: Optional[str] = None
    years_experience: Optional[int] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None
    professional_phone: Optional[str] = None  # Add professional phone field

class PatientProfileUpdate(BaseModel):
    date_of_birth: Optional[str] = None
    gender: Optional[str] = None
    address: Optional[str] = None
    medical_history: Optional[str] = None
    insurance_info: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None

class AdminProfileUpdate(BaseModel):
    department: Optional[str] = None
    permissions: Optional[List[str]] = None  # Change to List[str]
    #address: Optional[str] = None

class UserProfileUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    #address: Optional[str] = None  # For updating PatientProfile.address if applicable

# New models for verification payloads
class PhoneVerificationRequest(BaseModel):
    phone: str

class PhoneVerificationConfirm(BaseModel):
    phone: str
    code: str

class EmailVerificationRequest(BaseModel):
    email: str

class EmailVerificationConfirm(BaseModel):
    email: str
    code: str

class PatientProfileResponse(BaseModel):
    user_id: int
    email: str
    phone: Optional[str] = None
    first_name: str
    last_name: str
    date_of_birth: Optional[str] = None
    gender: Optional[str] = None
    address: Optional[str] = None
    medical_history: Optional[str] = None
    insurance_info: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None

    class Config:
        orm_mode = True

class AdminCreateRequest(BaseModel):
    email: EmailStr
    first_name: str
    last_name: str
    phone: str
    password: str
    department: Optional[str] = None
    permissions: Optional[str] = None  # Change to List[str] to accept array of permissions

class AdminProfileResponse(BaseModel):
    id: int
    user_id: int
    department: Optional[str] = None
    permissions: Optional[str] = None
    address: Optional[str] = None

    class Config:
        orm_mode = True

class AdminUserResponse(BaseModel):
    id: int
    email: str
    first_name: str
    last_name: str
    phone: Optional[str] = None
    is_active: bool
    admin_profile: Optional[AdminProfileResponse] = None

    class Config:
        orm_mode = True

class UnverifiedDoctorResponse(BaseModel):
    id: int
    user_id: int
    email: str
    first_name: str
    last_name: str
    phone: Optional[str] = None
    specialty: str
    license_number: str
    created_at: datetime
    verification_notes: Optional[str] = None

    class Config:
        orm_mode = True

class DeleteAccountRequest(BaseModel):
    password: str
    confirm_deletion: bool = False

class FeaturedDoctorCreate(BaseModel):
    doctor_id: int
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    feature_enabled: bool = True

class FeaturedDoctorUpdate(BaseModel):
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    feature_enabled: Optional[bool] = None

# Add a new Pydantic model for HomeDisplaySettings
class HomeDisplaySettingsModel(BaseModel):
    show_verified_doctors: bool
    max_doctors: int

# --- Helper function for sending email ---
def send_verification_email(to_email: str, code: str) -> None:
    try:
        settings = get_settings()
        
        # Get email settings from config
        SMTP_HOST = settings.EMAIL_HOST
        SMTP_PORT = settings.EMAIL_PORT
        EMAIL_FROM = settings.EMAIL_USER
        EMAIL_PASSWORD = settings.EMAIL_PASSWORD

        if not all([SMTP_HOST, SMTP_PORT, EMAIL_FROM, EMAIL_PASSWORD]):
            raise Exception("SMTP configuration is incomplete.")

        msg = EmailMessage()
        msg["Subject"] = "TabibMeet - Your Verification Code"
        msg["From"] = EMAIL_FROM
        msg["To"] = to_email
        
        # Create HTML content with formatted OTP code
        html_content = f"""
        <html>
          <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
              <h2 style="color: #4a90e2;">TabibMeet Verification</h2>
              <p>Thank you for using TabibMeet. Please use the verification code below to complete your request:</p>
              <div style="background-color: #f4f4f4; padding: 15px; border-radius: 5px; text-align: center; margin: 20px 0;">
                <h2 style="letter-spacing: 5px; font-size: 32px; margin: 0;">{code}</h2>
              </div>
              <p>This code will expire in 10 minutes. If you didn't request this code, please ignore this email.</p>
              <p>Best regards,<br>The TabibMeet Team</p>
            </div>
          </body>
        </html>
        """
        
        # Set plain text content as fallback
        plain_text = f"Your verification code is: {code}\nThis code will expire in 10 minutes."
        
        msg.set_content(plain_text)
        msg.add_alternative(html_content, subtype="html")

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_FROM, EMAIL_PASSWORD)
            server.send_message(msg)
            
    except ImportError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to import configuration settings."
        )
    except Exception as e:
        import logging
        logging.error(f"Email sending error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not send verification email: {str(e)}"
        )

# --- Endpoint to get current user profile ---
@router.get("/me", response_model=UserProfile)
async def get_current_user_profile(current_user: User = Depends(get_current_active_user)):
    profile_data = {}
    if (current_user.role == UserRole.ADMIN and current_user.admin_profile):
        profile_data = {
            "department": current_user.admin_profile.department,
            "permissions": current_user.admin_profile.permissions,
        }
    elif (current_user.role == UserRole.DOCTOR and current_user.doctor_profile):
        profile_data = {
            "specialty": current_user.doctor_profile.specialty,
            "license_number": current_user.doctor_profile.license_number,
            "bio": current_user.doctor_profile.bio,
            "education": current_user.doctor_profile.education,
            "years_experience": current_user.doctor_profile.years_experience,
            #"address": current_user.doctor_profile.address
        }
    elif (current_user.role == UserRole.PATIENT and current_user.patient_profile):
        profile_data = {
            "date_of_birth": current_user.patient_profile.date_of_birth.isoformat() if current_user.patient_profile.date_of_birth else None,
            "gender": current_user.patient_profile.gender,
            #"address": current_user.patient_profile.address,
            "medical_history": current_user.patient_profile.medical_history,
            "insurance_info": current_user.patient_profile.insurance_info,
            "emergency_contact_name": current_user.patient_profile.emergency_contact_name,
            "emergency_contact_phone": current_user.patient_profile.emergency_contact_phone
        }
    
    return {
        "id": current_user.id,
        "email": current_user.email,
        "first_name": current_user.first_name,
        "last_name": current_user.last_name,
        "phone": current_user.phone,
        "role": current_user.role.value,
        "is_active": current_user.is_active,
        "two_factor_enabled": current_user.two_factor_enabled,
        "profile_data": profile_data
    }

@router.get("/doctors", response_model=List[DoctorProfileResponse])
def list_doctors_by_specialty(
    specialty: str,
    db: Session = Depends(get_db)
):
    doctors = db.query(DoctorProfile).filter(
        func.lower(DoctorProfile.specialty) == func.lower(specialty)
    ).all()
    response_list = []
    for doc in doctors:
        user_info = doc.user  # The associated User instance
        response_list.append({
            "doctor_id": doc.id,
            "specialty": doc.specialty,
            "license_number": doc.license_number,
            "bio": doc.bio,
            "education": doc.education,
            "years_experience": doc.years_experience,
            #"address": doc.address,
            "email": user_info.email,
            "phone": user_info.phone,
            "first_name": user_info.first_name,
            "last_name": user_info.last_name,
        })
    return response_list

@router.get("/doctors/{doctor_profile_id}", response_model=DoctorIdOnlyResponse)
async def get_doctor_profile_by_id(
    doctor_profile_id: int,
    db: Session = Depends(get_db)
):
    doctor_profile = db.query(DoctorProfile).filter(DoctorProfile.id == doctor_profile_id).first()
    if not doctor_profile:
        raise HTTPException(status_code=404, detail="Doctor profile not found")
    user = doctor_profile.user
    return {
        "phone": user.phone,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "specialty": doctor_profile.specialty,
        "license_number": doctor_profile.license_number,
        "bio": doctor_profile.bio,
        "education": doctor_profile.education,
        "years_experience": doctor_profile.years_experience,
        #"address": doctor_profile.address
    }

@router.get("/patients/{patient_id}", response_model=PatientProfileResponse)
async def get_patient_profile_by_id(
    patient_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    # Allow access if current user is a doctor or admin, or if the patient is accessing their own profile.
    if current_user.role == UserRole.PATIENT and current_user.id != patient_id:
        raise HTTPException(status_code=403, detail="Not authorized to view other patient's profile.")
    
    user = db.query(User).filter(
        User.id == patient_id,
        User.role == UserRole.PATIENT
    ).first()
    if not user or not user.patient_profile:
        raise HTTPException(status_code=404, detail="Patient profile not found")
    patient = user.patient_profile
    return {
        "user_id": user.id,
        "email": user.email,
        "phone": user.phone,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "date_of_birth": patient.date_of_birth.isoformat() if patient.date_of_birth else None,
        "gender": patient.gender,
        "address": patient.address,
        "medical_history": patient.medical_history,
        "insurance_info": patient.insurance_info,
        "emergency_contact_name": patient.emergency_contact_name,
        "emergency_contact_phone": patient.emergency_contact_phone,
    }

# --- Update user profile ---
@router.put("/me", response_model=UserProfile)
async def update_user_profile(
    profile_update: UserProfileUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    update_data = profile_update.dict(exclude_unset=True)
    for key, value in update_data.items():
        if key == "address":
            # update address in patient profile if user is a patient
            if current_user.role == UserRole.PATIENT:
                if current_user.patient_profile:
                    current_user.patient_profile.address = value
            continue
        setattr(current_user, key, value)

    db.commit()
    db.refresh(current_user)
    
    # Prepare role-specific profile data
    profile_data = {}
    if current_user.role == UserRole.ADMIN and current_user.admin_profile:
        profile_data = {
            "department": current_user.admin_profile.department,
            "permissions": current_user.admin_profile.permissions,
           # "address": current_user.admin_profile.address
        }
    elif current_user.role == UserRole.DOCTOR and current_user.doctor_profile:
        profile_data = {
            "specialty": current_user.doctor_profile.specialty,
            "license_number": current_user.doctor_profile.license_number,
            "bio": current_user.doctor_profile.bio,
            "education": current_user.doctor_profile.education,
            "years_experience": current_user.doctor_profile.years_experience,
          #  "address": current_user.doctor_profile.address
        }
    elif current_user.role == UserRole.PATIENT and current_user.patient_profile:
        profile_data = {
            "date_of_birth": current_user.patient_profile.date_of_birth.isoformat() if current_user.patient_profile.date_of_birth else None,
            "gender": current_user.patient_profile.gender,
            #"address": current_user.patient_profile.address,
            "medical_history": current_user.patient_profile.medical_history,
            "insurance_info": current_user.patient_profile.insurance_info,
            "emergency_contact_name": current_user.patient_profile.emergency_contact_name,
            "emergency_contact_phone": current_user.patient_profile.emergency_contact_phone
        }

    return {
        "id": current_user.id,
        "email": current_user.email,
        "first_name": current_user.first_name,
        "last_name": current_user.last_name,
        "phone": current_user.phone,
        "role": current_user.role.value,
        "is_active": current_user.is_active,
        "two_factor_enabled": current_user.two_factor_enabled,
        "profile_data": profile_data
    }

# Update doctor profile
@router.put("/me/doctor-profile", response_model=dict)
async def update_doctor_profile(
    profile_data: DoctorProfileUpdate,
    doctor_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Update the current doctor's profile or another doctor's profile (admin only)"""
    if doctor_id is not None:
        if current_user.role != UserRole.ADMIN:
            raise HTTPException(status_code=403, detail="Only administrators can update other doctors' profiles")
        doctor_profile = db.query(DoctorProfile).filter(DoctorProfile.id == doctor_id).first()
        if not doctor_profile:
            raise HTTPException(status_code=404, detail="Doctor profile not found")
    else:
        if current_user.role != UserRole.DOCTOR:
            raise HTTPException(status_code=403, detail="Only doctor accounts can update their own profiles")
        doctor_profile = db.query(DoctorProfile).filter(DoctorProfile.user_id == current_user.id).first()
        if not doctor_profile:
            raise HTTPException(status_code=404, detail="Doctor profile not found")
    
    # Update only provided fields
    if profile_data.specialty:
        doctor_profile.specialty = profile_data.specialty
    if profile_data.bio:
        doctor_profile.bio = profile_data.bio
    if profile_data.education:
        doctor_profile.education = profile_data.education
    if profile_data.years_experience:
        doctor_profile.years_experience = profile_data.years_experience
    if profile_data.address is not None:
        doctor_profile.address = profile_data.address
    if profile_data.city is not None:
        doctor_profile.city = profile_data.city
    if profile_data.state is not None:
        doctor_profile.state = profile_data.state
    if profile_data.postal_code is not None:
        doctor_profile.postal_code = profile_data.postal_code
    if profile_data.country is not None:
        doctor_profile.country = profile_data.country
    if profile_data.professional_phone is not None:
        doctor_profile.professional_phone = profile_data.professional_phone
    
    db.commit()
    
    return {
        "message": "Doctor profile updated successfully",
        "profile": {
            "id": doctor_profile.id,
            "specialty": doctor_profile.specialty,
            "bio": doctor_profile.bio,
            "education": doctor_profile.education,
            "years_experience": doctor_profile.years_experience,
            "address": doctor_profile.address,
            "city": doctor_profile.city,
            "state": doctor_profile.state,
            "postal_code": doctor_profile.postal_code,
            "country": doctor_profile.country,
            "professional_phone": doctor_profile.professional_phone
        }
    }

@router.get("/doctors/{doctor_id}", response_model=dict)
async def get_doctor_details(
    doctor_id: int,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_active_user)
):
    """Get doctor details by ID"""
    doctor_profile = db.query(DoctorProfile).filter(DoctorProfile.id == doctor_id).first()
    if not doctor_profile:
        raise HTTPException(status_code=404, detail="Doctor not found")
    
    doctor_user = db.query(User).filter(User.id == doctor_profile.user_id).first()
    
    # Include all information in doctor details
    return {
        "id": doctor_profile.id,
        "user_id": doctor_user.id,
        "first_name": doctor_user.first_name,
        "last_name": doctor_user.last_name,
        "phone": doctor_user.phone,
        "email": doctor_user.email,
        "specialty": doctor_profile.specialty,
        "bio": doctor_profile.bio,
        "education": doctor_profile.education,
        "years_experience": doctor_profile.years_experience,
        "address": doctor_profile.address,
        "city": doctor_profile.city,
        "state": doctor_profile.state,
        "postal_code": doctor_profile.postal_code,
        "country": doctor_profile.country,
        "professional_phone": doctor_profile.professional_phone,
        "is_verified": doctor_profile.is_verified
    }

@router.get("/unverified-doctors", response_model=List[UnverifiedDoctorResponse])
async def get_unverified_doctors(
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get all unverified doctors (admin access only)"""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can access this endpoint"
        )
    
    # Query doctor profiles where is_verified=False
    unverified_doctors = (
        db.query(DoctorProfile, User)
        .join(User, DoctorProfile.user_id == User.id)
        .filter(DoctorProfile.is_verified == False)
        .offset(skip)
        .limit(limit)
        .all()
    )
    
    result = []
    for doctor_profile, user in unverified_doctors:
        result.append({
            "id": doctor_profile.id,
            "user_id": user.id,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "phone": user.phone,
            "specialty": doctor_profile.specialty,
            "license_number": doctor_profile.license_number,
            "created_at": user.created_at,
            "verification_notes": doctor_profile.verification_notes
        })
    
    return result

# Update patient profile
@router.put("/me/patient-profile")
async def update_patient_profile(
    profile_data: PatientProfileUpdate,
    patient_id: Optional[int] = None,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Update the current patient's profile or another patient's profile (admin only)"""
    if patient_id is not None:
        if current_user.role != UserRole.ADMIN:
            raise HTTPException(status_code=403, detail="Only administrators can update other patients' profiles")
        patient_user = db.query(User).filter(User.id == patient_id, User.role == UserRole.PATIENT).first()
        if not patient_user or not patient_user.patient_profile:
            raise HTTPException(status_code=404, detail="Patient profile not found")
        patient_profile = patient_user.patient_profile
    else:
        if current_user.role != UserRole.PATIENT:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
        if not current_user.patient_profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Patient profile not found"
            )
        patient_profile = current_user.patient_profile
    
    # Update patient profile
    # Update fields only if they are provided
    if profile_data.date_of_birth is not None:
        from datetime import datetime
        patient_profile.date_of_birth = datetime.fromisoformat(profile_data.date_of_birth)
    if profile_data.gender is not None:
        patient_profile.gender = profile_data.gender
    if profile_data.address is not None:
        patient_profile.address = profile_data.address
    if profile_data.medical_history is not None:
        patient_profile.medical_history = profile_data.medical_history
    if profile_data.insurance_info is not None:
        patient_profile.insurance_info = profile_data.insurance_info
    if profile_data.emergency_contact_name is not None:
        patient_profile.emergency_contact_name = profile_data.emergency_contact_name
    if profile_data.emergency_contact_phone is not None:
        patient_profile.emergency_contact_phone = profile_data.emergency_contact_phone
    
    db.commit()
    return {"message": "Patient profile updated successfully"}

# Update admin profile
@router.put("/me/admin-profile", status_code=status.HTTP_200_OK)
def update_admin_profile(
    update: AdminProfileUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    if not current_user.admin_profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Admin profile not found"
        )
    
    # Update admin profile
    admin_profile = current_user.admin_profile
    update_data = update.dict(exclude_unset=True)
    
    # Handle permissions separately
    if "permissions" in update_data:
        if update_data["permissions"]:
            admin_profile.permissions = ",".join(update_data["permissions"])
        else:
            admin_profile.permissions = None
        del update_data["permissions"]
    
    # Update remaining fields
    for key, value in update_data.items():
        setattr(admin_profile, key, value)
    
    db.commit()
    db.refresh(admin_profile)
    
    # Return the updated admin profile
    return {
        "id": admin_profile.id,
        "user_id": admin_profile.user_id,
        "department": admin_profile.department,
        "permissions": admin_profile.permissions.split(",") if admin_profile.permissions else []
    }

# Admin endpoints for user management - Fixed implementation
@router.get("/all", response_model=List[UserProfile])
async def get_all_users(
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    users = db.query(User).offset(skip).limit(limit).all()
    result = []
    
    for user in users:
        # Get role-specific profile data
        profile_data = {}
        
        if user.role == UserRole.ADMIN and user.admin_profile:
            profile_data = {
                "department": user.admin_profile.department,
                "permissions": user.admin_profile.permissions
            }
        elif user.role == UserRole.DOCTOR and user.doctor_profile:
            profile_data = {
                "specialty": user.doctor_profile.specialty,
                "license_number": user.doctor_profile.license_number,
                "address": user.doctor_profile.address
            }
        elif user.role == UserRole.PATIENT and user.patient_profile:
            profile_data = {
                "date_of_birth": user.patient_profile.date_of_birth.isoformat() if user.patient_profile.date_of_birth else None,
                "gender": user.patient_profile.gender,
                "address": user.patient_profile.address
            }
        
        result.append({
            "id": user.id,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "phone": user.phone,
            "role": user.role.value,
            "is_active": user.is_active,
            "two_factor_enabled": user.two_factor_enabled,
            "profile_data": profile_data
        })
    
    return result

# Admin can set user active status
@router.put("/{user_id}/set-active")
async def set_user_active_status(
    user_id: int,
    is_active: bool,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    user.is_active = is_active
    db.commit()
    
    return {"message": f"User active status set to {is_active}"}

# Admin can delete user
@router.delete("/{user_id}")
async def delete_user(
    user_id: int,
    delete_request: Optional[DeleteAccountRequest] = None,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    # Only admins can access this endpoint
    if current_user.id == user_id:
        if not delete_request or not delete_request.confirm_deletion:
            raise HTTPException(status_code=400, detail="You must confirm account deletion")
        if not AuthHandler.verify_password(delete_request.password, current_user.password):
            raise HTTPException(status_code=401, detail="Incorrect password")
        db.delete(current_user)
        db.commit()
        return {"message": "Your account has been permanently deleted"}
    
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    # Find the target user to delete
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Don't allow admins to delete themselves
    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account"
        )
    
    # Special handling for admin deletion
    if user.role == UserRole.ADMIN:
        # Check if the current admin has IT department permissions
        current_admin_is_it = (
            current_user.admin_profile and 
            current_user.admin_profile.department and 
            current_user.admin_profile.department.lower() == "it"
        )
        
        # Check if target admin is from IT department
        target_admin_is_it = (
            user.admin_profile and 
            user.admin_profile.department and 
            user.admin_profile.department.lower() == "it"
        )
        
        # Only IT department admins can delete other admins
        if not current_admin_is_it:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only IT department administrators can delete admin accounts"
            )
        
        # IT department admins cannot be deleted
        if target_admin_is_it:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="IT department administrators cannot be deleted"
            )
    
    db.delete(user)
    db.commit()
    
    return {"message": "User deleted successfully"}

# Endpoint to send a phone verification code - updated to send via email
@router.post("/verify-phone", status_code=200)
async def send_phone_verification(
    payload: PhoneVerificationRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    new_phone = payload.phone
    
    # Validate phone number format (basic check)
    if not new_phone or len(''.join(filter(str.isdigit, new_phone))) < 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid phone number format. Please provide a valid phone number."
        )
    
    # Generate a 6-digit numeric verification code
    verification_code = str(random.randint(100000, 999999))
    
    # Save the new phone and the verification code in temporary fields
    current_user.pending_phone = new_phone
    current_user.phone_verification_code = verification_code
    db.commit()
    
    # Instead of SMS, send the verification code via email
    try:
        # Create email subject and content for phone verification
        settings = get_settings()
        
        # Get email settings from config
        SMTP_HOST = settings.EMAIL_HOST
        SMTP_PORT = settings.EMAIL_PORT
        EMAIL_FROM = settings.EMAIL_USER
        EMAIL_PASSWORD = settings.EMAIL_PASSWORD

        if not all([SMTP_HOST, SMTP_PORT, EMAIL_FROM, EMAIL_PASSWORD]):
            raise Exception("SMTP configuration is incomplete.")

        msg = EmailMessage()
        msg["Subject"] = "TabibMeet - Your Phone Verification Code"
        msg["From"] = EMAIL_FROM
        msg["To"] = current_user.email  # Send to user's registered email
        
        # Create HTML content with formatted OTP code
        html_content = f"""
        <html>
          <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
              <h2 style="color: #4a90e2;">TabibMeet Phone Verification</h2>
              <p>You have requested to verify the phone number: <strong>{new_phone}</strong></p>
              <p>Please use the verification code below to confirm this phone number:</p>
              <div style="background-color: #f4f4f4; padding: 15px; border-radius: 5px; text-align: center; margin: 20px 0;">
                <h2 style="letter-spacing: 5px; font-size: 32px; margin: 0;">{verification_code}</h2>
              </div>
              <p>This code will expire in 10 minutes. If you didn't request this code, please ignore this email.</p>
              <p>Best regards,<br>The TabibMeet Team</p>
            </div>
          </body>
        </html>
        """
        
        # Set plain text content as fallback
        plain_text = f"Your verification code for phone number {new_phone} is: {verification_code}\nThis code will expire in 10 minutes."
        
        msg.set_content(plain_text)
        msg.add_alternative(html_content, subtype="html")

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_FROM, EMAIL_PASSWORD)
            server.send_message(msg)
        
        # For development only - in production you would remove this return value
        return {
            "message": f"Verification code sent to your email ({current_user.email}). Please check your inbox.",
            "code": verification_code  # Remove in production
        }
            
    except Exception as e:
        import logging
        logging.error(f"Error sending phone verification code via email: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send verification code. Please try again later."
        )

# Endpoint to confirm the phone verification code and update the phone number
@router.post("/verify-phone/confirm", status_code=200)
async def confirm_phone_verification(
    payload: PhoneVerificationConfirm,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    # Check that the pending phone matches the provided phone
    if current_user.pending_phone != payload.phone:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Phone number mismatch."
        )
    # Check that the code matches
    if current_user.phone_verification_code != payload.code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid verification code."
        )
    # Update the user's phone number and clear temporary fields
    current_user.phone = payload.phone
    current_user.pending_phone = None
    current_user.phone_verification_code = None
    db.commit()
    db.refresh(current_user)
    return {"verified": True}

# --- Email verification endpoints ---
@router.post("/verifyemail", status_code=200)
async def send_email_verification(
    payload: EmailVerificationRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    new_email = payload.email

    # Generate a 6-digit verification code
    verification_code = str(random.randint(100000, 999999))
    
    # Save the new email and the verification code in temporary fields.
    current_user.pending_email = new_email
    current_user.email_verification_code = verification_code
    db.commit()
    
    # Send the code by email using our helper function.
    send_verification_email(new_email, verification_code)
    
    # In production do not return the code.
    return {"message": "Verification code sent to email."}

@router.post("/verify-email/confirm", status_code=200)
async def confirm_email_verification(
    payload: EmailVerificationConfirm,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    if current_user.pending_email != payload.email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email address mismatch."
        )
    if current_user.email_verification_code != payload.code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid verification code."
        )
    # Update the user's email and clear the temporary fields.
    current_user.email = payload.email
    current_user.pending_email = None
    current_user.email_verification_code = None
    db.commit()
    db.refresh(current_user)
    return {"verified": True}

@router.post("/admin/create", status_code=status.HTTP_201_CREATED)
async def create_admin(
    admin_data: AdminCreateRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Create a new admin account (only existing admins can use this endpoint)"""
    # Verify the current user is an admin
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can create new admin accounts"
        )
    
    # Check if email already exists
    existing_user = db.query(User).filter(User.email == admin_data.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Check if phone already exists
    existing_phone = db.query(User).filter(User.phone == admin_data.phone).first()
    if existing_phone:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Phone number already registered"
        )

    # Create new admin user
    salt = secrets.token_hex(16)
    hashed_password = AuthHandler.get_password_hash(admin_data.password)
    
    new_admin = User(
        email=admin_data.email,
        password=hashed_password,
        salt=salt,
        first_name=admin_data.first_name,
        last_name=admin_data.last_name,
        phone=admin_data.phone,
        role=UserRole.ADMIN,
        is_active=True,
        created_at=datetime.utcnow()
    )
    
    db.add(new_admin)
    db.flush()  # Get the ID without committing
    
    # Determine permissions based on department
    permissions_str = admin_data.permissions
    
    if not permissions_str:  # If permissions weren't explicitly provided
        # Define available permissions
        all_permissions = [
            "manage_admins", 
            "manage_doctors", 
            "manage_patients", 
            "manage_appointments", 
            "manage_marketing", 
            "view_statistics"
        ]
        
        # Auto assign permissions based on department
        department = admin_data.department
        if department:
            department = department.lower()
            
            if department == "it":
                # IT gets all permissions
                permissions_str = ",".join(all_permissions)
            elif department == "marketing":
                # Marketing can't manage admins, appointments or patients
                restricted = ["manage_admins", "manage_appointments", "manage_patients"]
                permissions_str = ",".join([p for p in all_permissions if p not in restricted])
            elif department == "hr":
                # HR can't manage admins, appointments or marketing
                restricted = ["manage_admins", "manage_appointments", "manage_marketing"]
                permissions_str = ",".join([p for p in all_permissions if p not in restricted])
            else:
                # Default: basic view permissions
                permissions_str = "view_statistics"
    
    # Create admin profile with determined permissions
    admin_profile = AdminProfile(
        user_id=new_admin.id,
        department=admin_data.department,
        permissions=permissions_str
    )
    
    db.add(admin_profile)
    db.commit()
    
    # Get permissions as a list for response
    permission_list = permissions_str.split(",") if permissions_str else []
    
    return {
        "message": "Admin account created successfully",
        "admin": {
            "id": new_admin.id,
            "email": new_admin.email,
            "first_name": new_admin.first_name,
            "last_name": new_admin.last_name,
            "role": new_admin.role.value,
            "department": admin_data.department,
            "permissions": permission_list,
            "admin_profile_id": admin_profile.id
        }
    }

@router.get("/admins", response_model=List[AdminUserResponse])
async def get_all_admins(
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get all admin users (admin access only)"""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can access this endpoint"
        )
    
    # Query all users with ADMIN role
    admin_users = db.query(User).filter(
        User.role == UserRole.ADMIN
    ).offset(skip).limit(limit).all()
    
    return admin_users

@router.put("/{user_id}")
async def admin_update_user(
    user_id: int,
    profile_data: UserProfileUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Access denied")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    for key, value in profile_data.dict(exclude_unset=True).items():
        setattr(user, key, value)
    db.commit()
    db.refresh(user)
    return {"message": "User profile updated successfully"}

@router.put("/{user_id}/doctor-profile")
async def admin_update_doctor_profile(
    user_id: int,
    profile_data: DoctorProfileUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Access denied")
    user = db.query(User).filter(User.id == user_id, User.role == UserRole.DOCTOR).first()
    if not user or not user.doctor_profile:
        raise HTTPException(status_code=404, detail="Doctor not found")
    doctor_profile = user.doctor_profile
    
    # Update all fields from the profile data
    for field, value in profile_data.dict(exclude_unset=True).items():
        setattr(doctor_profile, field, value)
    
    db.commit()
    db.refresh(doctor_profile)
    return {"message": "Doctor profile updated successfully"}

@router.put("/{user_id}/patient-profile")
async def admin_update_patient_profile(
    user_id: int,
    profile_data: PatientProfileUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Access denied")
    user = db.query(User).filter(User.id == user_id, User.role == UserRole.PATIENT).first()
    if not user or not user.patient_profile:
        raise HTTPException(status_code=404, detail="Patient not found")
    patient_profile = user.patient_profile
    if profile_data.date_of_birth:
        if profile_data.date_of_birth.strip():
            try:
                patient_profile.date_of_birth = datetime.fromisoformat(profile_data.date_of_birth)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid date_of_birth format. Must be ISO 8601.")
    for field in ["gender", "address", "medical_history", "insurance_info", "emergency_contact_name", "emergency_contact_phone"]:
        val = getattr(profile_data, field)
        if val is not None:
            setattr(patient_profile, field, val)
    db.commit()
    db.refresh(patient_profile)
    return {"message": "Patient profile updated successfully"}

@router.put("/{user_id}/admin-profile")
async def admin_update_admin_profile(
    user_id: int,
    update_data: AdminProfileUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Access denied")
    user = db.query(User).filter(User.id == user_id, User.role == UserRole.ADMIN).first()
    if not user or not user.admin_profile:
        raise HTTPException(status_code=404, detail="Admin not found")
    admin_profile = user.admin_profile
    if update_data.permissions is not None:
        if update_data.permissions:
            admin_profile.permissions = ",".join(update_data.permissions)
        else:
            admin_profile.permissions = None
    for key, value in update_data.dict(exclude_unset=True, exclude={"permissions"}).items():
        setattr(admin_profile, key, value)
    db.commit()
    db.refresh(admin_profile)
    return {"message": "Admin profile updated successfully"}

@public_router.get("/featured-doctors")
def get_featured_doctors(db: Session = Depends(get_db)):
    featured_doctors = db.query(FeaturedDoctor).filter(FeaturedDoctor.feature_enabled == True).all()
    result = []
    
    for fd in featured_doctors:
        # Only include entries with valid doctor and user relationships
        if fd.doctor and fd.doctor.user:
            result.append({
                "id": fd.id,
                "doctor_id": fd.doctor_id,
                "start_date": fd.start_date,
                "end_date": fd.end_date,
                "feature_enabled": fd.feature_enabled,
                "doctor": {
                    "id": fd.doctor.id,
                    "first_name": fd.doctor.user.first_name,
                    "last_name": fd.doctor.user.last_name,
                    "specialty": fd.doctor.specialty
                }
            })
    
    return result

@router.get("/featured-doctors")
def get_featured_doctors_protected(db: Session = Depends(get_db)):
    """
    Get comprehensive information about all featured doctors for admin view
    and home screen display.
    """
    # Get all featured doctors, regardless of enabled status for admin view
    featured_doctors = db.query(FeaturedDoctor).all()
    result = []
    
    for fd in featured_doctors:
        # Check if doctor and user relationships exist
        if fd.doctor and fd.doctor.user:
            doc = fd.doctor
            user = doc.user
            
            # Include full location information and contact details
            formatted_location = None
            if doc.city and doc.state and doc.country:
                formatted_location = f"{doc.city}, {doc.state}, {doc.country}"
            elif doc.address:
                formatted_location = doc.address
                
            result.append({
                "id": fd.id,
                "doctor_id": fd.doctor_id,
                "start_date": fd.start_date,
                "end_date": fd.end_date,
                "feature_enabled": fd.feature_enabled,
                "doctor": {
                    "id": doc.id,
                    "user_id": user.id,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "email": user.email,
                    "phone": user.phone,
                    "professional_phone": doc.professional_phone,
                    "specialty": doc.specialty,
                    "license_number": doc.license_number,
                    "bio": doc.bio,
                    "education": doc.education,
                    "years_experience": doc.years_experience,
                    "address": doc.address,
                    "city": doc.city,
                    "state": doc.state,
                    "postal_code": doc.postal_code,
                    "country": doc.country,
                    "is_verified": doc.is_verified,
                    "formatted_location": formatted_location,
                    "contact": doc.professional_phone or user.phone,  # Prioritize professional phone
                    "full_name": f"{user.first_name} {user.last_name}"
                }
            })
        else:
            # Include incomplete entries with a warning for admins
            result.append({
                "id": fd.id,
                "doctor_id": fd.doctor_id if fd.doctor else None,
                "start_date": fd.start_date,
                "end_date": fd.end_date,
                "feature_enabled": fd.feature_enabled,
                "doctor": {
                    "id": fd.doctor_id if fd.doctor else None,
                    "warning": "Doctor profile or user data is missing"
                }
            })
    
    return result

@router.get("/featured-doctors/{featured_doctor_id}")
def get_featured_doctor_by_id(featured_doctor_id: int, db: Session = Depends(get_db)):
    featured_doctor = db.query(FeaturedDoctor).filter(FeaturedDoctor.id == featured_doctor_id).first()
    if not featured_doctor:
        raise HTTPException(status_code=404, detail="Featured doctor not found")
    
    # Get comprehensive doctor information
    doctor_profile = featured_doctor.doctor
    doctor_user = doctor_profile.user
    
    return {
        "id": featured_doctor.id,
        "doctor_id": featured_doctor.doctor_id,
        "start_date": featured_doctor.start_date,
        "end_date": featured_doctor.end_date,
        "feature_enabled": featured_doctor.feature_enabled,
        "doctor": {
            "id": doctor_profile.id,
            "user_id": doctor_user.id,
            "first_name": doctor_user.first_name,
            "last_name": doctor_user.last_name,
            "email": doctor_user.email,
            "phone": doctor_user.phone,
            "professional_phone": doctor_profile.professional_phone,
            "specialty": doctor_profile.specialty,
            "license_number": doctor_profile.license_number,
            "bio": doctor_profile.bio,
            "education": doctor_profile.education,
            "years_experience": doctor_profile.years_experience,
            "address": doctor_profile.address,
            "city": doctor_profile.city,
            "state": doctor_profile.state,
            "postal_code": doctor_profile.postal_code,
            "country": doctor_profile.country,
            "is_verified": doctor_profile.is_verified,
        }
    }

@router.post("/featured-doctors")
def create_featured_doctor(
    data: FeaturedDoctorCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Only admins can create featured doctors.")
    featured_doctor = FeaturedDoctor(
        doctor_id=data.doctor_id,
        start_date=data.start_date,
        end_date=data.end_date,
        feature_enabled=data.feature_enabled
    )
    db.add(featured_doctor)
    db.commit()
    db.refresh(featured_doctor)
    return {"message": "Featured doctor created.", "featured_doctor": featured_doctor}

@router.put("/featured-doctors/{featured_doctor_id}")
def update_featured_doctor(
    featured_doctor_id: int,
    data: FeaturedDoctorUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Only admins can update featured doctors.")
    featured_doctor = db.query(FeaturedDoctor).filter(FeaturedDoctor.id == featured_doctor_id).first()
    if not featured_doctor:
        raise HTTPException(status_code=404, detail="Featured doctor not found.")
    if data.start_date is not None:
        featured_doctor.start_date = data.start_date
    if data.end_date is not None:
        featured_doctor.end_date = data.end_date
    if data.feature_enabled is not None:
        featured_doctor.feature_enabled = data.feature_enabled
    db.commit()
    db.refresh(featured_doctor)
    return {"message": "Featured doctor updated.", "featured_doctor": featured_doctor}

@router.delete("/featured-doctors/{featured_doctor_id}")
def delete_featured_doctor(
    featured_doctor_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Delete a featured doctor by ID (admin only)"""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Only admins can delete featured doctors"
        )
    
    featured_doctor = db.query(FeaturedDoctor).filter(FeaturedDoctor.id == featured_doctor_id).first()
    if not featured_doctor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Featured doctor not found"
        )
    
    db.delete(featured_doctor)
    db.commit()
    
    return {"message": f"Featured doctor with ID {featured_doctor_id} has been deleted"}

# Keep the admin version for modifying settings
@router.get("/home-display-settings", response_model=HomeDisplaySettingsModel)
async def get_home_display_settings_admin(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get the current home display settings, only admins can access"""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can access display settings"
        )
    
    # Get the settings or create default if not exists
    settings = db.query(HomeDisplaySettings).first()
    if not settings:
        # Create with default values
        settings = HomeDisplaySettings(
            show_verified_doctors=False,
            max_doctors=10
        )
        db.add(settings)
        db.commit()
        db.refresh(settings)
    
    return {
        "show_verified_doctors": settings.show_verified_doctors,
        "max_doctors": settings.max_doctors
    }

# Add a public endpoint to get home display settings without authentication
@public_router.get("/home-display-settings", response_model=HomeDisplaySettingsModel)
async def get_home_display_settings(
    db: Session = Depends(get_db)
):
    """Get the current home display settings, public access"""
    # Get the settings or return default if not exists
    settings = db.query(HomeDisplaySettings).first()
    
    if not settings:
        # Return default values without creating in DB
        # (admin will create when they access the settings)
        return {
            "show_verified_doctors": False,
            "max_doctors": 10
        }
    
    return {
        "show_verified_doctors": settings.show_verified_doctors,
        "max_doctors": settings.max_doctors
    }

# Add endpoint to update home display settings
@router.post("/home-display-settings", response_model=HomeDisplaySettingsModel)
async def update_home_display_settings(
    settings_data: HomeDisplaySettingsModel,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Update the home display settings, only admins can modify"""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can update display settings"
        )
    
    # Get current settings or create new
    settings = db.query(HomeDisplaySettings).first()
    if not settings:
        settings = HomeDisplaySettings()
        db.add(settings)
    
    # Update fields
    settings.show_verified_doctors = settings_data.show_verified_doctors
    settings.max_doctors = settings_data.max_doctors
    
    db.commit()
    db.refresh(settings)
    
    return {
        "show_verified_doctors": settings.show_verified_doctors,
        "max_doctors": settings.max_doctors
    }

# Add public endpoint to get verified doctors for the home page
@public_router.get("/verified-doctors-for-home")
async def get_verified_doctors_for_home(
    limit: int = 10,
    db: Session = Depends(get_db)
):
    """Get verified doctors for the home page with optional limit parameter"""
    # First check the display settings to see what we should return
    settings = db.query(HomeDisplaySettings).first()
    
    # Default to featured doctors if settings don't exist or show_verified_doctors is False
    show_verified = settings.show_verified_doctors if settings else False
    max_count = min(settings.max_doctors if settings else 10, limit)
    
    if show_verified:
        # Return verified doctors with complete information
        doctors = (db.query(DoctorProfile)
                  .filter(DoctorProfile.is_verified == True)
                  .order_by(func.random())  # Random order for variety
                  .limit(max_count)
                  .all())
                  
        result = []
        for doc in doctors:
            if doc.user:  # Check if user exists
                result.append({
                    "id": doc.id,
                    "user_id": doc.user_id,
                    "first_name": doc.user.first_name,
                    "last_name": doc.user.last_name,
                    "email": doc.user.email,
                    "professional_phone": doc.professional_phone,
                    "specialty": doc.specialty,
                    "license_number": doc.license_number,
                    "bio": doc.bio,
                    "education": doc.education,
                    "years_experience": doc.years_experience,
                    "address": doc.address,
                    "city": doc.city,
                    "state": doc.state,
                    "postal_code": doc.postal_code,
                    "country": doc.country,
                    "verification_notes": doc.verification_notes,
                    "location": f"{doc.city}, {doc.state}, {doc.country}" if doc.city and doc.state and doc.country else (
                        doc.address if doc.address else "No location provided"
                    )
                })
        return result
    else:
        # Return featured doctors with complete information
        featured_doctors = db.query(FeaturedDoctor).filter(FeaturedDoctor.feature_enabled == True).limit(max_count).all()
        result = []
        
        for fd in featured_doctors:
            # Only include entries with valid doctor and user relationships
            if fd.doctor and fd.doctor.user:
                doc = fd.doctor
                user = doc.user
                result.append({
                    "id": doc.id,
                    "user_id": doc.user_id,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "email": user.email,
                    "professional_phone": doc.professional_phone,
                    "specialty": doc.specialty,
                    "license_number": doc.license_number,
                    "bio": doc.bio,
                    "education": doc.education,
                    "years_experience": doc.years_experience,
                    "address": doc.address,
                    "city": doc.city,
                    "state": doc.state,
                    "postal_code": doc.postal_code,
                    "country": doc.country,
                    "is_verified": doc.is_verified,
                    "verification_notes": doc.verification_notes,
                    "created_at": user.created_at.isoformat() if user.created_at else None,
                    "location": f"{doc.city}, {doc.state}, {doc.country}" if doc.city and doc.state and doc.country else (
                        doc.address if doc.address else "No location provided"
                    ),
                    "featured": True,
                    "feature_start_date": fd.start_date.isoformat() if fd.start_date else None,
                    "feature_end_date": fd.end_date.isoformat() if fd.end_date else None
                })
        
        return result

@public_router.get("/doctors/searchbyname")
def search_doctors_by_name(
    name: str,
    db: Session = Depends(get_db)
):
    """Search for doctors by name and return comprehensive information
    
    First searches in the User table to find name matches,
    then filters to only include users who are doctors.
    """
    # First search for users whose names match the search term
    matching_users = db.query(User).filter(
        User.role == UserRole.DOCTOR,
        func.concat(User.first_name, ' ', User.last_name).ilike(f"%{name}%")
    ).all()
    
    result = []
    for user in matching_users:
        # For each matching user with DOCTOR role, get their doctor profile
        if user.doctor_profile:
            # Create a more comprehensive response with additional profile details
            result.append({
                "doctor_id": user.doctor_profile.id,
                "user_id": user.id,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "email": user.email,
                "phone": user.phone,
                "specialty": user.doctor_profile.specialty or "",
                "license_number": user.doctor_profile.license_number,
                "bio": user.doctor_profile.bio,
                "education": user.doctor_profile.education,
                "years_experience": user.doctor_profile.years_experience,
                "address": user.doctor_profile.address,
                "city": user.doctor_profile.city,
                "state": user.doctor_profile.state,
                "postal_code": user.doctor_profile.postal_code,
                "country": user.doctor_profile.country,
                "is_verified": user.doctor_profile.is_verified
            })
    
    return result

