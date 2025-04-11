# routes/availability.py

from typing import List, Optional
from datetime import date, time, datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database.session import get_db
from services.availability_service import AvailabilityService
from models.user import DoctorAvailability, User
from models.user import Appointment  # Import the Appointment model
from services.auth import  get_current_active_user

# Define request and response schemas
from pydantic import BaseModel


class AvailabilityCreate(BaseModel):
    availability_date: datetime
    start_time: time
    end_time: time
    is_available: bool = True
    # New optional intervals
    start_time2: Optional[time] = None
    end_time2: Optional[time] = None
    start_time3: Optional[time] = None
    end_time3: Optional[time] = None



class AvailabilityUpdate(BaseModel):
    availability_date: Optional[date] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    is_available: Optional[bool] = None
    start_time2: Optional[time] = None
    end_time2: Optional[time] = None
    start_time3: Optional[time] = None
    end_time3: Optional[time] = None
  


class AvailabilityOut(BaseModel):
    id: int
    doctor_id: int
    availability_date: date
    start_time: time
    end_time: time
    is_available: bool
    # New optional intervals in response
    start_time2: Optional[time] = None
    end_time2: Optional[time] = None
    start_time3: Optional[time] = None
    end_time3: Optional[time] = None
   
    
    class Config:
        orm_mode = True


class AppointmentOut(BaseModel):
    id: int
    doctor_id: int
    patient_id: int
    start_time: time
    end_time: time
    appointment_date: date
    status: str
    reason: Optional[str] = None
    notes: Optional[str] = None
    
    class Config:
        orm_mode = True


router = APIRouter(
    prefix="/availability",
    tags=["availability"],
    responses={404: {"description": "Not found"}},
)


@router.get("/doctor_availability", response_model=List[AvailabilityOut])
def get_doctor_availability(
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_active_user)
):
    # Retrieve the user's ID.
     #user_id = current_user.id

    # Obtain the doctor ID from the user's doctor_profile.
    doctor_id = current_user.doctor_profile.id

    # The following lines remain unchanged:
    try:
        availability_list = AvailabilityService.get_doctor_availability(db, doctor_id)
        return availability_list
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving doctor availability: {str(e)}"
        )



@router.get("/doctor/{doctor_id}/date/{availability_date}", response_model=List[AvailabilityOut])
def get_doctor_availability_by_date(
        doctor_id: int,
        availability_date: date,
        db: Session = Depends(get_db),
        current_user: dict = Depends(get_current_active_user)
):
    """Get doctor availability for a specific date"""
    try:
        availability_list = AvailabilityService.get_available_slots_by_date(db, doctor_id, availability_date)
        return availability_list
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving doctor availability: {str(e)}"
        )


@router.post("/", response_model=AvailabilityOut)
def create_availability_slot(
        availability_data: AvailabilityCreate,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_active_user),
):
    """Create a new availability slot for a doctor using token-based user info."""
    # Retrieve the doctor ID from the token (i.e., the current user's profile)
    doctor_id = current_user.doctor_profile.id

    try:
        new_slot = AvailabilityService.create_availability_slot(
            db=db,
            doctor_id=doctor_id,  # Use the doctor's ID retrieved from the token
            availability_date=availability_data.availability_date,
            start_time=availability_data.start_time,
            end_time=availability_data.end_time,
            is_available=availability_data.is_available,
            start_time2=availability_data.start_time2,
            end_time2=availability_data.end_time2,
            start_time3=availability_data.start_time3,
            end_time3=availability_data.end_time3,
           
        )
        return new_slot
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating availability slot: {e}",
        )




@router.put("/{slot_id}", response_model=AvailabilityOut)
def update_availability_slot(
        slot_id: int,
        slot_update: AvailabilityUpdate,
        db: Session = Depends(get_db),
        current_user: dict = Depends(get_current_active_user)
):
    """Update an existing availability slot"""
    try:
        updated_slot = AvailabilityService.update_availability_slot(
            db=db,
            slot_id=slot_id,
            availability_date=slot_update.availability_date,
            start_time=slot_update.start_time,
            end_time=slot_update.end_time,
            is_available=slot_update.is_available,
            start_time2=slot_update.start_time2,
            end_time2=slot_update.end_time2,
            start_time3=slot_update.start_time3,
            end_time3=slot_update.end_time3,
         
        )
        return updated_slot
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating availability slot: {str(e)}"
        )


@router.delete("/{slot_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_availability_slot(
        slot_id: int,
        db: Session = Depends(get_db),
        current_user: dict = Depends(get_current_active_user)
):
    """Delete an availability slot"""
    try:
        AvailabilityService.delete_availability_slot(db, slot_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting availability slot: {str(e)}"
        )


@router.get("/find/", response_model=List[dict])
def find_available_doctors(
        availability_date: date,
        start_time: time,
        end_time: time,
        db: Session = Depends(get_db),
        current_user: dict = Depends(get_current_active_user)
):
    """Find doctors available on a specific date during a given time period"""
    try:
        available_doctors = AvailabilityService.get_available_doctors_by_date_time(
            db=db,
            availability_date=availability_date,
            start_time=start_time,
            end_time=end_time
        )

        # Format the response to include relevant doctor information
        result = []
        for user in available_doctors:
            doctor = user.doctor_profile
            result.append({
                "doctor_id": doctor.id,
                "user_id": user.id,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "specialty": doctor.specialty,
                "years_experience": doctor.years_experience,
                "address": doctor.address,
                "city": doctor.city,
                "state": doctor.state,
                "postal_code": doctor.postal_code,
                "country": doctor.country
            })

        return result
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error finding available doctors: {str(e)}"
        )


# NEW: Public router without prefix for public endpoints
public_router = APIRouter()

@public_router.get("/public/doctor/{doctor_id}/availabilities")
def get_public_doctor_availabilities(
    doctor_id: int,
    db: Session = Depends(get_db)
):
    """Public endpoint to get all availabilities and appointments for a doctor by doctor id without token authentication"""
    try:
        # For debugging
        print(f"Calling get_public_doctor_availabilities with doctor_id: {doctor_id}")
        
        # Get the data directly from the database if the service method doesn't work
        try:
            data = AvailabilityService.get_public_doctor_availabilities(db, doctor_id)
        except AttributeError:
            # Fallback direct query if the method isn't found
            availabilities = db.query(DoctorAvailability).filter(
                DoctorAvailability.doctor_id == doctor_id
            ).all()
            appointments = db.query(Appointment).filter(
                Appointment.doctor_id == doctor_id
            ).all()
            data = {"availabilities": availabilities, "appointments": appointments}
        
        # Convert SQLAlchemy objects to dictionaries to avoid serialization issues
        return {
            "availabilities": [
                {
                    "id": av.id,
                    "doctor_id": av.doctor_id,
                    "availability_date": str(av.availability_date),
                    "start_time": str(av.start_time),
                    "end_time": str(av.end_time), 
                    "is_available": av.is_available,
                    "start_time2": str(av.start_time2) if av.start_time2 else None,
                    "end_time2": str(av.end_time2) if av.end_time2 else None,
                    "start_time3": str(av.start_time3) if av.start_time3 else None,
                    "end_time3": str(av.end_time3) if av.end_time3 else None
                } 
                for av in data["availabilities"]
            ],
            "appointments": [
                {
                    "id": app.id,
                    "doctor_id": app.doctor_id,
                    "patient_id": app.patient_id,
                    "start_time": str(app.start_time),
                    "end_time": str(app.end_time),
                    "appointment_date": str(app.appointment_date),
                    "status": app.status,
                    "reason": app.reason,
                    "notes": app.notes
                }
                for app in data["appointments"]
            ]
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving doctor availabilities: {str(e)}"
        )