from datetime import datetime, time, date
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import or_, func
from models.user import Appointment, DoctorAvailability, User, UserRole, DoctorProfile, PatientProfile

# Fix the import to use the proper path
from ws import manager
# Alternative import if the above doesn't work: 
# from websockets.connection_manager import manager
from ws.notifications import create_appointment_created_notification, create_appointment_status_changed_notification
import asyncio

def create_appointment(
        session: Session, doctor_id: int, patient_id: int, 
        start_time: time, end_time: time,              # Accept time only
        appointment_date: date,                         # Separate date field
        reason: str = None, notes: str = None):
    # Remove seconds and microseconds from provided times
    start_time = start_time.replace(second=0, microsecond=0)
    end_time = end_time.replace(second=0, microsecond=0)
    
    # Check for existing appointment on the same date with overlapping time
    conflict = session.query(Appointment).filter(
        Appointment.doctor_id == doctor_id,
        Appointment.appointment_date == appointment_date,
        Appointment.start_time < end_time,
        Appointment.end_time > start_time,
    ).first()
    if conflict:
        raise Exception("Appointment time overlaps with an existing appointment on the same date.")
    
    def overlaps(s1: time, e1: time, s2: time, e2: time) -> bool:
        return s1 < e2 and s2 < e1
    # Retrieve doctor's availability for the given appointment_date only
    availability = session.query(DoctorAvailability).filter(
        DoctorAvailability.doctor_id == doctor_id,
        DoctorAvailability.availability_date == appointment_date,
    ).first()
    if availability:
        # Removed overall availability check:
        # if not availability.is_available:
        #    raise Exception("Doctor is marked as not available on the selected date.")
        
        req_start = start_time
        req_end = end_time
        if not availability.is_available and availability.start_time and availability.end_time:
            if overlaps(req_start, req_end,
                        availability.start_time.replace(second=0, microsecond=0),
                        availability.end_time.replace(second=0, microsecond=0)):
                raise Exception("Requested time collides with doctor's unavailability (primary slot).")
        if not availability.is_available and availability.start_time2 and availability.end_time2:
            if overlaps(req_start, req_end,
                        availability.start_time2.replace(second=0, microsecond=0),
                        availability.end_time2.replace(second=0, microsecond=0)):
                raise Exception("Requested time collides with doctor's unavailability (secondary slot).")
        if not availability.is_available and availability.start_time3 and availability.end_time3:
            if overlaps(req_start, req_end,
                        availability.start_time3.replace(second=0, microsecond=0),
                        availability.end_time3.replace(second=0, microsecond=0)):
                raise Exception("Requested time collides with doctor's unavailability (tertiary slot).")
    
    new_appointment = Appointment(
        doctor_id=doctor_id,
        patient_id=patient_id,
        start_time=start_time,
        end_time=end_time,
        appointment_date=appointment_date,
        status="pending",
        reason=reason,
        notes=notes
    )
    session.add(new_appointment)
    try:
        session.commit()
        session.refresh(new_appointment)
        
        # Get doctor and patient details for notification
        doctor = session.query(DoctorProfile).filter(DoctorProfile.id == doctor_id).options(
            selectinload(DoctorProfile.user)
        ).first()
        
        patient = session.query(PatientProfile).filter(PatientProfile.id == patient_id).options(
            selectinload(PatientProfile.user)
        ).first()
        
        doctor_name = f"{doctor.user.first_name} {doctor.user.last_name}"
        patient_name = f"{patient.user.first_name} {patient.user.last_name}"
        
        # Create appointment data for notification
        appointment_data = {
            "id": new_appointment.id,
            "doctor_id": doctor_id,
            "patient_id": patient_id,
            "start_time": start_time.isoformat() if isinstance(start_time, time) else start_time,
            "end_time": end_time.isoformat() if isinstance(end_time, time) else end_time,
            "appointment_date": appointment_date.isoformat() if isinstance(appointment_date, date) else appointment_date,
            "status": "pending",
            "reason": reason,
            "notes": notes
        }
        
        # Create notification payload
        notification = create_appointment_created_notification(
            appointment=appointment_data,
            doctor_name=doctor_name,
            patient_name=patient_name
        )
        
        # Send notifications to both doctor and patient
        affected_users = [
            str(doctor.user_id),
            str(patient.user_id)
        ]
        
        # Handle the WebSocket notification asynchronously but safely
        try:
            import asyncio
            
            # Check if there's a running event loop we can use
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # If there's a running loop, use it to create a task
                    loop.create_task(manager.send_appointment_notification(
                        notification, 
                        "new",
                        affected_users
                    ))
                else:
                    # If no running loop but one exists, run the coroutine 
                    # with a short timeout to avoid blocking
                    asyncio.run_coroutine_threadsafe(
                        manager.send_appointment_notification(notification, "new", affected_users), 
                        loop
                    )
            except RuntimeError:
                # If no event loop exists or it can't be accessed, 
                # log this but don't block the appointment creation
                print("No running event loop for WebSocket notification. Notification will be skipped.")
        except Exception as ws_error:
            # If any WebSocket error occurs, log it but don't fail the appointment
            print(f"WebSocket notification error: {ws_error}")
            # The appointment should still be considered successful
            
    except IntegrityError:
        session.rollback()
        raise Exception("Failed to create appointment due to a database error.")
    
    return new_appointment

def create_appointment_by_patient_fullname(
    session: Session,
    doctor_id: int,
    patient_full_name: str,
    start_time: time,
    end_time: time,
    appointment_date: date,
    reason: str = None,
    notes: str = None
):
    # Remove seconds and microseconds from provided times
    start_time = start_time.replace(second=0, microsecond=0)
    end_time = end_time.replace(second=0, microsecond=0)
    
    # Find the patient by concatenated full name (case sensitive)
    patient = session.query(PatientProfile).join(User).filter(
        func.concat(User.first_name, ' ', User.last_name) == patient_full_name
    ).first()
    if not patient:
        raise Exception("Patient with given full name not found.")
    patient_id = patient.user_id

    # Filtering logic: check for existing appointment conflicts
    conflict = session.query(Appointment).filter(
        Appointment.doctor_id == doctor_id,
        Appointment.appointment_date == appointment_date,
        Appointment.start_time < end_time,
        Appointment.end_time > start_time,
    ).first()
    if conflict:
        raise Exception("Appointment time overlaps with an existing appointment on the same date.")
    
    # Filtering logic: check doctor's availability
    def overlaps(s1: time, e1: time, s2: time, e2: time) -> bool:
        return s1 < e2 and s2 < e1
    availability = session.query(DoctorAvailability).filter(
        DoctorAvailability.doctor_id == doctor_id,
        DoctorAvailability.availability_date == appointment_date,
    ).first()
    if availability:
        req_start = start_time
        req_end = end_time
        if not availability.is_available and availability.start_time and availability.end_time:
            if overlaps(req_start, req_end,
                        availability.start_time.replace(second=0, microsecond=0),
                        availability.end_time.replace(second=0, microsecond=0)):
                raise Exception("Requested time collides with doctor's unavailability (primary slot).")
        if not availability.is_available and availability.start_time2 and availability.end_time2:
            if overlaps(req_start, req_end,
                        availability.start_time2.replace(second=0, microsecond=0),
                        availability.end_time2.replace(second=0, microsecond=0)):
                raise Exception("Requested time collides with doctor's unavailability (secondary slot).")
        if not availability.is_available and availability.start_time3 and availability.end_time3:
            if overlaps(req_start, req_end,
                        availability.start_time3.replace(second=0, microsecond=0),
                        availability.end_time3.replace(second=0, microsecond=0)):
                raise Exception("Requested time collides with doctor's unavailability (tertiary slot).")
    
    new_appointment = Appointment(
        doctor_id=doctor_id,
        patient_id=patient_id,
        start_time=start_time,
        end_time=end_time,
        appointment_date=appointment_date,
        status="confirmed",  # Changed from "pending" to "confirmed"
        reason=reason,
        notes=notes
    )
    session.add(new_appointment)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise Exception("Failed to create appointment due to a database error.")
    return new_appointment

async def update_appointment_status(session: Session, appointment_id: int, new_status: str, doctor_id: int):
    # Retrieve the appointment ensuring the doctor is authorized to update it
    appointment = session.query(Appointment).filter(
        Appointment.id == appointment_id,
        Appointment.doctor_id == doctor_id
    ).first()
    if not appointment:
        raise Exception("Appointment not found or unauthorized")
    
    # Updated list of allowed status values - added "undetermined_pending"
    allowed_statuses = ["confirmed", "pending", "done", "cancelled", "absent", "undetermined_confirmed", "undetermined_pending"]
    if new_status not in allowed_statuses:
        raise Exception(f"Invalid status. Allowed: {', '.join(allowed_statuses)}.")
    
    old_status = appointment.status
    
    appointment.status = new_status
    # Mark appointment as updated and record update timestamp
    appointment.is_updated = True
    appointment.update_date = datetime.now()
    
    try:
        session.commit()
        session.refresh(appointment)
        
        # Get doctor and patient details for notification
        doctor = session.query(DoctorProfile).filter(DoctorProfile.id == doctor_id).options(
            selectinload(DoctorProfile.user)
        ).first()
        
        patient = session.query(PatientProfile).filter(PatientProfile.id == appointment.patient_id).options(
            selectinload(PatientProfile.user)
        ).first()
        
        doctor_name = f"{doctor.user.first_name} {doctor.user.last_name}"
        patient_name = f"{patient.user.first_name} {patient.user.last_name}"
        
        # Create appointment data for notification
        appointment_data = {
            "id": appointment.id,
            "doctor_id": doctor_id,
            "patient_id": appointment.patient_id,
            "start_time": appointment.start_time,
            "end_time": appointment.end_time,
            "appointment_date": appointment.appointment_date,
            "status": new_status,
            "reason": appointment.reason,
            "notes": appointment.notes
        }
        
        # Create notification payload
        notification = create_appointment_status_changed_notification(
            appointment=appointment_data,
            old_status=old_status,
            new_status=new_status,
            changed_by="doctor",
            doctor_name=doctor_name,
            patient_name=patient_name
        )
        
        # Send notifications to both doctor and patient
        affected_users = [
            str(doctor.user_id),
            str(patient.user_id)
        ]
        
           # Use await instead of creating a separate task
        await manager.send_appointment_notification(
            notification, 
            "status_change",
            affected_users
        )
    except Exception as e:
        session.rollback()
        raise Exception("Failed to update appointment status: " + str(e))
        
    return appointment

def delete_appointment(session: Session, appointment_id: int, current_user: User):
    # Allow deletion if the current user is the doctor, patient, or admin linked to the appointment
    if current_user.role == UserRole.DOCTOR:
        appointment = session.query(Appointment).filter(
            Appointment.id == appointment_id,
            Appointment.doctor_id == current_user.doctor_profile.id
        ).first()
    elif current_user.role == UserRole.PATIENT:
        appointment = session.query(Appointment).filter(
            Appointment.id == appointment_id,
            Appointment.patient_id == current_user.patient_profile.id
        ).first()
    elif current_user.role == UserRole.ADMIN:
        appointment = session.query(Appointment).filter(
            Appointment.id == appointment_id
        ).first()
    else:
        raise Exception("Not authorized to delete appointment")
    
    if not appointment:
        raise Exception("Appointment not found")
    
    session.delete(appointment)
    try:
        session.commit()
    except Exception as e:
        session.rollback()
        raise Exception("Failed to delete appointment: " + str(e))
    return True

def update_appointment_details(session: Session, appointment: Appointment, update_data: dict) -> Appointment:
    from datetime import datetime  # Ensure datetime is imported
    # Parse new values or fallback to existing ones
    new_doctor_id = update_data.get("doctor_id", appointment.doctor_id)
    new_patient_id = update_data.get("patient_id", appointment.patient_id)
    new_appointment_date = appointment.appointment_date
    if "appointment_date" in update_data:
        new_appointment_date = datetime.strptime(update_data["appointment_date"], "%Y-%m-%d").date()
    new_start_time = appointment.start_time
    if "start_time" in update_data:
        new_start_time = datetime.strptime(update_data["start_time"], "%H:%M:%S").time()
    new_end_time = appointment.end_time
    if "end_time" in update_data:
        new_end_time = datetime.strptime(update_data["end_time"], "%H:%M:%S").time()

    # Conflict check (excluding current appointment)
    conflict = session.query(Appointment).filter(
        Appointment.id != appointment.id,
        Appointment.doctor_id == new_doctor_id,
        Appointment.appointment_date == new_appointment_date,
        Appointment.start_time < new_end_time,
        Appointment.end_time > new_start_time,
    ).first()
    if conflict:
        raise Exception("Updated appointment conflicts with an existing appointment.")

    # Only check doctor's availability if any date/time fields are updated
    if any(key in update_data for key in ["appointment_date", "start_time", "end_time"]):
        availability = session.query(DoctorAvailability).filter(
            DoctorAvailability.doctor_id == new_doctor_id,
            DoctorAvailability.availability_date == new_appointment_date,
        ).first()
        if availability:
            def overlaps(s1: time, e1: time, s2: time, e2: time) -> bool:
                return s1 < e2 and s2 < e1
            req_start = new_start_time
            req_end = new_end_time
            if not availability.is_available and availability.start_time and availability.end_time:
                if overlaps(req_start, req_end,
                            availability.start_time.replace(second=0, microsecond=0),
                            availability.end_time.replace(second=0, microsecond=0)):
                    raise Exception("Updated appointment collides with doctor's unavailability (primary slot).")
            if not availability.is_available and availability.start_time2 and availability.end_time2:
                if overlaps(req_start, req_end,
                            availability.start_time2.replace(second=0, microsecond=0),
                            availability.end_time2.replace(second=0, microsecond=0)):
                    raise Exception("Updated appointment collides with doctor's unavailability (secondary slot).")
            if not availability.is_available and availability.start_time3 and availability.end_time3:
                if overlaps(req_start, req_end,
                            availability.start_time3.replace(second=0, microsecond=0),
                            availability.end_time3.replace(second=0, microsecond=0)):
                    raise Exception("Updated appointment collides with doctor's unavailability (tertiary slot).")
        # If no availability record exists, allow the update without raising an exception.

    # Apply updates to appointment fields
    appointment.doctor_id = new_doctor_id
    appointment.patient_id = new_patient_id
    appointment.appointment_date = new_appointment_date
    appointment.start_time = new_start_time
    appointment.end_time = new_end_time
    if "reason" in update_data:
        appointment.reason = update_data["reason"]
    if "notes" in update_data:
        appointment.notes = update_data["notes"]

    # Mark appointment as updated and record the latest update date and time
    appointment.is_updated = True
    appointment.update_date = datetime.now()

    try:
        session.commit()
    except Exception as e:
        session.rollback()
        raise Exception("Failed to update appointment: " + str(e))
    session.refresh(appointment)
    return appointment

def search_appointments_by_name(session: Session, name: str):
    appointments = session.query(Appointment).filter(
        or_(
            Appointment.doctor.has(
                DoctorProfile.user.has(
                    func.concat(User.first_name, ' ', User.last_name).like(f"%{name}%")
                )
            ),
            Appointment.patient.has(
                PatientProfile.user.has(
                    func.concat(User.first_name, ' ', User.last_name).like(f"%{name}%")
                )
            )
        )
    ).all()
    return appointments

def get_appointments_by_date(session: Session, doctor_id: int, appointment_date: date):
    return session.query(Appointment).filter(
        Appointment.doctor_id == doctor_id,
        Appointment.appointment_date == appointment_date
    ).all()

def get_past_appointments(session: Session, user: User):
    """
    Get past appointments for the current user (doctor, patient, or admin).
    Past appointments are those with an appointment_date earlier than today.
    """
    from datetime import date
    today = date.today()
    
    if user.role == UserRole.DOCTOR:
        return session.query(Appointment).filter(
            Appointment.doctor_id == user.doctor_profile.id,
            Appointment.appointment_date < today
        ).order_by(Appointment.appointment_date.desc()).all()
    
    elif user.role == UserRole.PATIENT:
        return session.query(Appointment).filter(
            Appointment.patient_id == user.patient_profile.id,
            Appointment.appointment_date < today
        ).order_by(Appointment.appointment_date.desc()).all()
    
    elif user.role == UserRole.ADMIN:
        # Admins can see all past appointments
        return session.query(Appointment).filter(
            Appointment.appointment_date < today
        ).order_by(Appointment.appointment_date.desc()).all()
    
    # For any other roles (should not happen with the endpoint check)
    return []
