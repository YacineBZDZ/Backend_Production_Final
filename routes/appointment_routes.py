from fastapi import APIRouter, HTTPException, Depends, status, Query, Response
from datetime import datetime, date, timedelta, time
from pydantic import BaseModel
from typing import List, Optional
from database.base import SessionLocal
from database.session import get_db  # updated to use get_db
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from services.appointment_service import (
    create_appointment, update_appointment_status, delete_appointment, 
    update_appointment_details, search_appointments_by_name, 
    create_appointment_by_patient_fullname, get_appointments_by_date, get_past_appointments
)
from models.user import Appointment, User, UserRole
from services.auth import get_current_active_user

class AppointmentOut(BaseModel):
    id: int
    doctor_id: int
    patient_id: int
    start_time: time       # changed from datetime to time
    end_time: time         # changed from datetime to time
    appointment_date: date
    status: str
    reason: Optional[str] = None
    notes: Optional[str] = None
    doctor: Optional["DoctorDetails"] = None  # Add doctor field

    class Config:
        orm_mode = True

class AppointmentCreate(BaseModel):
    doctor_id: int
    #patient_id: int
    start_time: time            # now type time
    end_time: Optional[time] = None  # now type time
    appointment_date: date      # now type date
    reason: Optional[str] = None
    notes: Optional[str] = None

class AppointmentUpdate(BaseModel):
    # Updated to provide default None values
    doctor_id: Optional[int] = None
    patient_id: Optional[int] = None
    appointment_date: Optional[str] = None  # e.g., "YYYY-MM-DD"
    start_time: Optional[str] = None        # e.g., "HH:MM:SS"
    end_time: Optional[str] = None          # e.g., "HH:MM:SS"
    reason: Optional[str] = None
    notes: Optional[str] = None

class AppointmentStatusOut(BaseModel):
    status: str

class AppointmentCreateByFullName(BaseModel):
    patient_full_name: str
    start_time: time
    end_time: Optional[time] = None
    appointment_date: date
    reason: Optional[str] = None
    notes: Optional[str] = None

class PatientDetails(BaseModel):
    id: int
    first_name: str
    last_name: str
    gender: Optional[str] = None
    date_of_birth: Optional[date] = None
    phone: Optional[str] = None
    
    class Config:
        orm_mode = True

class DoctorDetails(BaseModel):
    id: int
    first_name: str
    last_name: str
    specialty: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None
    
    class Config:
        orm_mode = True

class AppointmentWithPatientOut(BaseModel):
    id: int
    doctor_id: int
    patient_id: int
    start_time: time
    end_time: time
    appointment_date: date
    status: str
    reason: Optional[str] = None
    notes: Optional[str] = None
    patient: PatientDetails
    
    class Config:
        orm_mode = True

class AppointmentWithDoctorOut(BaseModel):
    id: int
    doctor_id: int
    patient_id: int
    start_time: time
    end_time: time
    appointment_date: date
    status: str
    reason: Optional[str] = None
    notes: Optional[str] = None
    doctor: DoctorDetails
    patient: Optional[PatientDetails] = None
    
    class Config:
        orm_mode = True

router = APIRouter()

@router.get("/appointments/me", response_model=List[AppointmentWithDoctorOut])
def get_user_appointments(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    # Get the current date and time to filter out past appointments
    today = date.today()
    current_time = datetime.now().time()
    
    # Return appointments based on the user's role
    if current_user.role == UserRole.DOCTOR:
        # Exclude past appointments (before today or today with time already passed)
        appointments = db.query(Appointment).filter(
            Appointment.doctor_id == current_user.doctor_profile.id,
            or_(
                Appointment.appointment_date > today,
                and_(
                    Appointment.appointment_date == today,
                    Appointment.end_time >= current_time
                )
            )
        ).all()
        
        # For doctors, include patient details with each appointment
        result = []
        for appointment in appointments:
            patient_profile = appointment.patient
            patient_user = db.query(User).filter(User.id == patient_profile.user_id).first()
            
            appointment_dict = {
                "id": appointment.id,
                "doctor_id": appointment.doctor_id,
                "patient_id": appointment.patient_id,
                "start_time": appointment.start_time,
                "end_time": appointment.end_time,
                "appointment_date": appointment.appointment_date,
                "status": appointment.status,
                "reason": appointment.reason,
                "notes": appointment.notes,
                "doctor": {
                    "id": current_user.doctor_profile.id,
                    "first_name": current_user.first_name,
                    "last_name": current_user.last_name,
                    "specialty": current_user.doctor_profile.specialty,
                    "phone": current_user.phone
                },
                "patient": {
                    "id": patient_profile.id,
                    "first_name": patient_user.first_name,
                    "last_name": patient_user.last_name,
                    "gender": patient_profile.gender,
                    "date_of_birth": patient_profile.date_of_birth,
                    "phone": patient_user.phone
                }
            }
            result.append(appointment_dict)
        return result
        
    elif current_user.role == UserRole.PATIENT:
        # Exclude past appointments (before today or today with time already passed)
        appointments = db.query(Appointment).filter(
            Appointment.patient_id == current_user.patient_profile.id,
            or_(
                Appointment.appointment_date > today,
                and_(
                    Appointment.appointment_date == today,
                    Appointment.end_time >= current_time
                )
            )
        ).all()
        
        # For patients, include doctor details with each appointment
        result = []
        for appointment in appointments:
            doctor_profile = appointment.doctor
            if not doctor_profile:
                continue  # Skip appointments with missing doctor profile
                
            doctor_user = db.query(User).filter(User.id == doctor_profile.user_id).first()
            if not doctor_user:
                continue  # Skip appointments with missing doctor user
            
            appointment_dict = {
                "id": appointment.id,
                "doctor_id": appointment.doctor_id,
                "patient_id": appointment.patient_id,
                "start_time": appointment.start_time,
                "end_time": appointment.end_time,
                "appointment_date": appointment.appointment_date,
                "status": appointment.status,
                "reason": appointment.reason,
                "notes": appointment.notes,
                "doctor": {
                    "id": doctor_profile.id,
                    "first_name": doctor_user.first_name,
                    "last_name": doctor_user.last_name,
                    "specialty": doctor_profile.specialty,
                    "phone": doctor_user.phone,
                    "address": doctor_profile.address,
                    "city": doctor_profile.city,
                    "state": doctor_profile.state,
                    "postal_code": doctor_profile.postal_code,
                    "country": doctor_profile.country
                },
                "patient": {
                    "id": current_user.patient_profile.id,
                    "first_name": current_user.first_name,
                    "last_name": current_user.last_name,
                    "gender": current_user.patient_profile.gender,
                    "date_of_birth": current_user.patient_profile.date_of_birth,
                    "phone": current_user.phone
                }
            }
            result.append(appointment_dict)
        return result
    else:
        raise HTTPException(
            status_code=403,
            detail="Appointments available only for doctors and patients."
        )

@router.post("/appointments", response_model=AppointmentOut)
def add_appointment(
    appointment: AppointmentCreate,
    current_user: User = Depends(get_current_active_user)
):
    
    # Remove seconds/microseconds from times
    st = appointment.start_time.replace(second=0, microsecond=0)
    if appointment.end_time:
        et = appointment.end_time.replace(second=0, microsecond=0)
    else:
        default_dt = datetime.combine(appointment.appointment_date, appointment.start_time) + timedelta(hours=1)
        et = default_dt.time().replace(second=0, microsecond=0)
    ad = appointment.appointment_date
    session = SessionLocal()
    try:
        # Create the appointment - any WebSocket notification errors are handled internally
        # and won't affect the success of the appointment creation
        new_appt = create_appointment(
            session=session,
            doctor_id=appointment.doctor_id,
            patient_id=current_user.patient_profile.id,
            start_time=st,
            end_time=et,
            appointment_date=ad,
            reason=appointment.reason,
            notes=appointment.notes
        )
        # Fetch doctor details for response
        doctor_profile = session.query(User).filter(User.id == appointment.doctor_id).first()
        doctor_details = None
        if doctor_profile and doctor_profile.doctor_profile:
            dp = doctor_profile.doctor_profile
            doctor_details = DoctorDetails(
                id=dp.id,
                first_name=doctor_profile.first_name,
                last_name=doctor_profile.last_name,
                specialty=dp.specialty,
                phone=doctor_profile.phone,
                address=dp.address,
                city=dp.city,
                state=dp.state,
                postal_code=dp.postal_code,
                country=dp.country
            )
        return AppointmentOut(
            id=new_appt.id,
            doctor_id=new_appt.doctor_id,
            patient_id=new_appt.patient_id,
            start_time=new_appt.start_time,
            end_time=new_appt.end_time,
            appointment_date=new_appt.appointment_date,
            status=new_appt.status,
            reason=new_appt.reason,
            notes=new_appt.notes,
            doctor=doctor_details
        )
    except Exception as e:
        session.rollback()
        # Improve error message with more details
        error_message = f"Failed to create appointment: {str(e)}"
        print(error_message)  # Log the detailed error
        raise HTTPException(status_code=400, detail=error_message)
    finally:
        session.close()

@router.post("/appointments/by-fullname", response_model=AppointmentOut)
def add_appointment_by_fullname(   # changed to synchronous function
    appointment: AppointmentCreateByFullName,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    # Only doctors can create appointments by patient full name
    if current_user.role != UserRole.DOCTOR:
        raise HTTPException(status_code=403, detail="Only doctors can create this appointment.")
    
    st = appointment.start_time.replace(second=0, microsecond=0)
    if appointment.end_time:
        et = appointment.end_time.replace(second=0, microsecond=0)
    else:
        default_dt = datetime.combine(appointment.appointment_date, appointment.start_time) + timedelta(hours=1)
        et = default_dt.time().replace(second=0, microsecond=0)
    
    try:
        new_appt = create_appointment_by_patient_fullname(   # removed await
            session=db,
            doctor_id=current_user.doctor_profile.id,
            patient_full_name=appointment.patient_full_name,
            start_time=st,
            end_time=et,
            appointment_date=appointment.appointment_date,
            reason=appointment.reason,
            notes=appointment.notes
        )
        return new_appt
    except Exception as e:
        db.rollback()
        error_message = f"Failed to create appointment by fullname: {e}"
        print(error_message)  # Log the detailed error
        raise HTTPException(status_code=400, detail=error_message)

@router.patch("/appointments/{appointment_id}/status", response_model=AppointmentStatusOut)
def update_appointment_status_endpoint(
    appointment_id: int,
    new_status: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    # Get the appointment first to check ownership
    appointment = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    
    # Allow patients to cancel their own appointments
    if current_user.role == UserRole.PATIENT:
        # Check if this appointment belongs to the current patient
        if appointment.patient_id != current_user.patient_profile.id:
            raise HTTPException(status_code=403, detail="You can only update your own appointments")
        
        # Patients can only set status to "cancelled"
        if new_status != "cancelled":
            raise HTTPException(status_code=403, detail="Patients can only cancel appointments")
        
        # Update the appointment status to cancelled
        appointment.status = "cancelled"
        appointment.is_updated = True
        appointment.update_date = datetime.now()
        
        try:
            db.commit()
            db.refresh(appointment)
            return {"status": appointment.status}
        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=400, detail=f"Failed to update appointment status: {str(e)}")
            
    # For doctors, use the existing service function
    elif current_user.role == UserRole.DOCTOR:
        try:
            updated_appt = update_appointment_status(db, appointment_id, new_status, current_user.doctor_profile.id)
            return {"status": updated_appt.status}
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
            
    else:
        raise HTTPException(status_code=403, detail="Only doctors and patients can update appointment status")

@router.delete("/appointments/{appointment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_appointment_endpoint(
    appointment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    try:
        delete_appointment(db, appointment_id, current_user)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.put("/appointments/{appointment_id}", status_code=status.HTTP_200_OK)
def update_appointment(appointment_id: int, update: AppointmentUpdate, 
                       current_user: User = Depends(get_current_active_user)):
    # Allow update only for doctors and admins
    if current_user.role not in [UserRole.DOCTOR, UserRole.ADMIN]:
        raise HTTPException(status_code=403, detail="Only doctors or admins can update appointments")
    
    update_data = update.dict(exclude_unset=True)
    
    session = SessionLocal()
    try:
        appointment = session.query(Appointment).filter(Appointment.id == appointment_id).first()
        if not appointment:
            raise HTTPException(status_code=404, detail="Appointment not found")
        
        updated_appointment = update_appointment_details(
            session=session,
            appointment=appointment,
            update_data=update_data
        )
        return updated_appointment
    except HTTPException as he:
        session.rollback()
        raise he
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        session.close()

@router.get("/appointments/by-status", response_model=List[AppointmentWithPatientOut])
def get_appointments_by_status(
    status: str,  # status provided by the frontend
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    # Get the current date and time to filter out past appointments
    today = date.today()
    current_time = datetime.now().time()
    
    appointments = db.query(Appointment).filter(
        or_(
            Appointment.doctor_id == current_user.doctor_profile.id,
            Appointment.patient_id == current_user.id
        ),
        Appointment.status == status,
        # Exclude past appointments
        or_(
            Appointment.appointment_date > today,
            and_(
                Appointment.appointment_date == today,
                Appointment.end_time >= current_time
            )
        )
    ).all()
    
    # Enhance appointments with patient data
    result = []
    for appointment in appointments:
        patient_profile = appointment.patient
        patient_user = db.query(User).filter(User.id == patient_profile.user_id).first()
        
        appointment_dict = {
            "id": appointment.id,
            "doctor_id": appointment.doctor_id,
            "patient_id": appointment.patient_id,
            "start_time": appointment.start_time,
            "end_time": appointment.end_time,
            "appointment_date": appointment.appointment_date,
            "status": appointment.status,
            "reason": appointment.reason,
            "notes": appointment.notes,
            "patient": {
                "id": patient_profile.id,
                "first_name": patient_user.first_name,
                "last_name": patient_user.last_name,
                "gender": patient_profile.gender,
                "date_of_birth": patient_profile.date_of_birth,
                "phone": patient_user.phone
            }
        }
        result.append(appointment_dict)
    
    return result

@router.get("/appointments/search", response_model=List[AppointmentWithDoctorOut])
def search_appointments(name: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    """
    Search appointments by user's full name (case sensitive).
    The search matches the concatenation of first and last names.
    """
    appointments = search_appointments_by_name(db, name)
    result = []
    for appointment in appointments:
        patient_details = None
        if appointment.patient and appointment.patient.user:
            patient_details = PatientDetails(
                id=appointment.patient_id,
                first_name=appointment.patient.user.first_name,
                last_name=appointment.patient.user.last_name,
                phone=appointment.patient.user.phone,
                gender=appointment.patient.gender,
                date_of_birth=appointment.patient.date_of_birth
            )
        result.append(AppointmentWithDoctorOut(
            id=appointment.id,
            doctor_id=appointment.doctor_id,
            patient_id=appointment.patient_id,
            start_time=appointment.start_time,
            end_time=appointment.end_time,
            appointment_date=appointment.appointment_date,
            status=appointment.status,
            reason=appointment.reason,
            notes=appointment.notes,
            doctor=DoctorDetails(
                id=appointment.doctor.user.id,
                first_name=appointment.doctor.user.first_name,
                last_name=appointment.doctor.user.last_name,
                specialty=appointment.doctor.specialty,
                phone=appointment.doctor.user.phone,
                address=appointment.doctor.address,
                city=appointment.doctor.city,
                state=appointment.doctor.state,
                postal_code=appointment.doctor.postal_code,
                country=appointment.doctor.country
            ) if appointment.doctor else None,
            patient=patient_details
        ))
    return result

@router.get("/appointments/by-date", response_model=List[AppointmentWithPatientOut])
def get_appointments_by_date_endpoint(date: date, 
                                      db: Session = Depends(get_db), 
                                      current_user: User = Depends(get_current_active_user)):
    if current_user.role != UserRole.DOCTOR:
        raise HTTPException(status_code=403, detail="Only doctors can view appointments by date.")
        
    # Get the current date and time to filter out past appointments if viewing today
    today = date.today()
    current_time = datetime.now().time()
    
    # If viewing today, filter out past appointments based on time
    if date == today:
        appointments = db.query(Appointment).filter(
            Appointment.doctor_id == current_user.doctor_profile.id,
            Appointment.appointment_date == date,
            Appointment.end_time >= current_time
        ).all()
    else:
        # For future or past dates, show all appointments for that date
        appointments = get_appointments_by_date(db, current_user.doctor_profile.id, date)
    
    # Enhance appointments with patient data
    result = []
    for appointment in appointments:
        patient_profile = appointment.patient
        patient_user = db.query(User).filter(User.id == patient_profile.user_id).first()
        
        appointment_dict = {
            "id": appointment.id,
            "doctor_id": appointment.doctor_id,
            "patient_id": appointment.patient_id,
            "start_time": appointment.start_time,
            "end_time": appointment.end_time,
            "appointment_date": appointment.appointment_date,
            "status": appointment.status,
            "reason": appointment.reason,
            "notes": appointment.notes,
            "patient": {
                "id": patient_profile.id,
                "first_name": patient_user.first_name,
                "last_name": patient_user.last_name,
                "gender": patient_profile.gender,
                "date_of_birth": patient_profile.date_of_birth,
                "phone": patient_user.phone
            }
        }
        result.append(appointment_dict)
    
    return result

@router.get("/appointments/past", response_model=List[AppointmentWithDoctorOut])
def get_past_appointments_endpoint(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get all past appointments for the current user.
    Past appointments are those where:
    1. The appointment date is earlier than today, OR
    2. The appointment is today but the end_time has already passed
    
    All appointment statuses will be included in the results.
    """
    if current_user.role not in [UserRole.DOCTOR, UserRole.PATIENT, UserRole.ADMIN]:
        raise HTTPException(
            status_code=403,
            detail="Only doctors, patients, and admins can view past appointments."
        )
    
    appointments = get_past_appointments(db, current_user)
    print(f"Total appointments fetched: {len(appointments)}")
    
    # Prepare result list with proper format for both doctor and patient users
    result = []
    for appointment in appointments:
        try:
            # Get doctor details using the relationship that's already loaded
            doctor_profile = appointment.doctor
            
            # Skip if there's no doctor profile
            if not doctor_profile:
                print(f"Skipping appointment ID={appointment.id}: No doctor profile")
                continue
            
            # Explicitly load user if needed
            if not hasattr(doctor_profile, 'user') or doctor_profile.user is None:
                if doctor_profile.user_id is None:
                    print(f"Skipping appointment ID={appointment.id}: Doctor has no user_id")
                    continue
                doctor_user = db.query(User).filter(User.id == doctor_profile.user_id).first()
                if not doctor_user:
                    print(f"Skipping appointment ID={appointment.id}: Could not find doctor user with ID={doctor_profile.user_id}")
                    continue
            else:
                doctor_user = doctor_profile.user
                if not doctor_user:
                    print(f"Skipping appointment ID={appointment.id}: Doctor user is None")
                    continue
            
            # Get patient details
            patient_profile = appointment.patient
            patient_user = patient_profile.user if patient_profile and hasattr(patient_profile, 'user') else None
            if patient_profile and not patient_user and patient_profile.user_id:
                patient_user = db.query(User).filter(User.id == patient_profile.user_id).first()
            
            # Construct doctor details
            doctor_details = DoctorDetails(
                id=doctor_profile.id,
                first_name=doctor_user.first_name,
                last_name=doctor_user.last_name,
                specialty=doctor_profile.specialty,
                phone=doctor_user.phone,
                address=doctor_profile.address,
                city=doctor_profile.city,
                state=doctor_profile.state,
                postal_code=doctor_profile.postal_code,
                country=doctor_profile.country
            )
            
            # Construct patient details if available
            patient_details = None
            if patient_profile and patient_user:
                patient_details = PatientDetails(
                    id=patient_profile.id,
                    first_name=patient_user.first_name,
                    last_name=patient_user.last_name,
                    gender=patient_profile.gender,
                    date_of_birth=patient_profile.date_of_birth,
                    phone=patient_user.phone
                )
            
            # Create appointment dictionary and add to results
            appointment_dict = {
                "id": appointment.id,
                "doctor_id": appointment.doctor_id,
                "patient_id": appointment.patient_id,
                "start_time": appointment.start_time,
                "end_time": appointment.end_time,
                "appointment_date": appointment.appointment_date,
                "status": appointment.status,
                "reason": appointment.reason,
                "notes": appointment.notes,
                "doctor": doctor_details,
                "patient": patient_details
            }
            result.append(appointment_dict)
            print(f"Added appointment ID={appointment.id} with doctor={doctor_user.first_name} {doctor_user.last_name}")
        except Exception as e:
            # Log the error but continue processing other appointments
            print(f"Error processing appointment {appointment.id}: {str(e)}")
            continue
    
    print(f"Returning {len(result)} appointments")
    for idx, appt in enumerate(result):
        print(f"{idx+1}. Appt ID={appt['id']}, Date={appt['appointment_date']}, Doctor={appt['doctor'].first_name} {appt['doctor'].last_name}")
    
    return result