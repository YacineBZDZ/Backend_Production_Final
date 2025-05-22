#!/usr/bin/env python3
"""
Script to create the tabibmeet database on Google Cloud SQL.

This script connects to the default 'postgres' database and creates
the 'tabibmeet' database if it doesn't exist.
"""

import sys
import os
import logging
import argparse
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

def create_database(host, port, admin_user, admin_password, db_name, db_user=None, db_password=None):
    """
    Create the database and user if they don't exist
    """
    # Connect to the default 'postgres' database first (this always exists)
    logger.info(f"Connecting to default postgres database as {admin_user}...")
    
    try:
        # Connect to postgres database with admin credentials
        conn = psycopg2.connect(
            host=host,
            port=port,
            dbname="postgres",  # Default database
            user=admin_user,
            password=admin_password,
            sslmode="disable"
        )
        
        # Set isolation level to AUTOCOMMIT for database creation
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()
        
        # Check if database exists
        cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
        exists = cursor.fetchone()
        
        if not exists:
            logger.info(f"Creating database '{db_name}'...")
            # CREATE DATABASE must run outside of a transaction block
            cursor.execute(f"CREATE DATABASE {db_name}")
            logger.info(f"Database '{db_name}' created successfully!")
        else:
            logger.info(f"Database '{db_name}' already exists.")
        
        # Create user if provided
        if db_user and db_password:
            # Check if user exists
            cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (db_user,))
            user_exists = cursor.fetchone()
            
            if not user_exists:
                logger.info(f"Creating user '{db_user}'...")
                cursor.execute(f"CREATE USER {db_user} WITH PASSWORD %s", (db_password,))
                logger.info(f"User '{db_user}' created successfully!")
            else:
                logger.info(f"User '{db_user}' already exists, updating password...")
                cursor.execute(f"ALTER USER {db_user} WITH PASSWORD %s", (db_password,))
            
            # Grant privileges to the user on the database
            logger.info(f"Granting privileges to user '{db_user}' on database '{db_name}'...")
            cursor.execute(f"GRANT ALL PRIVILEGES ON DATABASE {db_name} TO {db_user}")
            
        cursor.close()
        conn.close()
        
        logger.info(f"Setup completed successfully!")
        return True
        
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        return False

def main():
    parser = argparse.ArgumentParser(description='Create database on Google Cloud SQL')
    parser.add_argument('--host', required=True, help='Database host (IP or hostname)')
    parser.add_argument('--port', default='5432', help='Database port')
    parser.add_argument('--admin-user', default='postgres', help='Admin username')
    parser.add_argument('--admin-password', required=True, default='z^94c$$OTta0EXcgV')
    parser.add_argument('--db-name', default='tabibmeet', help='Database name to create')
    parser.add_argument('--db-user', help='Database user to create (optional)')
    parser.add_argument('--db-password', default='z^94c$$OTta0EXcgV')
    
    args = parser.parse_args()
    
    # Create the database
    success = create_database(
        args.host, 
        args.port, 
        args.admin_user, 
        args.admin_password, 
        args.db_name,
        args.db_user,
        args.db_password
    )
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()