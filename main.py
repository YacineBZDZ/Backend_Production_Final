import sys
import os
from fastapi import FastAPI, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import logging
from contextlib import asynccontextmanager
import uvicorn
import psycopg2
from fastapi.security import HTTPBearer
from starlette.middleware.sessions import SessionMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
import secrets
import time
from fastapi.templating import Jinja2Templates
from pathlib import Path

from core.config import get_settings
from routes import appointment_routes
from routes import privacy_policy_routes  # Import the new privacy policy routes
from services import auth
from services import users
from services import availability_routes
from ws.router import router as websocket_router
import services.appointment_updater as appointment_updater
from database.session import close_db_connections
from services.users import public_router as users_public_router
# Import test user creation functions
from database.create_test_doctor import create_verified_test_doctor, create_verified_test_admin, create_test_patient

# ToDOS
"""TODO1: implment the applinks redirection
  TODO3: Fix the websocket trigring withe the notification
  TODO2: encrypt the users data in the database
  TODO4: Check all the security integration (JWT, CSRF, CORS, etc.)
  TODO5: Check the image cache and the memory usage
  TODO6: PUSH THE APP TO THE PLAY STORE
  
     """

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Global background tasks set
background_tasks = set()

# Function to create test users for the application
def setup_test_users():
    """Create test users for development and testing purposes."""
    logger.info("Creating test users...")
    
    try:
        # Create a doctor user
        create_verified_test_doctor()
        # Create an admin user
        create_verified_test_admin()
        # Create a patient user
        create_test_patient()
        
        logger.info("Test users created successfully")
    except Exception as e:
        logger.error(f"Error creating test users: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create test users on startup
    if os.getenv("ENV", "development") == "development":
        setup_test_users()
        logger.info("Test users credentials:")
        logger.info("Doctor: testdoctor1@tabibmeet.com / Testtest@1!")
        logger.info("Admin: testadmin@tabibmeet.com / AdminTest@1!")
        logger.info("Patient: testpatient@tabibmeet.com / PatientTest@1!")
    
    # Start background tasks on startup
    task = asyncio.create_task(appointment_updater.update_past_appointments())
    background_tasks.add(task)
    task.add_done_callback(background_tasks.discard)
    
    logger.info("Background tasks started")
    yield
    
    # Cancel background tasks on shutdown
    for task in background_tasks:
        task.cancel()
    
    # Close all database connections
    logger.info("Closing database connections...")
    await close_db_connections()
    
    logger.info("Background tasks cancelled")

# Initialize FastAPI app
app = FastAPI(
    title=get_settings().PROJECT_NAME,
    lifespan=lifespan,
)

# Configure CORS
allowed_origins = os.getenv("ALLOWED_ORIGINS", "*")
if isinstance(allowed_origins, str):
    allowed_origins = allowed_origins.split(",")
logger.info(f"Configured CORS with allowed origins: {allowed_origins}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)

# Security middleware
app.add_middleware(SessionMiddleware, secret_key=get_settings().SECRET_KEY)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=get_settings().ALLOWED_HOSTS)

# Rate limiting data structure (simple in-memory implementation)
rate_limit_data = {}

@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    # Add security headers to all responses
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    
    # Add CSP headers (adjust as needed for your application)
    csp_value = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "font-src 'self'; "
        "connect-src 'self'"
    )
    response.headers["Content-Security-Policy"] = csp_value
    return response

@app.middleware("http")
async def rate_limiter_middleware(request: Request, call_next):
    # Skip rate limiting for some endpoints
    if not is_sensitive_endpoint(request.url.path):
        return await call_next(request)
    
    # Get client IP
    client_ip = request.client.host if request.client else "unknown"
    current_time = time.time()
    
    # Check if IP is already rate limited
    if client_ip in rate_limit_data:
        # Clean up old requests
        rate_limit_data[client_ip] = [
            timestamp for timestamp in rate_limit_data[client_ip] 
            if current_time - timestamp < 60  # 1 minute window
        ]
        
        # Check if too many requests
        if len(rate_limit_data[client_ip]) >= 10:  # Max 10 requests per minute
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please try again later."}
            )
        
    else:
        rate_limit_data[client_ip] = []
    
    # Add current request timestamp
    rate_limit_data[client_ip].append(current_time)
    
    # Process the request
    return await call_next(request)

def is_sensitive_endpoint(path: str) -> bool:
    """Check if an endpoint should be rate limited"""
    sensitive_paths = [
        "/auth/login", 
        "/auth/password-reset",
        "/auth/password-reset-confirm",
        "/auth/reset-password",
        "/auth/password-reset-form",
        "/auth/2fa"
    ]
    return any(path.startswith(sensitive) for sensitive in sensitive_paths)

# CSRF token middleware                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               
@app.middleware("http")
async def csrf_protection_middleware(request: Request, call_next):
    # Skip CSRF protection for requests with JWT authentication
    if request.headers.get("Authorization") and request.headers.get("Authorization").startswith("Bearer "):
        return await call_next(request)
        
    # Skip CSRF for GET/HEAD/OPTIONS or public endpoints
    if request.method in ["GET", "HEAD", "OPTIONS"] or is_public_endpoint(request.url.path):
        return await call_next(request)
    
    # Check for CSRF token in POST requests
    if request.method == "POST":
        # For API requests, check X-CSRF-Token header
        csrfToken = request.headers.get("X-CSRF-Token")
        
        # For form submissions, check form data
        if not csrfToken and "application/x-www-form-urlencoded" in request.headers.get("content-type", ""):
            form_data = await request.form()
            csrfToken = form_data.get("csrf_token")
        
        # For JSON requests, check request body
        if not csrfToken and "application/json" in request.headers.get("content-type", ""):
            try:
                json_body = await request.json()
                csrfToken = json_body.get("csrf_token")
            except:
                pass
        
        # Get session token
        session_token = request.cookies.get("session")
        if not session_token or not csrfToken:
            return JSONResponse(
                status_code=403,
                content={"detail": "CSRF token missing or invalid"}
            )
        
        # In a real implementation, validate CSRF token against session token
        # Here we're just checking that it exists
    
    return await call_next(request)

def is_public_endpoint(path: str) -> bool:
    """Check if an endpoint is public and should skip CSRF protection"""
    public_paths = [
        "/health", 
        "/public/", 
        "/api/public/",
        "/auth/password-reset/request",
        "/auth/reset-password",
        "/auth/password-reset-form",
        "/public/users",
        "/auth/login",
        "/auth/2fa",
        "/auth/2fa/verify",
        "/auth/2fa/disable",
        "/auth/register"
    ]
    return any(path.startswith(sensitive) for sensitive in public_paths)

# Include routes
app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(users.router, prefix="/users", tags=["Users"])
app.include_router(users.public_router, prefix="/public/users", tags=["Public Users"])
app.include_router(appointment_routes.router)
app.include_router(availability_routes.router)
app.include_router(availability_routes.public_router, tags=["Public Availability"])
app.include_router(websocket_router, tags=["WebSockets"])
app.include_router(users.public_router, prefix="/public", tags=["Public Home Display"])
app.include_router(users_public_router, prefix="/api/public/users")
app.include_router(privacy_policy_routes.router, prefix="/privacy-policy", tags=["Privacy Policy"])
app.include_router(privacy_policy_routes.public_router, prefix="/public/privacy-policy", tags=["Public Privacy Policy"])

@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring services"""
    return {"status": "healthy"}

# Check if running directly or imported
if __name__ == "__main__":
    # Get port from environment variable for Render compatibility
    port = int(os.getenv("PORT", "8000"))
    host = os.getenv("HOST", "0.0.0.0")
    
    # For local development, enable reload
    reload_enabled = os.getenv("ENV", "development") == "development"
    
    logger.info(f"Starting server on {host}:{port} (reload={reload_enabled})")
    uvicorn.run("main:app", host=host, port=port, reload=reload_enabled)

