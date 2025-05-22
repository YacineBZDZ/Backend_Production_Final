from sqlalchemy import Column, Integer, ForeignKey, create_engine, MetaData, Table, inspect, text
import sqlalchemy as sa
import sys
import os
import time

# Add the project root to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import SQLAlchemy session
from database.session import engine, SessionLocal

def add_user_id_column():
    """
    Add user_id column to featured_doctors table and populate it from doctor_profiles
    """
    # Create a connection and metadata object
    conn = engine.connect()
    
    try:
        # Get the inspector to check for existing columns
        inspector = inspect(engine)
        existing_columns = [col['name'] for col in inspector.get_columns('featured_doctors')]
        
        # First check if user_id column already exists
        if 'user_id' not in existing_columns:
            print("Adding user_id column to featured_doctors table...")
            
            # Start a transaction
            trans = conn.begin()
            
            try:
                # Add user_id column without constraints initially
                conn.execute(text(
                    "ALTER TABLE featured_doctors ADD COLUMN user_id INTEGER"
                ))
                
                # Now populate the user_id column using data from doctor_profiles
                # Get all featured doctors with their doctor_id
                result = conn.execute(text(
                    "SELECT id, doctor_id FROM featured_doctors"
                ))
                featured_doctors = result.fetchall()
                
                print(f"Found {len(featured_doctors)} featured doctors to update")
                
                # For each featured doctor, find the corresponding user_id in doctor_profiles
                updated_count = 0
                for fd_id, doctor_id in featured_doctors:
                    # Get user_id from doctor_profiles
                    result = conn.execute(text(
                        f"SELECT user_id FROM doctor_profiles WHERE id = {doctor_id}"
                    ))
                    doctor_record = result.fetchone()
                    
                    if doctor_record and doctor_record[0]:
                        user_id = doctor_record[0]
                        print(f"Updating featured doctor ID {fd_id} with user_id {user_id}")
                        
                        # Update the featured_doctor with the user_id
                        conn.execute(text(
                            f"UPDATE featured_doctors SET user_id = {user_id} WHERE id = {fd_id}"
                        ))
                        updated_count += 1
                    else:
                        print(f"Warning: No user_id found for doctor_id {doctor_id} in featured doctor ID {fd_id}")
                
                # Add uniqueness constraint
                conn.execute(text(
                    "CREATE UNIQUE INDEX idx_featured_doctors_user_id ON featured_doctors (user_id) WHERE user_id IS NOT NULL"
                ))
                print("Added uniqueness constraint for user_id column")
                
                # Add foreign key constraint after population
                try:
                    conn.execute(text(
                        "ALTER TABLE featured_doctors ADD CONSTRAINT fk_featured_doctors_user_id FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE"
                    ))
                    print("Added foreign key constraint for user_id column")
                except Exception as e:
                    print(f"Warning: Could not add foreign key constraint: {str(e)}")
                
                # Commit the transaction
                trans.commit()
                print(f"Migration completed: Added user_id column and populated {updated_count} records")
            except Exception as e:
                trans.rollback()
                print(f"Error during transaction: {str(e)}")
                raise
        else:
            print("user_id column already exists in featured_doctors table")
    
    except Exception as e:
        print(f"Error during migration: {str(e)}")
        raise
    finally:
        # Always close the connection
        conn.close()

def verify_relationships_raw_sql():
    """
    Verify that relationships between FeaturedDoctor, DoctorProfile, and User are correct using raw SQL
    """
    conn = engine.connect()
    try:
        # Check if the user_id column exists
        inspector = inspect(engine)
        existing_columns = [col['name'] for col in inspector.get_columns('featured_doctors')]
        
        if 'user_id' not in existing_columns:
            print("user_id column does not exist in featured_doctors table. Cannot verify relationships.")
            return
            
        # Get database version info
        db_version = conn.execute(text("SELECT version()")).scalar()
        print(f"PostgreSQL version: {db_version}")
        
        # Get all featured doctors
        result = conn.execute(text(
            """
            SELECT 
                fd.id, fd.doctor_id, fd.user_id,
                dp.user_id as doctor_user_id,
                u1.email as user_email,
                u2.email as doctor_user_email
            FROM 
                featured_doctors fd
            LEFT JOIN 
                doctor_profiles dp ON fd.doctor_id = dp.id
            LEFT JOIN 
                users u1 ON fd.user_id = u1.id
            LEFT JOIN 
                users u2 ON dp.user_id = u2.id
            """
        ))
        
        featured_doctors = result.fetchall()
        print(f"Verifying {len(featured_doctors)} featured doctors...")
        
        valid_count = 0
        invalid_count = 0
        
        for row in featured_doctors:
            fd_id = row[0]
            doctor_id = row[1]
            user_id = row[2]
            doctor_user_id = row[3]
            user_email = row[4]
            doctor_user_email = row[5]
            
            # Check relationships
            if user_id is not None and user_email is not None:
                print(f"Featured doctor ID {fd_id} has direct user relationship: {user_email}")
                valid_count += 1
            elif doctor_user_id is not None and doctor_user_email is not None:
                print(f"Featured doctor ID {fd_id} has user through doctor: {doctor_user_email}")
                # Update the user_id to match doctor's user_id if missing
                if user_id is None:
                    try:
                        conn.execute(text(
                            f"UPDATE featured_doctors SET user_id = {doctor_user_id} WHERE id = {fd_id}"
                        ))
                        print(f"  - Updated user_id to {doctor_user_id} from doctor relationship")
                    except Exception as e:
                        print(f"  - Error updating user_id: {str(e)}")
                valid_count += 1
            else:
                print(f"Featured doctor ID {fd_id} has no valid user relationship")
                invalid_count += 1
        
        print(f"Verification complete: {valid_count} valid, {invalid_count} invalid relationships")
        
    except Exception as e:
        print(f"Error during verification: {str(e)}")
    finally:
        conn.close()

if __name__ == "__main__":
    print("Starting user_id migration for featured_doctors table...")
    add_user_id_column()
    print("\nVerifying relationships between featured doctors, doctor profiles, and users...")
    verify_relationships_raw_sql()
    print("\nMigration and verification complete!")
    print("\n\nTo create featured doctors for testing, run:")
    print("python -c \"from tests.create_test_featured_doctor import create_test_featured_doctor; create_test_featured_doctor()\"")
