import sys
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import logging
from contextlib import asynccontextmanager
import uvicorn
import psycopg2

from core.config import get_settings
from routes import appointment_routes
from services import auth
from services import users
from services import availability_routes
from ws.router import router as websocket_router
import services.appointment_updater as appointment_updater
from database.session import close_db_connections
from services.users import public_router as users_public_router
# Import test user creation functions
from database.create_test_doctor import create_verified_test_doctor, create_verified_test_admin, create_test_patient

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

