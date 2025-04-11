import sys
import os
from datetime import datetime
import secrets

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from database.base import engine
from models.user import User, UserRole, DoctorProfile, AdminProfile
from models.authentication import AuthHandler

def create_verified_test_doctor():
    """Create a verified doctor account for testing purposes."""
    from database.base import SessionLocal
    #testdoctor@tabibmeet.com
    #TestDoctor123!

    # Create a database session
    db = SessionLocal()
    
    try:
        # Check if test doctor already exists
        test_email = "testdoctor1@tabibmeet.com"
        existing_user = db.query(User).filter(User.email == test_email).first()
        
        if existing_user:
            print(f"Test doctor already exists with ID: {existing_user.id}")
            # Update the doctor to ensure it's verified
            if existing_user.doctor_profile:
                existing_user.doctor_profile.is_verified = True
                db.commit()
                print("Updated doctor verification status to True")
            return
            
        # Create doctor user
        salt = secrets.token_hex(16)
        password = "Testtest@1!"  # Strong password for testing
        hashed_password = AuthHandler.get_password_hash(password)
        
        new_doctor = User(
            email=test_email,
            password=hashed_password,
            salt=salt,
            first_name="Test",
            last_name="Doctor",
            phone="+1234564562",
            role=UserRole.DOCTOR,
            is_active=True,
            created_at=datetime.utcnow()
        )
        
        db.add(new_doctor)
        db.flush()  # Get the ID without committing
        
        # Create doctor profile
        doctor_profile = DoctorProfile(
            user_id=new_doctor.id,
            specialty="General",
            license_number=f"LICENSE-TEST-{new_doctor.id}",
            bio="Test doctor for development purposes",
            education="Medical School, University of Testing",
            years_experience=10,
            is_verified=True,  # Set as verified
            verification_notes="Auto-verified for testing",
            address="123 Medical Center Blvd",
            city="Test City",
            state="Test State",
            postal_code="12345",
            country="Test Country"
        )
        
        db.add(doctor_profile)
        db.commit()
        
        print(f"Created verified test doctor with ID: {new_doctor.id}")
        print(f"Doctor profile ID: {doctor_profile.id}")
        print(f"Username: {test_email}")
        print(f"Password: {password}")
        print(f"Use these credentials for testing.")
        
    except Exception as e:
        db.rollback()
        print(f"Error creating test doctor: {str(e)}")
    finally:
        db.close()

def create_verified_test_admin():
    """Create an admin account for testing purposes."""
    from database.base import SessionLocal

    # Create a database session
    db = SessionLocal()
    
    try:
        # Check if test admin already exists
        test_email = "testadmin@tabibmeet.com"
        existing_user = db.query(User).filter(User.email == test_email).first()
        
        if existing_user:
            print(f"Test admin already exists with ID: {existing_user.id}")
            # Update the admin to ensure it's active and has IT department
            if not existing_user.is_active:
                existing_user.is_active = True
            
            # Update or create admin profile with IT department
            if existing_user.admin_profile:
                existing_user.admin_profile.department = "IT"
                existing_user.admin_profile.permissions = "manage_admins,manage_doctors,manage_patients,manage_appointments,manage_marketing,view_statistics"
            else:
                # Create admin profile if it doesn't exist
                admin_profile = AdminProfile(
                    user_id=existing_user.id,
                    department="IT",
                    permissions="manage_admins,manage_doctors,manage_patients,manage_appointments,manage_marketing,view_statistics"
                )
                db.add(admin_profile)
                
            db.commit()
            print("Updated admin with IT department and full permissions")
            return
            
        # Create admin user
        salt = secrets.token_hex(16)
        password = "AdminTest@1!"  # Strong password for testing
        hashed_password = AuthHandler.get_password_hash(password)
        
        new_admin = User(
            email=test_email,
            password=hashed_password,
            salt=salt,
            first_name="Test",
            last_name="Admin",
            phone="+9876543210",
            role=UserRole.ADMIN,
            is_active=True,
            created_at=datetime.utcnow()
        )
        
        db.add(new_admin)
        db.flush()  # Get the ID without committing
        
        # Create admin profile with IT department and full permissions
        admin_profile = AdminProfile(
            user_id=new_admin.id,
            department="IT",
            permissions="manage_admins,manage_doctors,manage_patients,manage_appointments,manage_marketing,view_statistics"
        )
        
        db.add(admin_profile)
        db.commit()
        
        print(f"Created IT admin account with ID: {new_admin.id}")
        print(f"Username: {test_email}")
        print(f"Password: {password}")
        print(f"Department: IT (full permissions)")
        print(f"Use these credentials for admin testing.")
        
    except Exception as e:
        db.rollback()
        print(f"Error creating test admin: {str(e)}")
    finally:
        db.close()

def create_test_patient():
    """Create a patient account for testing purposes."""
    from database.base import SessionLocal
    
    # Create a database session
    db = SessionLocal()
    
    try:
        # Check if test patient already exists
        test_email = "testpatient@tabibmeet.com"
        existing_user = db.query(User).filter(User.email == test_email).first()
        
        if existing_user:
            print(f"Test patient already exists with ID: {existing_user.id}")
            return
            
        # Create patient user
        salt = secrets.token_hex(16)
        password = "PatientTest@1!"  # Strong password for testing
        hashed_password = AuthHandler.get_password_hash(password)
        
        new_patient = User(
            email=test_email,
            password=hashed_password,
            salt=salt,
            first_name="Test",
            last_name="Patient",
            phone="+1234567890",
            role=UserRole.PATIENT,
            is_active=True,
            created_at=datetime.utcnow()
        )
        
        db.add(new_patient)
        db.commit()
        
        print(f"Created test patient with ID: {new_patient.id}")
        print(f"Username: {test_email}")
        print(f"Password: {password}")
        print(f"Use these credentials for patient testing.")
        
    except Exception as e:
        db.rollback()
        print(f"Error creating test patient: {str(e)}")
    finally:
        db.close()

if __name__ == "__main__":
    create_verified_test_doctor()
    create_verified_test_admin()
    create_test_patient()


#testadmin@tabibmeet.com laurineclair@gmail.com   loradenzel@gmail.com  lombiemoge@gmail.com
#AdminTest@1!