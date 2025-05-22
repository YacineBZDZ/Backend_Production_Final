from datetime import datetime, date, time, timedelta
import asyncio
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import and_, or_, update
from sqlalchemy.orm import selectinload
from typing import List, Dict, Any

from models.user import Appointment, User, DoctorProfile, PatientProfile
from ws.connection_manager import manager
from ws.notifications import create_appointment_status_changed_notification
from database.session import get_async_db_context  # Use the context manager version

logger = logging.getLogger(__name__)

async def update_past_appointments():
    """
    Background task to automatically update appointment statuses
    for appointments that have passed but weren't updated by the doctor.
    
    Runs every 15 minutes.
    """
    while True:
        try:
            # Use async with for context manager
            async with get_async_db_context() as session:
                await process_past_appointments(session)
        except Exception as e:
            logger.error(f"Error in appointment update task: {str(e)}", exc_info=True)
        
        # Sleep for 15 minutes
        await asyncio.sleep(15 * 60)
        
async def process_past_appointments(session: AsyncSession):
    """Process all appointments that need status updates"""
    today = date.today()
    now = datetime.now().time()
    
    # Find confirmed appointments that have passed
    confirmed_stmt = select(Appointment).where(
        and_(
            Appointment.status == "confirmed",
            or_(
                Appointment.appointment_date < today,
                and_(
                    Appointment.appointment_date == today,
                    Appointment.end_time < now
                )
            )
        )
    ).options(
        selectinload(Appointment.doctor).selectinload(DoctorProfile.user),
        selectinload(Appointment.patient).selectinload(PatientProfile.user)
    )
    
    confirmed_result = await session.execute(confirmed_stmt)
    confirmed_appointments = confirmed_result.scalars().all()
    
    # Process each appointment
    for appointment in confirmed_appointments:
        await update_appointment_status(
            session, 
            appointment, 
            "undetermined_confirmed", 
            "Automatically marked as undetermined (confirmed) as the appointment time has passed."
        )
    
    # Find pending appointments that have passed
    pending_stmt = select(Appointment).where(
        and_(
            Appointment.status == "pending",
            or_(
                Appointment.appointment_date < today,
                and_(
                    Appointment.appointment_date == today,
                    Appointment.end_time < now
                )
            )
        )
    ).options(
        selectinload(Appointment.doctor).selectinload(DoctorProfile.user),
        selectinload(Appointment.patient).selectinload(PatientProfile.user)
    )
    
    pending_result = await session.execute(pending_stmt)
    pending_appointments = pending_result.scalars().all()
    
    # Process each appointment
    for appointment in pending_appointments:
        await update_appointment_status(
            session, 
            appointment, 
            "undetermined_pending", 
            "Automatically marked as undetermined (pending) as the appointment time has passed."
        )
    
    await session.commit()

async def update_appointment_status(
    session: AsyncSession, 
    appointment: Appointment, 
    new_status: str, 
    reason: str
):
    """Update an appointment's status and send notifications"""
    old_status = appointment.status
    
    # Update the appointment
    appointment.status = new_status
    appointment.is_updated = True
    appointment.update_date = datetime.now()
    appointment.notes = appointment.notes + "\n" + reason if appointment.notes else reason
    
    # Get doctor and patient details for the notification
    # Add null checks for doctor and doctor.user
    if not appointment.doctor or not appointment.doctor.user:
        logger.warning(f"Skipping notification for appointment {appointment.id}: Missing doctor or user data.")
        return
        
    doctor_name = f"{appointment.doctor.user.first_name} {appointment.doctor.user.last_name}" 
    
    if not appointment.patient or not appointment.patient.user:
        logger.warning(f"Skipping notification for appointment {appointment.id}: Missing patient or user data.")
        return
        
    patient_name = f"{appointment.patient.user.first_name} {appointment.patient.user.last_name}"
    
    # Create appointment data for notification
    appointment_data = {
        "id": appointment.id,
        "doctor_id": appointment.doctor_id,
        "patient_id": appointment.patient_id,
        "start_time": appointment.start_time.strftime('%H:%M') if hasattr(appointment.start_time, 'strftime') else appointment.start_time,
        "end_time": appointment.end_time.strftime('%H:%M') if hasattr(appointment.end_time, 'strftime') else appointment.end_time,
        "appointment_date": appointment.appointment_date.isoformat() if hasattr(appointment.appointment_date, 'isoformat') else appointment.appointment_date,
        "status": new_status,
        "reason": appointment.reason,
        "notes": appointment.notes
    }
    
    # Create notification payload
    notification = create_appointment_status_changed_notification(
        appointment=appointment_data,
        old_status=old_status,
        new_status=new_status,
        changed_by="system",
        doctor_name=doctor_name,
        patient_name=patient_name,
        reason=reason
    )
    
    # Send notifications to both doctor and patient
    affected_users = [
        str(appointment.doctor.user_id),
        str(appointment.patient.user_id)
    ]
    
    await manager.send_appointment_notification(
        notification, 
        "auto_status_change",
        affected_users
    )
    
    logger.info(f"Updated appointment {appointment.id} from {old_status} to {new_status}")
