# backend/api/services.py
from datetime import datetime, timedelta
import logging
import secrets
import pyotp
import hashlib
from fastapi import APIRouter, Depends, HTTPException, status, Request, BackgroundTasks
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr, field_validator
import re
import smtplib
from typing import Optional
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from core.config import get_settings
from database.session import get_db
from models.user import User, UserRole, AdminProfile, PatientProfile, DoctorProfile

from models.authentication import (
    AuthHandler, 
    authenticate_user, 
    get_current_active_user
)

# Import the email utility function - renamed to avoid conflicts
from email_utils import send_email as send_email_util, print_email_config, test_send_direct_email
import user_agents
import random

router = APIRouter(tags=["Authentication"])
settings = get_settings()
ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES

# Print email configuration on module load for debugging purposes
print("\n=== Auth Module Email Configuration ===")
email_config = print_email_config()
print(f"Auth will use email config: {email_config}")

# Check if we're running on Render and show special message
if os.environ.get('RENDER') == 'true':
    print("\n=== RUNNING ON RENDER - TESTING EMAIL DIRECTLY ===")
    # Try to send a direct test email to diagnose issues
    test_result = test_send_direct_email(to_email=settings.ADMIN_EMAIL)
    print(f"Direct email test result: {'SUCCESS' if test_result else 'FAILED'}")
    print("====================================================\n")

# Function to send email - using the imported function with a different name to prevent recursion
async def send_email_wrapper(to_email: str, subject: str, html_content: str, signature_enabled: bool = True):
    """A wrapper around the email utility to send emails."""
    # Log the email attempt for debugging
    logger = logging.getLogger(__name__)
    logger.info(f"Auth module sending email to: {to_email}, subject: {subject}")
    
    # Call the imported utility function, not recursively calling this function
    result = await send_email_util(
        to_email=to_email,
        subject=subject,
        html_content=html_content,
        signature_enabled=signature_enabled
    )
    
    # Log the result
    if result:
        logger.info(f"Email to {to_email} sent successfully from auth module")
    else:
        logger.error(f"Failed to send email to {to_email} from auth module")
    
    return result

# Pydantic models for request/response
class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int
    user_id: int
    role: str

class TokenRefresh(BaseModel):
    refresh_token: str

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    confirm_password: str
    first_name: str
    last_name: str
    phone: str
    role: UserRole
    
    # Optional fields for patient profile
    date_of_birth: Optional[str] = None
    gender: Optional[str] = None
    medical_history: Optional[str] = None
    insurance_info: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    
    # Optional fields for doctor profile
    specialty: Optional[str] = None
    bio: Optional[str] = None
    education: Optional[str] = None
    years_experience: Optional[int] = None
    license_number: Optional[str] = None
    
    # Common fields for both
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None

    @field_validator('password')
    def password_strength(cls, v):
        """Validate password strength."""
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters')
        if not re.search(r'[A-Z]', v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not re.search(r'[a-z]', v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not re.search(r'[0-9]', v):
            raise ValueError('Password must contain at least one number')
        if not re.search(r'[^A-Za-z0-9]', v):
            raise ValueError('Password must contain at least one special character')
        return v
    
    @field_validator('confirm_password')
    def passwords_match(cls, v, values, **kwargs):
        if 'password' in values.data and v != values.data['password']:
            raise ValueError('Passwords do not match')
        return v
    
    @field_validator('phone')
    def phone_format(cls, v):
        """Validate phone number format."""
        if not re.match(r'^\+?[0-9]{10,15}$', v):
            raise ValueError('Invalid phone number format')
        return v

class TwoFactorSetup(BaseModel):
    enabled: bool

class TwoFactorVerify(BaseModel):
    code: str

class PasswordResetRequest(BaseModel):
    email: EmailStr

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str
    confirm_password: str

# Doctor Verification Status model
class DoctorVerificationUpdate(BaseModel):
    is_verified: bool
    license_number: Optional[str] = None
    specialty: Optional[str] = None
    verification_notes: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None

# Add a new class for 2FA-related responses
class TwoFactorLoginResponse(BaseModel):
    message: str
    requires_2fa: bool = True
    user_id: int
    email: str

# Helper function to generate and send 2FA code with TabibMeet signature
async def generate_and_send_2fa_code(user: User, db: Session, purpose: str = "login") -> str:
    """
    Generate a 6-digit 2FA code, save it to the user, and send it via email
    
    Args:
        user: The user object
        db: Database session
        purpose: Purpose of the code (login, setup, etc.)
        
    Returns:
        The generated code
    """
    # Generate a random 6-digit code
    code = str(random.randint(100000, 999999))
    
    # Save the code to the user
    user.two_factor_secret = code
    db.commit()
    
    # Log for debugging
    logger = logging.getLogger(__name__)
    logger.info(f"Generated 2FA code for user {user.id} ({user.email}) for purpose: {purpose}")
    
    # Determine the appropriate email subject and content
    if purpose == "login":
        subject = "Votre Code de Vérification pour la Connexion - TabibMeet"
        html_content = f"""
        <html>
        <body>
            <h2>Code de Vérification pour la Connexion</h2>
            <p>Bonjour {user.first_name},</p>
            <p>Votre code de vérification pour vous connecter à TabibMeet est :</p>
            <p style="font-size: 24px; font-weight: bold; text-align: center; padding: 10px; background-color: #f0f0f0; border-radius: 5px;">{code}</p>
            <p>Ce code expirera dans 10 minutes.</p>
            <p>Si vous n'avez pas demandé ce code, veuillez ignorer cet e-mail ou contacter le support si vous avez des inquiétudes concernant la sécurité de votre compte.</p>
            <p>Merci,<br>L'équipe TabibMeet</p>
        </body>
        </html>
        """
    elif purpose == "setup":
        subject = "Votre Code de Configuration pour l'Authentification à Deux Facteurs - TabibMeet"
        html_content = f"""
        <html>
        <body>
            <h2>Configuration de l'Authentification à Deux Facteurs</h2>
            <p>Bonjour {user.first_name},</p>
            <p>Votre code de vérification pour configurer l'authentification à deux facteurs est :</p>
            <p style="font-size: 24px; font-weight: bold; text-align: center; padding: 10px; background-color: #f0f0f0; border-radius: 5px;">{code}</p>
            <p>Veuillez saisir ce code dans l'application TabibMeet pour terminer la configuration de votre authentification à deux facteurs.</p>
            <p>Si vous n'avez pas demandé ce code, veuillez ignorer cet e-mail ou contacter le support.</p>
            <p>Merci,<br>L'équipe TabibMeet</p>
        </body>
        </html>
        """
    else:
        subject = "Votre Code de Vérification - TabibMeet"
        html_content = f"""
        <html>
        <body>
            <h2>Code de Vérification</h2>
            <p>Bonjour {user.first_name},</p>
            <p>Votre code de vérification est :</p>
            <p style="font-size: 24px; font-weight: bold; text-align: center; padding: 10px; background-color: #f0f0f0; border-radius: 5px;">{code}</p>
            <p>Si vous n'avez pas demandé ce code, veuillez ignorer cet e-mail.</p>
            <p>Merci,<br>L'équipe TabibMeet</p>
        </body>
        </html>
        """
    
    # Log the email attempt
    logger.info(f"Sending 2FA email to {user.email} for purpose: {purpose}")
    
    # Send the email with our standard signature using the wrapper function
    email_sent = await send_email_wrapper(user.email, subject, html_content, signature_enabled=True)
    
    # Log the result
    if email_sent:
        logger.info(f"2FA email sent successfully to {user.email}")
    else:
        logger.error(f"Failed to send 2FA email to {user.email}")
    
    return code

# Registration endpoint
@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    user_data: UserCreate, 
    db: Session = Depends(get_db), 
    background_tasks: BackgroundTasks = BackgroundTasks(),
    created_by_admin: bool = False  # New parameter to indicate if created by admin
):
    # Check if email already exists
    if db.query(User).filter(User.email == user_data.email).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Check if phone already exists
    if user_data.phone and db.query(User).filter(User.phone == user_data.phone).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Phone number already registered"
        )
    
    # Generate salt and hash password
    salt = AuthHandler.generate_salt()
    hashed_password = AuthHandler.get_password_hash(user_data.password)
    
    try:
        # Create new user
        new_user = User(
            email=user_data.email,
            password=hashed_password,
            salt=salt,
            first_name=user_data.first_name,
            last_name=user_data.last_name,
            phone=user_data.phone,
            role=user_data.role
        )
        
        db.add(new_user)
        db.flush()  # Flush to get ID but don't commit yet
        
        # Create role-specific profile based on the role
        if user_data.role == UserRole.ADMIN:
            profile = AdminProfile(user_id=new_user.id)
            db.add(profile)
            success_message = "Admin account created successfully"
            
        elif user_data.role == UserRole.DOCTOR:
            # Generate a temporary unique license number if not provided
            license_number = user_data.license_number
            if not license_number:
                license_number = f"TMP-{new_user.id}-{secrets.token_hex(4)}"
            
            # Create doctor profile with unverified status
            profile = DoctorProfile(
                user_id=new_user.id,
                specialty=user_data.specialty or "Pending Verification",
                license_number=license_number,
                is_verified=False,
                verification_notes="Awaiting admin verification",
                bio=user_data.bio,
                education=user_data.education,
                years_experience=user_data.years_experience,
                address=user_data.address,
                city=user_data.city,
                state=user_data.state,
                postal_code=user_data.postal_code,
                country=user_data.country
            )
            db.add(profile)
            db.flush()  # Ensure the profile is added before sending emails
            
            # Set up email sending for doctor registration
            try:
                # Send email to admin about new doctor registration
                admin_subject = "Nouvel Enregistrement de Médecin - TabibMeet"
                admin_html_content = f"""
                <html>
                <body>
                    <h2>Un Nouvel Enregistrement de Médecin Nécessite une Vérification</h2>
                    <p>Un nouveau médecin s'est inscrit sur TabibMeet et nécessite votre approbation :</p>
                    <table border="1" cellpadding="5" cellspacing="0">
                        <tr>
                            <th>Nom :</th>
                            <td>{user_data.first_name} {user_data.last_name}</td>
                        </tr>
                        <tr>
                            <th>Email :</th>
                            <td>{user_data.email}</td>
                        </tr>
                        <tr>
                            <th>Téléphone :</th>
                            <td>{user_data.phone}</td>
                        </tr>
                        <tr>
                            <th>Spécialité :</th>
                            <td>{profile.specialty}</td>
                        </tr>
                        <tr>
                            <th>Numéro de Licence :</th>
                            <td>{profile.license_number}</td>
                        </tr>
                    </table>
                    <p>Pour vérifier ce médecin, connectez-vous au tableau de bord administrateur et accédez à la section Médecins.</p>
                    <p>ID du Médecin : {new_user.id}</p>
                </body>
                </html>
                """
                background_tasks.add_task(send_email_wrapper, settings.ADMIN_EMAIL, admin_subject, admin_html_content)
                print(f"Admin email task added for {settings.ADMIN_EMAIL}")
                
                # Notify the doctor about pending verification
                doctor_subject = "Inscription Médecin - Vérification Requise"
                doctor_html_content = f"""
                <html>
                <body>
                    <h2>Inscription du Médecin Soumise</h2>
                    <p>Cher Dr. {user_data.first_name} {user_data.last_name},</p>
                    <p>Merci pour votre inscription à TabibMeet. Votre inscription a été reçue et est en attente de vérification par nos administrateurs.</p>
                    <p>Vous pouvez vous connecter à votre compte, mais vous aurez des fonctionnalités limitées jusqu'à ce que vos informations soient vérifiées. 
                    Un administrateur vous contactera si des informations supplémentaires sont nécessaires.</p>
                    <p>Numéro de Licence : {profile.license_number}</p>
                    <p>Cordialement,<br>L'équipe TabibMeet</p>
                </body>
                </html>
                """
                background_tasks.add_task(send_email_wrapper, user_data.email, doctor_subject, doctor_html_content)
                print(f"Doctor email task added for {user_data.email}")
                
            except Exception as email_error:
                print(f"Failed to set up registration emails: {str(email_error)}")
                # Continue with registration even if email setup fails
            
            success_message = "Doctor registration submitted for verification"
            
        else:  # PATIENT
            # Convert date_of_birth string to datetime if provided
            date_of_birth = None
            if user_data.date_of_birth:
                try:
                    date_of_birth = datetime.fromisoformat(user_data.date_of_birth.replace('Z', '+00:00'))
                except ValueError:
                    # If date parsing fails, leave as None
                    pass
            
            profile = PatientProfile(
                user_id=new_user.id,
                date_of_birth=date_of_birth,
                gender=user_data.gender,
                address=user_data.address,
                medical_history=user_data.medical_history,
                insurance_info=user_data.insurance_info,
                emergency_contact_name=user_data.emergency_contact_name,
                emergency_contact_phone=user_data.emergency_contact_phone
            )
            db.add(profile)
            success_message = "Patient account created successfully"
        
        # Commit all changes after successfully creating both user and profile
        db.commit()
        db.refresh(new_user)
        
        # For doctor or patient accounts, automatically log in ONLY if not created by admin
        if (user_data.role == UserRole.DOCTOR or user_data.role == UserRole.PATIENT) and not created_by_admin:
            # Create tokens for automatic login
            access_token = AuthHandler.create_access_token({"sub": str(new_user.id), "role": new_user.role.value})
            refresh_token = AuthHandler.create_refresh_token({"sub": str(new_user.id)})
            
            # Store refresh token in database
            new_user.refresh_token = refresh_token
            new_user.last_login = datetime.utcnow()
            db.commit()
            
            # Return success message with tokens
            return {
                "message": success_message,
                "user_id": new_user.id,
                "role": user_data.role.value,
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_type": "bearer",
                "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
                "auto_login": True
            }
        else:
            # For admin accounts or users created by admin, return the standard response without tokens
            return {
                "message": success_message,
                "user_id": new_user.id,
                "role": user_data.role.value,
                "created_by_admin": created_by_admin
            }
    except Exception as e:
        db.rollback()
        # Log the full error and handle specific database errors
        error_message = str(e)
        print(f"Registration error: {error_message}")
        
        if "duplicate key" in error_message.lower():
            if "license_number" in error_message.lower():
                # Handle duplicate license number
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="License number already exists. Please contact support."
                )
            elif "email" in error_message.lower():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email already registered"
                )
            elif "phone" in error_message.lower() or "users_phone_key" in error_message.lower():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Phone number already registered"
                )
            else:
                # Generic duplicate key error
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Registration failed: duplicate entry found"
                )
        else:
            # Other unexpected errors
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create user profile. Please try again later."
            )#222

# Add a new endpoint for admins to verify doctors
@router.post("/doctor/verify/{doctor_id}", status_code=status.HTTP_200_OK)
async def verify_doctor(
    doctor_id: int,
    verification_data: DoctorVerificationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    # Only admins can verify doctors
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can verify doctors"
        )
    
    # Get the doctor profile
    doctor_profile = db.query(DoctorProfile).filter(DoctorProfile.id == doctor_id).first()
    if not doctor_profile or not doctor_profile.user or doctor_profile.user.role != UserRole.DOCTOR:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Doctor not found"
        )
    
    # Update doctor profile with verification data
    doctor_profile.is_verified = verification_data.is_verified
    
    if verification_data.license_number:
        # Check if the new license number is unique
        existing_license = db.query(DoctorProfile).filter(
            DoctorProfile.license_number == verification_data.license_number,
            DoctorProfile.id != doctor_id
        ).first()
        if existing_license:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="License number already exists"
            )
        doctor_profile.license_number = verification_data.license_number
        
    if verification_data.specialty:
        doctor_profile.specialty = verification_data.specialty
        
    if verification_data.verification_notes:
        doctor_profile.verification_notes = verification_data.verification_notes
        
    # Update address fields if provided
    if verification_data.address:
        doctor_profile.address = verification_data.address
    if verification_data.city:
        doctor_profile.city = verification_data.city
    if verification_data.state:
        doctor_profile.state = verification_data.state
    if verification_data.postal_code:
        doctor_profile.postal_code = verification_data.postal_code
    if verification_data.country:
        doctor_profile.country = verification_data.country
    
    try:
        db.commit()
        
        # Send email notification to doctor about verification status
        verification_status = "approved" if verification_data.is_verified else "not approved"
        doctor_email = doctor_profile.user.email
        
        subject = f"Statut de Vérification du Médecin : {verification_status.title()}"
        html_content = f"""
        <html>
        <body>
            <h2>Vérification du Médecin {verification_status.title()}</h2>
            <p>Cher Dr. {doctor_profile.user.first_name} {doctor_profile.user.last_name},</p>
            <p>Votre statut de vérification de médecin a été mis à jour : <strong>{verification_status}</strong>.</p>
            
            {"<p>Félicitations ! Vous pouvez maintenant utiliser toutes les fonctionnalités de médecin dans le système.</p>" if verification_data.is_verified else 
             "<p>Malheureusement, votre vérification n'a pas été approuvée pour le moment. Veuillez contacter le support pour plus d'informations.</p>"}
            
            {f"<p><strong>Notes :</strong> {verification_data.verification_notes}</p>" if verification_data.verification_notes else ""}
            
            <p>Cordialement,<br>L'équipe TabibMeet</p>
        </body>
        </html>
        """
        
        background_tasks.add_task(send_email_wrapper, doctor_email, subject, html_content)
        
        return {
            "message": f"Doctor verification status updated to {verification_status}",
            "doctor_id": doctor_id,
            "is_verified": doctor_profile.is_verified
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update verification status: {str(e)}"
        )

# Update login endpoint to strictly enforce 2FA without returning tokens
@router.post("/login")
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
    request: Request = None
):
    # First authenticate with username/password
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        # Update failed login attempts
        potential_user = db.query(User).filter(User.email == form_data.username).first()
        if potential_user:
            potential_user.login_attempts += 1
            potential_user.last_login_attempt = datetime.utcnow()
            
            # Lock account after 5 failed attempts
            if potential_user.login_attempts >= 5:
                potential_user.locked_until = datetime.utcnow() + timedelta(minutes=15)
            
            db.commit()
        
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Check if account is locked
    if user.locked_until and user.locked_until > datetime.utcnow():
        remaining_time = (user.locked_until - datetime.utcnow()).seconds // 60
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Account locked due to too many failed attempts. Try again in {remaining_time} minutes."
        )
    
    # Reset failed login attempts on successful password verification
    user.login_attempts = 0
    user.last_ip = str(request.client.host) if request and request.client else None
    db.commit()
    
    # For users with 2FA enabled, we need to check for the verification code
    if user.two_factor_enabled:
        # Check if there's a 2FA code provided with this request
        twofa_code = None
        # FastAPI OAuth2 form stores additional fields in scopes
        if hasattr(form_data, 'scopes') and form_data.scopes:
            twofa_code = form_data.scopes[0] if form_data.scopes else None
        
        # If no valid 2FA code, always generate a new one and require verification
        if not twofa_code or twofa_code != user.two_factor_secret:
            # Generate and send a new 2FA code
            await generate_and_send_2fa_code(user, db, purpose="login")
            
            # Return the 2FA challenge response (without tokens)
            return TwoFactorLoginResponse(
                message="2FA verification required. A code has been sent to your email.",
                requires_2fa=True,
                user_id=user.id,
                email=user.email
            )
        
        # If we reach here, the 2FA code was valid
        # Clear the used 2FA code
        user.two_factor_secret = None
    
    # At this point, authentication is complete (password + 2FA if enabled)
    
    # Update last login timestamp
    user.last_login = datetime.utcnow()
    
    # Create tokens after successful authentication
    access_token = AuthHandler.create_access_token({"sub": str(user.id), "role": user.role.value})
    refresh_token = AuthHandler.create_refresh_token({"sub": str(user.id)})
    
    # Store refresh token in database
    user.refresh_token = refresh_token
    db.commit()
    
    # Return standard token response
    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user_id=user.id,
        role=user.role.value
    )

# Add a new endpoint for 2FA verification during login
@router.post("/verify-login", response_model=Token)
async def verify_login(
    user_id: int,
    verification_code: str,
    db: Session = Depends(get_db),
    request: Request = None
):
    """Endpoint to verify 2FA code during login process"""
    
    # Get user by ID
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Verify the provided 2FA code
    if not user.two_factor_secret or user.two_factor_secret != verification_code:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid verification code"
        )
    
    # Clear the 2FA code after successful verification
    user.two_factor_secret = None
    
    # Update last login timestamp
    user.last_login = datetime.utcnow()
    
    # Create tokens after successful authentication
    access_token = AuthHandler.create_access_token({"sub": str(user.id), "role": user.role.value})
    refresh_token = AuthHandler.create_refresh_token({"sub": str(user.id)})
    
    # Store refresh token in database
    user.refresh_token = refresh_token
    
    # Record the login IP
    user.last_ip = str(request.client.host) if request and request.client else None
    
    db.commit()
    
    # Return standard token response
    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user_id=user.id,
        role=user.role.value
    )

# Token refresh endpoint
@router.post("/refresh-token", response_model=Token)
async def refresh_token(
    token_data: TokenRefresh,
    db: Session = Depends(get_db)
):
    try:
        payload = AuthHandler.decode_token(token_data.refresh_token)
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token",
            )
        
        user = db.query(User).filter(User.id == user_id).first()
        if user is None or user.refresh_token != token_data.refresh_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token",
            )
        
        # Create new tokens
        access_token = AuthHandler.create_access_token({"sub": str(user.id), "role": user.role.value})
        refresh_token = AuthHandler.create_refresh_token({"sub": str(user.id)})
        
        # Update refresh token in database
        user.refresh_token = refresh_token
        db.commit()
        
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            "user_id": user.id,
            "role": user.role.value
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

# Logout endpoint
@router.post("/logout")
async def logout(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Enhanced logout endpoint that can handle both authenticated requests 
    and token-based requests
    """
    # First try to get the token from the Authorization header
    auth_header = request.headers.get("Authorization")
    token = None
    
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
    
    # If no Authorization header, check for token in request body
    if not token:
        try:
            body = await request.json()
            token = body.get("token")
        except:
            # If request body can't be parsed, proceed without token
            pass
    
    # If we have a token, try to invalidate it
    if token:
        try:
            payload = AuthHandler.decode_token(token)
            user_id = payload.get("sub")
            
            if user_id:
                user = db.query(User).filter(User.id == user_id).first()
                if user and user.refresh_token:
                    user.refresh_token = None
                    db.commit()
                    return {"message": "Successfully logged out"}
        except Exception as e:
            # If token validation fails, it's already invalid
            print(f"Error during logout: {str(e)}")
            pass
    
    # Return success even if token wasn't found or was invalid
    # This prevents user enumeration and is user-friendly
    return {"message": "Successfully logged out"}

# Add a new endpoint to validate tokens
@router.post("/validate-token")
async def validate_token(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Validate an access token without requiring full authentication
    Enhanced for web app support to prevent unintended logouts
    
    Accepts token via:
    - Authorization header
    - Request body
    - Query parameter
    
    Returns:
        - 200 OK with user details if token is valid
        - 401 Unauthorized if token is invalid
    """
    token = None
    
    # Check Authorization header first (standard method)
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
    
    # If no token in header, check request body
    if not token:
        try:
            body = await request.json()
            token = body.get("token") or body.get("access_token")
        except:
            # Body parsing failed, continue to other methods
            pass
    
    # If still no token, check query parameters
    if not token:
        token = request.query_params.get("token") or request.query_params.get("access_token")
    
    # If no token found by any method, return error
    if not token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No token provided",
        )
    
    try:
        # Decode the token
        payload = AuthHandler.decode_token(token)
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token format",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Get the user from database
        user = db.query(User).filter(User.id == user_id).first()
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Check if user is active
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Inactive user account",
            )
        
        # For web apps: check if a token refresh is recommended soon
        # This helps clients implement proactive token refresh
        exp_timestamp = payload.get("exp", 0)
        current_timestamp = datetime.utcnow().timestamp()
        time_remaining = exp_timestamp - current_timestamp
        refresh_recommended = time_remaining < 300  # Less than 5 minutes remaining
        
        # Token is valid, return user details and token status
        return {
            "valid": True,
            "user_id": user.id,
            "role": user.role.value,
            "email": user.email,
            "refresh_recommended": refresh_recommended,
            "expires_in": int(time_remaining) if time_remaining > 0 else 0
        }
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        # Log the actual error for debugging
        print(f"Token validation error: {str(e)}")
        # Any other exception means the token is invalid
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

# Add a silent refresh endpoint for web apps
@router.post("/silent-refresh", response_model=Token)
async def silent_refresh(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Silently refresh tokens for web applications to prevent session timeouts during active usage.
    Uses refresh token from:
    - Request body (refresh_token field)
    - Authorization header (if refresh token format is detected)
    - Cookies (if implemented)
    """
    refresh_token = None
    
    # Try to get token from request body first
    try:
        body = await request.json()
        refresh_token = body.get("refresh_token")
    except:
        pass
        
    # If no token in body, check Authorization header
    if not refresh_token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            potential_token = auth_header.split(" ")[1]
            # Check if this might be a refresh token (basic validation)
            try:
                payload = AuthHandler.decode_token(potential_token)
                if "sub" in payload and len(potential_token) > 100:  # Rough check for refresh token
                    refresh_token = potential_token
            except:
                pass
    
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No refresh token provided"
        )
    
    try:
        # Decode and validate the refresh token
        payload = AuthHandler.decode_token(refresh_token)
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token format",
            )
        
        # Get the user and verify token matches
        user = db.query(User).filter(User.id == user_id).first()
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
            )
        
        # Extra security check: stored refresh token must match
        # This prevents refresh token reuse after logout
        if user.refresh_token != refresh_token:
            # For web app: if token doesn't match, it could be due to
            # another tab/window/device logging out
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session expired or ended on another device",
            )
        
        # Create new tokens
        access_token = AuthHandler.create_access_token({"sub": str(user.id), "role": user.role.value})
        new_refresh_token = AuthHandler.create_refresh_token({"sub": str(user.id)})
        
        # Update refresh token in database
        user.refresh_token = new_refresh_token
        db.commit()
        
        return Token(
            access_token=access_token,
            refresh_token=new_refresh_token,
            token_type="bearer",
            expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user_id=user.id,
            role=user.role.value
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f"Silent refresh error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token or session expired",
        )

# Enhanced logout endpoint for web app
@router.post("/logout")
async def logout(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Enhanced logout endpoint that can handle both authenticated requests
    and token-based requests, with special handling for web applications.
    
    For web apps, this properly invalidates the refresh token to prevent
    session persistence across multiple tabs/windows.
    """
    # First try to get the token from the Authorization header
    auth_header = request.headers.get("Authorization")
    token = None
    token_type = "access"  # Default assumption
    
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
    
    # If no Authorization header, check for tokens in request body
    if not token:
        try:
            body = await request.json()
            # Try to get access token first
            token = body.get("token") or body.get("access_token")
            
            # If no access token but refresh token exists, use that instead
            if not token and body.get("refresh_token"):
                token = body.get("refresh_token")
                token_type = "refresh"
        except:
            # If request body can't be parsed, proceed without token
            pass
    
    user_id = None
    
    # If we have a token, try to decode it to get user_id
    if token:
        try:
            payload = AuthHandler.decode_token(token)
            user_id = payload.get("sub")
        except:
            # Token is invalid, but we'll still continue
            pass
    
    # If we have a user_id, find and update the user record
    if user_id:
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            # For web apps: always clear the refresh token on explicit logout
            # This ensures all tabs/windows will lose their session
            if user.refresh_token:
                user.refresh_token = None
                db.commit()
                
            return {"message": "Successfully logged out", "status": "complete"}
    
    # If we reached here without finding a valid user, return a generic success
    # This avoids leaking information about what went wrong
    return {"message": "Successfully logged out", "status": "no_session"}

# Update setup_two_factor to use the new helper function
@router.post("/2fa/setup")
async def setup_two_factor(
    setup_data: TwoFactorSetup,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    if setup_data.enabled:
        # Generate and send 2FA code using the helper function
        await generate_and_send_2fa_code(current_user, db, purpose="setup")
        return {"message": "A verification code was sent to your email. Please verify it to enable 2FA."}
    else:
        current_user.two_factor_enabled = False
        current_user.two_factor_secret = None
        db.commit()
        return {"message": "Two-factor authentication disabled"}

# Two-factor authentication verification
@router.post("/2fa/verify")
async def verify_two_factor(
    verify_data: TwoFactorVerify,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    if not current_user.two_factor_secret:
        raise HTTPException(status_code=400, detail="2FA not set up")
    if verify_data.code == current_user.two_factor_secret:
        current_user.two_factor_enabled = True
        current_user.two_factor_secret = None
        db.commit()
        return {"message": "2FA enabled successfully"}
    else:
        raise HTTPException(status_code=400, detail="Invalid 2FA code")

# Password reset request
@router.post("/password-reset/request")
async def request_password_reset(
    reset_request: PasswordResetRequest,
    background_tasks: BackgroundTasks,
    request: Request,  # Add request parameter to access client IP
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.email == reset_request.email).first()
    if not user:
        # Return success even if email doesn't exist to prevent email enumeration
        return {"message": "If your email is registered, you will receive a password reset link"}
    
    # Generate reset token
    reset_token = secrets.token_urlsafe(32)
    # Store hashed version of token in database
    token_hash = hashlib.sha256(reset_token.encode()).hexdigest()
    user.reset_token = token_hash
    user.reset_token_expires = datetime.utcnow() + timedelta(hours=1)
    # Store IP address for additional verification
    user.reset_request_ip = getattr(request, 'client', None) and getattr(request.client, 'host', None)
    db.commit()
    
    # Use backend URL for the reset link - this is our universal handler
    backend_url = request.url.scheme + "://" + request.url.netloc
    reset_link = f"{backend_url}/auth/reset-password?token={reset_token}"
    
    # Email content
    subject = "Demande de Réinitialisation de Mot de Passe - TabibMeet"
    html_content = f"""
    <html>
    <body>
        <h2>Demande de Réinitialisation de Mot de Passe</h2>
        <p>Bonjour {user.first_name},</p>
        <p>Nous avons reçu une demande de réinitialisation de votre mot de passe. Si vous n'avez pas fait cette demande, vous pouvez ignorer cet e-mail.</p>
        <p>Pour réinitialiser votre mot de passe, cliquez sur le lien ci-dessous :</p>
        <p><a href="{reset_link}" style="background-color: #4CAF50; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; display: inline-block;">Réinitialiser Mon Mot de Passe</a></p>
        <p>Ce lien expirera dans 1 heure.</p>
        <p>Pour des raisons de sécurité, ce lien de réinitialisation ne peut être utilisé qu'une seule fois.</p>
        <p>Merci,<br>L'équipe TabibMeet</p>
    </body>
    </html>
    """
    
    # Send email as a background task with signature
    background_tasks.add_task(send_email_wrapper, user.email, subject, html_content, signature_enabled=True)
    
    return {"message": "If your email is registered, you will receive a password reset link"}

# Password reset confirmation
@router.post("/password-reset/confirm")
async def confirm_password_reset(
    token: str,
    new_password: str,
    confirm_password: str,
    request: Request = None,
    db: Session = Depends(get_db),
    background_tasks: BackgroundTasks = None,
):
    if new_password != confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Passwords do not match"
        )
    
    # Validate password strength with the same rules as registration
    try:
        if len(new_password) < 8:
            raise ValueError('Password must be at least 8 characters')
        if not re.search(r'[A-Z]', new_password):
            raise ValueError('Password must contain at least one uppercase letter')
        if not re.search(r'[a-z]', new_password):
            raise ValueError('Password must contain at least one lowercase letter')
        if not re.search(r'[0-9]', new_password):
            raise ValueError('Password must contain at least one number')
        if not re.search(r'[^A-Za-z0-9]', new_password):
            raise ValueError('Password must contain at least one special character')
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    
    # Hash the token to compare with stored hash
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    
    user = db.query(User).filter(
        User.reset_token == token_hash,
        User.reset_token_expires > datetime.utcnow()
    ).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token"
        )
    
    # Optional: Check if reset is from same IP (add tolerance for mobile networks/VPNs)
    current_ip = getattr(request, 'client', None) and getattr(request.client, 'host', None)
    if user.reset_request_ip and current_ip and user.reset_request_ip != current_ip:
        # Log suspicious activity but still allow reset
        print(f"Warning: Password reset for user {user.id} requested from IP {user.reset_request_ip} but reset from {current_ip}")
    
    # Generate new salt and hash the new password
    salt = AuthHandler.generate_salt()
    hashed_password = AuthHandler.get_password_hash(new_password)
    
    # Update user's password and clear reset token
    user.password = hashed_password
    user.salt = salt
    user.reset_token = None
    user.reset_token_expires = None
    user.reset_request_ip = None
    
    # Log the successful password change
    user.password_changed_at = datetime.utcnow()
    
    # Force logout from all devices by invalidating refresh tokens
    user.refresh_token = None
    
    db.commit()
    
    # Send confirmation email
    subject = "Mot de Passe Modifié - TabibMeet"
    html_content = f"""
    <html>
    <body>
        <h2>Mot de Passe Changé avec Succès</h2>
        <p>Bonjour {user.first_name},</p>
        <p>Votre mot de passe a été changé avec succès. Si vous n'avez pas demandé ce changement, veuillez contacter le support immédiatement.</p>
        <p>Merci,<br>L'équipe TabibMeet</p>
    </body>
    </html>
    """
    
    # Use background tasks for email sending with signature
    if background_tasks:
        background_tasks.add_task(send_email_wrapper, user.email, subject, html_content, signature_enabled=True)
    else:
        await send_email_wrapper(user.email, subject, html_content, signature_enabled=True)
    
    return {"message": "Password reset successfully"}

# Add a new endpoint to change password for authenticated users
@router.post("/change-password")
async def change_password(
    change_request: ChangePasswordRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    # Verify current password
    if not AuthHandler.verify_password(change_request.current_password, current_user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect"
        )
    
    # Check if new passwords match
    if change_request.new_password != change_request.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New passwords do not match"
        )
    
    # Validate password strength
    try:
        if len(change_request.new_password) < 8:
            raise ValueError('Password must be at least 8 characters')
        if not re.search(r'[A-Z]', change_request.new_password):
            raise ValueError('Password must contain at least one uppercase letter')
        if not re.search(r'[a-z]', change_request.new_password):
            raise ValueError('Password must contain at least one lowercase letter')
        if not re.search(r'[0-9]', change_request.new_password):
            raise ValueError('Password must contain at least one number')
        if not re.search(r'[^A-Za-z0-9]', change_request.new_password):
            raise ValueError('Password must contain at least one special character')
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    
    # Generate new salt and hash the new password
    salt = AuthHandler.generate_salt()
    hashed_password = AuthHandler.get_password_hash(change_request.new_password)
    
    # Update user's password
    current_user.password = hashed_password
    current_user.salt = salt
    current_user.password_changed_at = datetime.utcnow()
    
    # Invalidate all existing sessions by clearing refresh token
    current_user.refresh_token = None
    
    db.commit()
    
    # Send confirmation email
    subject = "Mot de Passe Modifié - TabibMeet"
    html_content = f"""
    <html>
    <body>
        <h2>Mot de Passe Changé avec Succès</h2>
        <p>Bonjour {current_user.first_name},</p>
        <p>Votre mot de passe a été changé avec succès. Si vous n'avez pas demandé ce changement, veuillez contacter le support immédiatement.</p>
        <p>Merci,<br>L'équipe TabibMeet</p>
    </body>
    </html>
    """
    
    # Send email as a background task
    background_tasks.add_task(send_email_wrapper, current_user.email, subject, html_content)
    
    return {"message": "Password changed successfully"}

# Add a helper function to detect device type
def detect_device_type(request: Request):
    """Detect if the request is coming from mobile or web browser."""
    user_agent = request.headers.get("user-agent", "")
    if not user_agent:
        return "unknown"
    
    ua_string = user_agents.parse(user_agent)
    
    if ua_string.is_mobile:
        # Check for specific mobile platforms
        if "iPhone" in user_agent or "iPad" in user_agent:
            return "ios"
        elif "Android" in user_agent:
            return "android"
        else:
            return "mobile"
    elif ua_string.is_tablet:
        return "tablet"
    else:
        return "desktop"

# Update the reset password redirect to handle multiple platforms
@router.get("/reset-password", response_class=HTMLResponse)
async def reset_password_redirect(token: str, request: Request, db: Session = Depends(get_db)):
    """
    Smart redirect handler for password reset links.
    Detects device type and redirects accordingly:
    - Mobile apps: Use deep links
    - Web browsers: Redirect to reset page
    """
    # Verify token validity first (optional but provides better UX)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    valid_token = db.query(User).filter(
        User.reset_token == token_hash,
        User.reset_token_expires > datetime.utcnow()
    ).first() is not None
    
    # Get base URL from the current request
    base_url = f"{request.url.scheme}://{request.url.netloc}"
    
    if not valid_token:
        # For invalid tokens, redirect to error page
        error_page = f"{base_url}/auth/password-reset-error"
        return RedirectResponse(url=error_page)
    
    device_type = detect_device_type(request)
    
    # Create appropriate redirect based on device type
    if device_type == "ios":
        # iOS deep link
        redirect_url = f"tabibmeet://reset-password?token={token}"
    elif device_type == "android":
        # Android deep link
        redirect_url = f"tabibmeet://reset-password?token={token}"
    else:
        # Web redirect to the reset password form endpoint
        redirect_url = f"{base_url}/auth/password-reset-form?token={token}"
    
    # HTML with JavaScript that tries mobile app first, then falls back to web
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Password Reset - TabibMeet</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <script>
            // Function to redirect to web app after a timeout
            function redirectToWeb() {{
                window.location.href = "{base_url}/auth/password-reset-form?token={token}";
            }}
            
            // Try opening the mobile app
            window.location.href = "{redirect_url}";
            
            // If mobile app doesn't open within 1.5 seconds, redirect to web
            setTimeout(redirectToWeb, 1500);
        </script>
        <style>
            body {{ font-family: Arial, sans-serif; text-align: center; padding: 20px; }}
            .loader {{ 
                border: 5px solid #f3f3f3; 
                border-radius: 50%; 
                border-top: 5px solid #3498db; 
                width: 50px; 
                height: 50px; 
                animation: spin 1s linear infinite; 
                margin: 20px auto;
            }}
            @keyframes spin {{ 0% {{ transform: rotate(0deg); }} 100% {{ transform: rotate(360deg); }} }}
        </style>
    </head>
    <body>
        <h2>Password Reset - TabibMeet</h2>
        <div class="loader"></div>
        <p>Please wait while we process your password reset request...</p>
        <p>If you are not redirected automatically, <a href="{base_url}/auth/password-reset-form?token={token}">click here</a>.</p>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

# Add a simple password reset form endpoint
@router.get("/password-reset-form", response_class=HTMLResponse)
async def password_reset_form(token: str, db: Session = Depends(get_db)):
    """Provide a simple HTML form for password reset"""
    # Verify token validity
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    valid_token = db.query(User).filter(
        User.reset_token == token_hash,
        User.reset_token_expires > datetime.utcnow()
    ).first() is not None
    
    if not valid_token:
        return HTMLResponse(content="""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Invalid Token - TabibMeet</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                body { font-family: Arial, sans-serif; text-align: center; padding: 20px; }
                .error { color: red; }
            </style>
        </head>
        <body>
            <h2>Invalid or Expired Token</h2>
            <p class="error">The password reset link is invalid or has expired.</p>
            <p>Please request a new password reset link.</p>
        </body>
        </html>
        """)
    
    # Return a simple HTML form for resetting password
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Réinitialiser le Mot de Passe - TabibMeet</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body {{ font-family: Arial, sans-serif; padding: 20px; max-width: 500px; margin: 0 auto; }}
            .form-group {{ margin-bottom: 15px; }}
            label {{ display: block; margin-bottom: 5px; }}
            input[type="password"] {{ width: 100%; padding: 8px; box-sizing: border-box; }}
            button {{ background: #4CAF50; color: white; border: none; padding: 10px 15px; cursor: pointer; }}
            .error {{ color: red; display: none; }}
            .success {{ color: green; display: none; }}
        </style>
    </head>
    <body>
        <h2>Réinitialisez Votre Mot de Passe</h2>
        <div id="error-message" class="error"></div>
        <div id="success-message" class="success"></div>
        <form id="reset-form">
            <div class="form-group">
                <label for="password">Nouveau Mot de Passe</label>
                <input type="password" id="password" name="password" required>
            </div>
            <div class="form-group">
                <label for="confirm-password">Confirmer le Mot de Passe</label>
                <input type="password" id="confirm-password" name="confirm_password" required>
            </div>
            <button type="submit">Réinitialiser le Mot de Passe</button>
        </form>
        
        <script>
            document.getElementById('reset-form').addEventListener('submit', async function(e) {{
                e.preventDefault();
                
                const password = document.getElementById('password').value;
                const confirmPassword = document.getElementById('confirm-password').value;
                const errorElement = document.getElementById('error-message');
                const successElement = document.getElementById('success-message');
                
                errorElement.style.display = 'none';
                successElement.style.display = 'none';
                
                if (password !== confirmPassword) {{
                    errorElement.textContent = 'Les mots de passe ne correspondent pas';
                    errorElement.style.display = 'block';
                    return;
                }}
                
                try {{
                    const response = await fetch('/auth/password-reset/confirm', {{
                        method: 'POST',
                        headers: {{ 'Content-Type': 'application/json' }},
                        body: JSON.stringify({{
                            token: '{token}',
                            new_password: password,
                            confirm_password: confirmPassword
                        }})
                    }});
                    
                    const result = await response.json();
                    
                    if (response.ok) {{
                        successElement.textContent = result.message || 'Réinitialisation du mot de passe réussie !';
                        successElement.style.display = 'block';
                        document.getElementById('reset-form').style.display = 'none';
                    }} else {{
                        errorElement.textContent = result.detail || 'Échec de la réinitialisation du mot de passe';
                        errorElement.style.display = 'block';
                    }}
                }} catch (error) {{
                    errorElement.textContent = 'Une erreur s\'est produite. Veuillez réessayer.';
                    errorElement.style.display = 'block';
                    console.error(error);
                }}
            }});
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

# Add a password reset error page
@router.get("/password-reset-error", response_class=HTMLResponse)
async def password_reset_error():
    """Show error page for invalid reset links"""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Reset Link Invalid - TabibMeet</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body { font-family: Arial, sans-serif; text-align: center; padding: 20px; }
            .error { color: red; margin: 20px 0; }
            .btn { background: #4CAF50; color: white; border: none; padding: 10px 15px; cursor: pointer; text-decoration: none; }
        </style>
    </head>
    <body>
        <h2>Password Reset Failed</h2>
        <p class="error">The password reset link is invalid or has expired.</p>
        <p>Please request a new password reset link.</p>
        <a href="/auth/request-password-reset" class="btn">Request New Reset Link</a>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

# Modified model for resending 2FA code - using email instead of user_id
class ResendOTPRequest(BaseModel):
    email: EmailStr
    purpose: str = "login"  # Can be "login" or "setup"

# Modified endpoint to resend OTP code using email for identification
@router.post("/2fa/send-code")
async def resend_otp_code(
    request_data: ResendOTPRequest,
    db: Session = Depends(get_db)
):
    """Resend a new OTP code to the user's email, invalidating any previous code"""
    
    # Find the user by email
    user = db.query(User).filter(User.email == request_data.email).first()
    if not user:
        # Return a success message even if the email doesn't exist to prevent user enumeration
        return {
            "message": "If your email is registered, a verification code has been sent.",
        }
    
    # Generate and send a new 2FA code
    try:
        # The generate_and_send_2fa_code function already invalidates previous codes
        # by overwriting the two_factor_secret field
        await generate_and_send_2fa_code(user, db, purpose=request_data.purpose)
        
        return {
            "message": "A new verification code has been sent to your email.",
            "email": user.email
        }
    except Exception as e:
        print(f"Error sending 2FA code: {str(e)}")
        # Use a generic error message that doesn't confirm if email exists
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send verification code. Please try again."
        )