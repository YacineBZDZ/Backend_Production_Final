#!/usr/bin/env python3
"""
Google Cloud SQL Connection Test Script

This script tests the connection to Google Cloud SQL and runs
diagnostic checks to help identify connection issues.
"""

import sys
import os
import time
import logging
import socket
import psycopg2
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

# Add parent directory to path so we can import from project
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import project configuration
from core.config import get_settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

def test_dns_resolution():
    """Test DNS resolution for the database host"""
    settings = get_settings()
    
    # Check if we have a host to test
    if not settings.DB_HOST or settings.DB_HOST == "localhost":
        logger.info("Skipping DNS check - Using localhost or Cloud SQL Proxy")
        return True
    
    logger.info(f"Testing DNS resolution for {settings.DB_HOST}...")
    try:
        ip_address = socket.gethostbyname(settings.DB_HOST)
        logger.info(f"✓ DNS resolution successful: {settings.DB_HOST} resolves to {ip_address}")
        return True
    except socket.gaierror as e:
        logger.error(f"× DNS resolution failed: {e}")
        return False

def test_port_connectivity():
    """Test direct TCP connection to the database port"""
    settings = get_settings()
    
    # Skip if using localhost (likely with proxy)
    if not settings.DB_HOST or settings.DB_HOST == "localhost":
        logger.info("Skipping port connectivity check - Using localhost or Cloud SQL Proxy")
        return True
    
    port = int(settings.DB_PORT or 5432)
    logger.info(f"Testing TCP connection to {settings.DB_HOST}:{port}...")
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(5)  # 5 second timeout
    
    try:
        sock.connect((settings.DB_HOST, port))
        logger.info(f"✓ TCP connection successful to {settings.DB_HOST}:{port}")
        sock.close()
        return True
    except socket.error as e:
        logger.error(f"× TCP connection failed: {e}")
        sock.close()
        return False

def test_psycopg2_connection():
    """Test basic psycopg2 connection to the database"""
    settings = get_settings()
    
    # Get connection details
    if settings.DB_USE_PROXY:
        host = "localhost"
    else:
        host = settings.DB_HOST
    
    port = settings.DB_PORT or "5432"
    dbname = settings.DB_NAME
    user = settings.DB_USER
    password = settings.DB_PASSWORD
    
    # Log connection details (masking password)
    logger.info(f"Testing psycopg2 connection to {host}:{port}/{dbname} as {user}...")
    
    conn_string = f"host={host} port={port} dbname={dbname} user={user} password=******"
    logger.info(f"Connection string: {conn_string}")
    
    # Try to connect
    try:
        # Add sslmode parameter for Google Cloud SQL
        conn = psycopg2.connect(
            host=host,
            port=port,
            dbname=dbname,
            user=user,
            password=password,
            sslmode=settings.DB_SSL_MODE
        )
        
        # Test the connection
        cursor = conn.cursor()
        cursor.execute("SELECT version();")
        version = cursor.fetchone()
        
        logger.info(f"✓ psycopg2 connection successful")
        logger.info(f"Database version: {version[0]}")
        
        cursor.close()
        conn.close()
        return True
    except psycopg2.Error as e:
        logger.error(f"× psycopg2 connection failed: {e}")
        return False

def test_sqlalchemy_connection():
    """Test SQLAlchemy connection to the database"""
    settings = get_settings()
    
    try:
        # Get database URL from settings
        db_url = settings.get_database_url()
        
        # Mask password in log
        masked_url = db_url
        if '@' in db_url:
            parts = db_url.split('@')
            auth_part = parts[0].split(':')
            if len(auth_part) > 1:
                masked_url = f"{auth_part[0]}:******@{parts[1]}"
        
        logger.info(f"Testing SQLAlchemy connection with URL: {masked_url}")
        
        # Create engine with appropriate options
        engine_options = {
            "pool_pre_ping": True,
            "pool_recycle": 1800,
            "connect_args": {
                "connect_timeout": 10
            }
        }
        
        # Add SSL mode for non-proxy connections
        if not settings.DB_USE_PROXY and settings.DB_HOST != "localhost":
            engine_options["connect_args"]["sslmode"] = settings.DB_SSL_MODE
            logger.info(f"Using SSL mode: {settings.DB_SSL_MODE}")
        
        # Create engine
        engine = create_engine(db_url, **engine_options)
        
        # Test connection
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version();"))
            version = result.fetchone()[0]
            logger.info(f"✓ SQLAlchemy connection successful")
            logger.info(f"Database version: {version}")
            return True
    except SQLAlchemyError as e:
        logger.error(f"× SQLAlchemy connection failed: {e}")
        return False
    except Exception as e:
        logger.error(f"× Error in SQLAlchemy connection test: {e}")
        return False

def run_all_tests():
    """Run all connectivity tests and report results"""
    logger.info("===== Google Cloud SQL Connection Test =====")
    logger.info("Running diagnostic tests...")
    
    # Print environment
    settings = get_settings()
    logger.info(f"Database instance: {settings.DB_INSTANCE or 'Not set'}")
    logger.info(f"Database host: {settings.DB_HOST or 'Not set (using proxy?)'}")
    logger.info(f"Database name: {settings.DB_NAME or 'Not set'}")
    logger.info(f"Using Cloud SQL Proxy: {settings.DB_USE_PROXY}")
    logger.info(f"SSL Mode: {settings.DB_SSL_MODE}")
    
    # Run tests
    tests = [
        ("DNS Resolution", test_dns_resolution),
        ("TCP Port Connectivity", test_port_connectivity),
        ("psycopg2 Connection", test_psycopg2_connection),
        ("SQLAlchemy Connection", test_sqlalchemy_connection)
    ]
    
    results = {}
    for name, test_func in tests:
        logger.info(f"\n----- Testing {name} -----")
        try:
            start_time = time.time()
            success = test_func()
            duration = time.time() - start_time
            results[name] = {"success": success, "duration": duration}
        except Exception as e:
            logger.error(f"Exception during {name} test: {e}")
            results[name] = {"success": False, "error": str(e)}
    
    # Print summary
    logger.info("\n===== Test Results Summary =====")
    success_count = sum(1 for r in results.values() if r.get("success", False))
    logger.info(f"Passed: {success_count}/{len(tests)} tests")
    
    for name, result in results.items():
        status = "✓ PASS" if result.get("success", False) else "× FAIL"
        duration = f"{result.get('duration', 0):.2f}s" if "duration" in result else "N/A"
        logger.info(f"{status} - {name} ({duration})")
    
    # Provide diagnostic information for failures
    if success_count < len(tests):
        logger.info("\n===== Troubleshooting Tips =====")
        if not results.get("DNS Resolution", {}).get("success", False):
            logger.info("- Check if the DB_HOST value is correct")
            logger.info("- Verify network connectivity and DNS resolution")
        
        if not results.get("TCP Port Connectivity", {}).get("success", False):
            logger.info("- Check if firewall allows connections to the database port")
            logger.info("- Verify DB_PORT setting is correct (default is 5432)")
            logger.info("- Make sure the Cloud SQL instance is running")
        
        if not results.get("psycopg2 Connection", {}).get("success", False) or \
           not results.get("SQLAlchemy Connection", {}).get("success", False):
            logger.info("- Verify DB_USER and DB_PASSWORD are correct")
            logger.info("- Check if DB_NAME exists in the database")
            logger.info("- Try a different SSL mode (prefer, require, verify-ca, verify-full)")
            logger.info("- If using Cloud SQL Proxy, make sure it's running")

if __name__ == "__main__":
    run_all_tests()