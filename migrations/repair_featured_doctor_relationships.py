from sqlalchemy import text
import os
import sys

# Add the project root to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database.session import engine, SessionLocal
from models.user import FeaturedDoctor, DoctorProfile, User

def repair_featured_doctor_relationships():
    """
    Find and repair any broken relationships between FeaturedDoctor, DoctorProfile, and User models.
    Uses direct SQL for more reliable repairs.
    """
    conn = engine.connect()
    
    try:
        print("Starting repair of featured doctor relationships...")
        
        # Get all featured doctors with their relationships using SQL
        result = conn.execute(text("""
            SELECT 
                fd.id, fd.doctor_id, fd.user_id,
                dp.user_id as doctor_user_id,
                CASE WHEN dp.id IS NULL THEN 0 ELSE 1 END as doctor_exists,
                CASE WHEN u1.id IS NULL THEN 0 ELSE 1 END as user_exists,
                CASE WHEN u2.id IS NULL THEN 0 ELSE 1 END as doctor_user_exists
            FROM 
                featured_doctors fd
            LEFT JOIN 
                doctor_profiles dp ON fd.doctor_id = dp.id
            LEFT JOIN 
                users u1 ON fd.user_id = u1.id
            LEFT JOIN 
                users u2 ON dp.user_id = u2.id
        """))
        
        featured_doctors = result.fetchall()
        print(f"Found {len(featured_doctors)} featured doctors in database")
        
        fixed_count = 0
        deleted_count = 0
        
        trans = conn.begin()
        
        try:
            for row in featured_doctors:
                fd_id = row[0]
                doctor_id = row[1]
                user_id = row[2]
                doctor_user_id = row[3]
                doctor_exists = row[4]
                user_exists = row[5]
                doctor_user_exists = row[6]
                
                # Case 1: Doctor doesn't exist - delete the featured doctor
                if not doctor_exists:
                    print(f"Featured doctor ID {fd_id} has invalid doctor_id {doctor_id} - removing")
                    conn.execute(text(f"DELETE FROM featured_doctors WHERE id = {fd_id}"))
                    deleted_count += 1
                    continue
                
                # Case 2: Doctor exists but has no valid user - delete the featured doctor
                if doctor_exists and not doctor_user_exists:
                    print(f"Featured doctor ID {fd_id} has doctor with invalid user_id - removing")
                    conn.execute(text(f"DELETE FROM featured_doctors WHERE id = {fd_id}"))
                    deleted_count += 1
                    continue
                
                # Case 3: Doctor and doctor's user exist, but user_id in featured_doctors is wrong or missing
                if doctor_exists and doctor_user_exists and (not user_exists or user_id != doctor_user_id):
                    print(f"Featured doctor ID {fd_id} needs user_id update to {doctor_user_id}")
                    conn.execute(text(f"UPDATE featured_doctors SET user_id = {doctor_user_id} WHERE id = {fd_id}"))
                    fixed_count += 1
                    continue
                
                # Case 4: Everything is good
                if doctor_exists and user_exists and doctor_user_exists and user_id == doctor_user_id:
                    print(f"Featured doctor ID {fd_id} has valid relationships")
                    fixed_count += 1
            
            # Commit all changes
            trans.commit()
            
            print(f"Repair completed: {fixed_count} featured doctors with valid relationships, {deleted_count} invalid records removed")
            
        except Exception as e:
            trans.rollback()
            print(f"Error during repair transaction: {str(e)}")
            
    except Exception as e:
        print(f"Error during repair: {str(e)}")
    finally:
        conn.close()

if __name__ == "__main__":
    repair_featured_doctor_relationships()
