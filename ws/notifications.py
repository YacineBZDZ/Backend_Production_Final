from typing import Dict, List, Optional, Union, Any
from pydantic import BaseModel, Field
from datetime import datetime, date, time
from enum import Enum

class NotificationType(str, Enum):
    APPOINTMENT_CREATED = "appointment_created"
    APPOINTMENT_UPDATED = "appointment_updated"
    APPOINTMENT_CANCELED = "appointment_canceled"
    APPOINTMENT_STATUS_CHANGED = "appointment_status_changed"
    APPOINTMENT_AUTO_STATUS_CHANGED = "appointment_auto_status_changed"
    SYSTEM_NOTIFICATION = "system_notification"

class AppointmentData(BaseModel):
    id: int
    doctor_id: int
    patient_id: int
    doctor_name: str
    patient_name: str
    start_time: str  # HH:MM format
    end_time: str    # HH:MM format
    appointment_date: str  # YYYY-MM-DD format
    status: str
    reason: Optional[str] = None
    notes: Optional[str] = None

class StatusChangeData(BaseModel):
    appointment_id: int
    old_status: str
    new_status: str
    changed_by: str  # "doctor", "patient", "admin", or "system"
    reason: Optional[str] = None

class NotificationPayload(BaseModel):
    type: NotificationType
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    appointment: Optional[AppointmentData] = None
    status_change: Optional[StatusChangeData] = None
    message: Optional[str] = None
    additional_data: Optional[Dict[str, Any]] = None

# Helper functions to create various notification payloads
def create_appointment_created_notification(appointment: Dict, doctor_name: str, patient_name: str) -> Dict:
    """Create a notification payload for a new appointment"""
    return NotificationPayload(
        type=NotificationType.APPOINTMENT_CREATED,
        appointment=AppointmentData(
            id=appointment["id"],
            doctor_id=appointment["doctor_id"],
            patient_id=appointment["patient_id"],
            doctor_name=doctor_name,
            patient_name=patient_name,
            start_time=appointment["start_time"].strftime("%H:%M") if isinstance(appointment["start_time"], time) else appointment["start_time"],
            end_time=appointment["end_time"].strftime("%H:%M") if isinstance(appointment["end_time"], time) else appointment["end_time"],
            appointment_date=appointment["appointment_date"].strftime("%Y-%m-%d") if isinstance(appointment["appointment_date"], date) else appointment["appointment_date"],
            status=appointment["status"],
            reason=appointment.get("reason"),
            notes=appointment.get("notes")
        ),
        message=f"New appointment created with {doctor_name} for {patient_name}"
    ).dict()

def create_appointment_status_changed_notification(
    appointment: Dict,
    old_status: str,
    new_status: str,
    changed_by: str,
    doctor_name: str,
    patient_name: str,
    reason: Optional[str] = None
) -> Dict:
    """Create a notification payload for an appointment status change"""
    return NotificationPayload(
        type=NotificationType.APPOINTMENT_STATUS_CHANGED if changed_by != "system" else NotificationType.APPOINTMENT_AUTO_STATUS_CHANGED,
        appointment=AppointmentData(
            id=appointment["id"],
            doctor_id=appointment["doctor_id"],
            patient_id=appointment["patient_id"],
            doctor_name=doctor_name,
            patient_name=patient_name,
            start_time=appointment["start_time"].strftime("%H:%M") if isinstance(appointment["start_time"], time) else appointment["start_time"],
            end_time=appointment["end_time"].strftime("%H:%M") if isinstance(appointment["end_time"], time) else appointment["end_time"],
            appointment_date=appointment["appointment_date"].strftime("%Y-%m-%d") if isinstance(appointment["appointment_date"], date) else appointment["appointment_date"],
            status=new_status,
            reason=appointment.get("reason"),
            notes=appointment.get("notes")
        ),
        status_change=StatusChangeData(
            appointment_id=appointment["id"],
            old_status=old_status,
            new_status=new_status,
            changed_by=changed_by,
            reason=reason
        ),
        message=f"Appointment status changed from {old_status} to {new_status}" + (f" by system automation" if changed_by == "system" else "")
    ).dict()
