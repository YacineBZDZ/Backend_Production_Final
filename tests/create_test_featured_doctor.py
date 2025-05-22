import sys
import os
from datetime import datetime, timedelta

# Add the project root to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database.session import SessionLocal
from models.user import User, UserRole, DoctorProfile, FeaturedDoctor

def create_test_featured_doctor():
    """
    Create some test featured doctors using the first available doctor in the database.
    """
    db = SessionLocal()
    
    try:
        # Find doctors that are not already featured
        featured_doctor_ids = [fd.doctor_id for fd in db.query(FeaturedDoctor).all()]
        
        # Get doctors not already featured
        available_doctors = db.query(DoctorProfile).filter(
            ~DoctorProfile.id.in_(featured_doctor_ids) if featured_doctor_ids else True
        ).join(User).filter(User.role == UserRole.DOCTOR).limit(3).all()
        
        if not available_doctors:
            print("No unfeatured doctors found in the database. Please create some doctor accounts first.")
            return
        
        print(f"Found {len(available_doctors)} unfeatured doctors")
        
        # Create featured entries for each doctor
        for i, doctor in enumerate(available_doctors):
            # Get the user for this doctor profile
            user = doctor.user
            
            # Set different start/end dates for variety
            start_date = datetime.now() - timedelta(days=i)
            end_date = datetime.now() + timedelta(days=30 + i*5)
            
            featured_doctor = FeaturedDoctor(
                doctor_id=doctor.id,
                user_id=user.id,
                start_date=start_date,
                end_date=end_date,
                feature_enabled=True
            )
            
            db.add(featured_doctor)
            print(f"Created featured doctor for {user.first_name} {user.last_name} ({user.email})")
        
        db.commit()
        print("Featured doctors created successfully!")
        
    except Exception as e:
        db.rollback()
        print(f"Error creating test featured doctors: {str(e)}")
    finally:
        db.close()

if __name__ == "__main__":
    create_test_featured_doctor()
