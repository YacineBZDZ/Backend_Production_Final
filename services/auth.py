# backend/api/services.py
from datetime import datetime, timedelta
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
from database.session import get_db
from models.user import User, UserRole, AdminProfile, PatientProfile, DoctorProfile

from models.authentication import (
    AuthHandler, 
    authenticate_user, 
    get_current_active_user
)

from core.config import get_settings
import user_agents
import random

router = APIRouter(tags=["Authentication"])
settings = get_settings()
ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES

# Email configuration from settings
EMAIL_HOST = settings.EMAIL_HOST
EMAIL_PORT = settings.EMAIL_PORT
EMAIL_USER = settings.EMAIL_USER
EMAIL_PASSWORD = settings.EMAIL_PASSWORD
EMAIL_FROM = settings.EMAIL_FROM
FRONTEND_URL = settings.FRONTEND_URL

# Add admin email from settings
ADMIN_EMAIL = settings.ADMIN_EMAIL if hasattr(settings, 'ADMIN_EMAIL') else EMAIL_FROM

# Function to send email
async def send_email(to_email: str, subject: str, html_content: str):
    """Send an email using SMTP."""
    try:
        message = MIMEMultipart("alternative")
        message["Subject"] = subject
        message["From"] = EMAIL_FROM
        message["To"] = to_email
        
        # Add HTML content
        html_part = MIMEText(html_content, "html")
        message.attach(html_part)
        
        # Connect to server and send
        with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as server:
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_FROM, to_email, message.as_string())
        
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False

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

# Helper function to generate and send 2FA code
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
    
    # Determine the appropriate email subject and content
    if purpose == "login":
        subject = "Your TabibMeet Login Verification Code"
        html_content = f"""
        <html>
        <body>
            <h2>Login Verification Code</h2>
            <p>Hello {user.first_name},</p>
            <p>Your verification code to log in to TabibMeet is:</p>
            <p style="font-size: 24px; font-weight: bold; text-align: center; padding: 10px; background-color: #f0f0f0; border-radius: 5px;">{code}</p>
            <p>This code will expire in 10 minutes.</p>
            <p>If you did not request this code, please ignore this email or contact support if you have concerns about your account security.</p>
            <p>Thank you,<br>TabibMeet Team</p>
        </body>
        </html>
        """
    elif purpose == "setup":
        subject = "Your TabibMeet 2FA Setup Code"
        html_content = f"""
        <html>
        <body>
            <h2>Two-Factor Authentication Setup</h2>
            <p>Hello {user.first_name},</p>
            <p>Your verification code to set up two-factor authentication is:</p>
            <p style="font-size: 24px; font-weight: bold; text-align: center; padding: 10px; background-color: #f0f0f0; border-radius: 5px;">{code}</p>
            <p>Please enter this code in the TabibMeet app to complete your 2FA setup.</p>
            <p>If you did not request this code, please ignore this email or contact support.</p>
            <p>Thank you,<br>TabibMeet Team</p>
        </body>
        </html>
        """
    else:
        subject = "Your TabibMeet Verification Code"
        html_content = f"""
        <html>
        <body>
            <h2>Verification Code</h2>
            <p>Hello {user.first_name},</p>
            <p>Your verification code is:</p>
            <p style="font-size: 24px; font-weight: bold; text-align: center; padding: 10px; background-color: #f0f0f0; border-radius: 5px;">{code}</p>
            <p>If you did not request this code, please ignore this email.</p>
            <p>Thank you,<br>TabibMeet Team</p>
        </body>
        </html>
        """
    
    # Send the email
    await send_email(user.email, subject, html_content)
    
    return code

# Registration endpoint
@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    user_data: UserCreate, 
    db: Session = Depends(get_db), 
    background_tasks: BackgroundTasks = BackgroundTasks()
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
            # Generate a temporary unique license number
            temp_license = f"TMP-{new_user.id}-{secrets.token_hex(4)}"
            
            # Create doctor profile with unverified status
            profile = DoctorProfile(
                user_id=new_user.id,
                specialty="Pending Verification",
                license_number=temp_license,
                is_verified=False,
                verification_notes="Awaiting admin verification",
                address=None,
                city=None,
                state=None,
                postal_code=None,
                country=None
            )
            db.add(profile)
            db.flush()  # Ensure the profile is added before sending emails
            
            # Send email to admin about new doctor registration
            admin_subject = "New Doctor Registration - TabibMeet"
            admin_html_content = f"""
            <html>
            <body>
                <h2>New Doctor Registration Requires Verification</h2>
                <p>A new doctor has registered on TabibMeet and requires your approval:</p>
                <table border="1" cellpadding="5" cellspacing="0">
                    <tr>
                        <th>Name:</th>
                        <td>{user_data.first_name} {user_data.last_name}</td>
                    </tr>
                    <tr>
                        <th>Email:</th>
                        <td>{user_data.email}</td>
                    </tr>
                    <tr>
                        <th>Phone:</th>
                        <td>{user_data.phone}</td>
                    </tr>
                    <tr>
                        <th>Temporary License:</th>
                        <td>{temp_license}</td>
                    </tr>
                </table>
                <p>To verify this doctor, log into the admin dashboard and go to the Doctors section.</p>
                <p><a href="{FRONTEND_URL}/admin/doctors/verify/{new_user.id}">Click here to verify</a></p>
            </body>
            </html>
            """
            background_tasks.add_task(send_email, ADMIN_EMAIL, admin_subject, admin_html_content)
            
            # Notify the doctor about pending verification
            doctor_subject = "Doctor Registration - Verification Required"
            doctor_html_content = f"""
            <html>
            <body>
                <h2>Doctor Registration Submitted</h2>
                <p>Dear Dr. {user_data.first_name} {user_data.last_name},</p>
                <p>Thank you for registering with TabibMeet. Your registration has been received and is pending verification by our administrators.</p>
                <p>You can log in to your account, but you will have limited functionality until your credentials are verified. 
                An administrator will contact you if additional information is required.</p>
                <p>Temporary License: {temp_license}</p>
                <p>Best regards,<br>The TabibMeet Team</p>
            </body>
            </html>
            """
            background_tasks.add_task(send_email, user_data.email, doctor_subject, doctor_html_content)
            
            success_message = "Doctor registration submitted for verification"
            
        else:  # PATIENT
            profile = PatientProfile(user_id=new_user.id)
            db.add(profile)
            success_message = "Patient account created successfully"
        
        # Commit all changes after successfully creating both user and profile
        db.commit()
        db.refresh(new_user)
        
        # For doctor accounts, automatically log in and return tokens
        if user_data.role == UserRole.DOCTOR:
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
            # For non-doctor accounts, return the standard response
            if new_user.role == UserRole.PATIENT:
                token = AuthHandler.encode_token(new_user.id)
                return {"access_token": token, "token_type": "bearer", "user_id": new_user.id}
            return {
                "message": success_message,
                "user_id": new_user.id,
                "role": user_data.role.value
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
            )

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
        
        subject = f"Doctor Verification Status: {verification_status.title()}"
        html_content = f"""
        <html>
        <body>
            <h2>Doctor Verification {verification_status.title()}</h2>
            <p>Dear Dr. {doctor_profile.user.first_name} {doctor_profile.user.last_name},</p>
            <p>Your doctor verification status has been updated to: <strong>{verification_status}</strong>.</p>
            
            {"<p>Congratulations! You can now use all doctor features in the system.</p>" if verification_data.is_verified else 
             "<p>Unfortunately, your verification was not approved at this time. Please contact support for more information.</p>"}
            
            {f"<p><strong>Notes:</strong> {verification_data.verification_notes}</p>" if verification_data.verification_notes else ""}
            
            <p>Best regards,<br>The TabibMeet Team</p>
        </body>
        </html>
        """
        
        background_tasks.add_task(send_email, doctor_email, subject, html_content)
        
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
    subject = "Password Reset Request - TabibMeet"
    html_content = f"""
    <html>
    <body>
        <h2>Password Reset Request</h2>
        <p>Hello {user.first_name},</p>
        <p>We received a request to reset your password. If you didn't make this request, you can ignore this email.</p>
        <p>To reset your password, click the link below:</p>
        <p><a href="{reset_link}">Reset Your Password</a></p>
        <p>This link will expire in 1 hour.</p>
        <p>For security reasons, this reset link can only be used once.</p>
        <p>Thank you,<br>TabibMeet Team</p>
    </body>
    </html>
    """
    
    # Send email as a background task
    background_tasks.add_task(send_email, user.email, subject, html_content)
    
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
    subject = "Password Changed - TabibMeet"
    html_content = f"""
    <html>
    <body>
        <h2>Password Changed Successfully</h2>
        <p>Hello {user.first_name},</p>
        <p>Your password has been successfully changed. If you did not request this change, please contact support immediately.</p>
        <p>Thank you,<br>TabibMeet Team</p>
    </body>
    </html>
    """
    
    # Use background tasks for email sending
    if background_tasks:
        background_tasks.add_task(send_email, user.email, subject, html_content)
    else:
        await send_email(user.email, subject, html_content)
    
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
    subject = "Password Changed - TabibMeet"
    html_content = f"""
    <html>
    <body>
        <h2>Password Changed Successfully</h2>
        <p>Hello {current_user.first_name},</p>
        <p>Your password has been successfully changed. If you did not request this change, please contact support immediately.</p>
        <p>Thank you,<br>TabibMeet Team</p>
    </body>
    </html>
    """
    
    # Send email as a background task
    background_tasks.add_task(send_email, current_user.email, subject, html_content)
    
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
    - Web browsers: Redirect to frontend
    """
    # Verify token validity first (optional but provides better UX)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    valid_token = db.query(User).filter(
        User.reset_token == token_hash,
        User.reset_token_expires > datetime.utcnow()
    ).first() is not None
    
    if not valid_token:
        # For invalid tokens, always redirect to web frontend with error param
        return RedirectResponse(url=f"{FRONTEND_URL}/reset-password?error=invalid")
    
    device_type = detect_device_type(request)
    
    # Create appropriate redirect based on device type
    if device_type == "ios":
        # iOS deep link
        redirect_url = f"tabibmeet://reset-password?token={token}"
    elif device_type == "android":
        # Android deep link
        redirect_url = f"tabibmeet://reset-password?token={token}"
    else:
        # Web frontend URL
        redirect_url = f"{FRONTEND_URL}/reset-password?token={token}"
    
    # HTML with JavaScript that tries mobile app first, then falls back to web
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Redirecting to TabibMeet...</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <script>
            // Function to redirect to web app after a timeout
            function redirectToWeb() {{
                window.location.href = "{FRONTEND_URL}/reset-password?token={token}";
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
        <h2>Redirecting to TabibMeet</h2>
        <div class="loader"></div>
        <p>Please wait while we redirect you to the password reset page...</p>
        <p>If you are not redirected automatically, <a href="{FRONTEND_URL}/reset-password?token={token}">click here</a>.</p>
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