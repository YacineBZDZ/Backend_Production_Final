# services/availability.py

from datetime import datetime, time, date  # added date
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
from fastapi import HTTPException, status  # added imports

from models.user import DoctorAvailability, DoctorProfile, UserRole, User, Appointment  # add Appointment
from database.session import get_db


class AvailabilityService:
    """
    Service for managing doctor availability schedules
    """

    @staticmethod
    def get_doctor_availability(db: Session, doctor_id: int) -> List[DoctorAvailability]:
        """
        Get all availability slots for a specific doctor
        """
        return db.query(DoctorAvailability).filter(DoctorAvailability.doctor_id == doctor_id).all()

    @staticmethod
    def get_available_slots_by_date(db: Session, doctor_id: int, availability_date: date) -> List[DoctorAvailability]:
        """
        Get available time slots for a specific doctor on a particular date
        """
        return db.query(DoctorAvailability).filter(
            DoctorAvailability.doctor_id == doctor_id,
            DoctorAvailability.availability_date == availability_date,
        ).all()

    @staticmethod
    def create_availability_slot(
            db: Session,
            doctor_id: int,
            availability_date: date,
            start_time: time,
            end_time: time,
            is_available: bool = True,
            start_time2: Optional[time] = None,
            end_time2: Optional[time] = None,
            start_time3: Optional[time] = None,
            end_time3: Optional[time] = None,
    ) -> DoctorAvailability:
        """
        Create a new availability slot for a doctor on a specific date
        """
        try:
            # Check if doctor exists
            doctor = db.query(DoctorProfile).filter(DoctorProfile.id == doctor_id).first()
            if not doctor:
                raise ValueError(f"Doctor with ID {doctor_id} not found")

            # Validate time range
            if start_time >= end_time:
                raise ValueError("Start time must be before end time")

            # Validate optional intervals if provided
            intervals = [(start_time, end_time)]
            for idx, pair in enumerate([(start_time2, end_time2), (start_time3, end_time3)], start=2):
                st, et = pair
                if st is not None or et is not None:
                    if st is None or et is None or st >= et:
                        raise ValueError(f"Interval {idx}: both start and end time must be provided and start must be before end")
                    intervals.append((st, et))

            # Check for overlapping intervals within the same record
            sorted_intervals = sorted(intervals, key=lambda x: x[0])
            for i in range(1, len(sorted_intervals)):
                if sorted_intervals[i][0] < sorted_intervals[i-1][1]:
                    raise ValueError("Provided intervals overlap with each other")

            # Check for overlapping availability slots
            overlapping = db.query(DoctorAvailability).filter(
                DoctorAvailability.doctor_id == doctor_id,
                DoctorAvailability.availability_date == availability_date,
                or_(
                    and_(start_time <= DoctorAvailability.start_time, end_time > DoctorAvailability.start_time),
                    and_(start_time < DoctorAvailability.end_time, end_time >= DoctorAvailability.end_time),
                    and_(start_time >= DoctorAvailability.start_time, end_time <= DoctorAvailability.end_time)
                )
            ).first()

            if overlapping:
                raise ValueError("This time slot overlaps with an existing availability slot")

            # Create new availability slot
            new_slot = DoctorAvailability(
                doctor_id=doctor_id,
                availability_date=availability_date,
                start_time=start_time,
                end_time=end_time,
                is_available=is_available,
                start_time2=start_time2,
                end_time2=end_time2,
                start_time3=start_time3,
                end_time3=end_time3
            )

            db.add(new_slot)
            db.commit()
            db.refresh(new_slot)
            return new_slot
        except Exception as e:
            import traceback
            traceback.print_exc()  # temporarily log full error details
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error creating availability slot: {e}"
            )

    @staticmethod
    def update_availability_slot(
            db: Session,
            slot_id: int,
            availability_date: Optional[date] = None,
            start_time: Optional[time] = None,
            end_time: Optional[time] = None,
            is_available: Optional[bool] = None,
            start_time2: Optional[time] = None,
            end_time2: Optional[time] = None,
            start_time3: Optional[time] = None,
            end_time3: Optional[time] = None
    ) -> DoctorAvailability:
        """
        Update an existing availability slot
        """
        slot = db.query(DoctorAvailability).filter(DoctorAvailability.id == slot_id).first()
        if not slot:
            raise ValueError(f"Availability slot with ID {slot_id} not found")

        new_st = start_time if start_time is not None else slot.start_time
        new_et = end_time if end_time is not None else slot.end_time
        if new_st >= new_et:
            raise ValueError("Start time must be before end time")

        # Prepare intervals from updated values (using existing if not provided)
        intervals = [(new_st, new_et)]
        for attr_pair, default_st, default_et in zip(
            [(start_time2, end_time2), (start_time3, end_time3)],
            [slot.start_time2, slot.start_time3],
            [slot.end_time2, slot.end_time3]
        ):
            st_new = attr_pair[0] if attr_pair[0] is not None else default_st
            et_new = attr_pair[1] if attr_pair[1] is not None else default_et
            if st_new is not None or et_new is not None:
                if st_new is None or et_new is None or st_new >= et_new:
                    raise ValueError("All provided optional intervals must have both times and start must be before end")
                intervals.append((st_new, et_new))

        sorted_intervals = sorted(intervals, key=lambda x: x[0])
        for i in range(1, len(sorted_intervals)):
            if sorted_intervals[i][0] < sorted_intervals[i-1][1]:
                raise ValueError("Updated intervals overlap with each other")

        # Update fields
        if availability_date is not None:
            slot.availability_date = availability_date
        if start_time is not None:
            slot.start_time = start_time
        if end_time is not None:
            slot.end_time = end_time
        if is_available is not None:
            slot.is_available = is_available
        if start_time2 is not None:
            slot.start_time2 = start_time2
        if end_time2 is not None:
            slot.end_time2 = end_time2
        if start_time3 is not None:
            slot.start_time3 = start_time3
        if end_time3 is not None:
            slot.end_time3 = end_time3

        # Check for overlapping slots (excluding this slot)
        overlapping = db.query(DoctorAvailability).filter(
            DoctorAvailability.doctor_id == slot.doctor_id,
            DoctorAvailability.availability_date == slot.availability_date,
            DoctorAvailability.id != slot_id,
            or_(
                and_(new_st <= DoctorAvailability.start_time, new_et > DoctorAvailability.start_time),
                and_(new_st < DoctorAvailability.end_time, new_et >= DoctorAvailability.end_time),
                and_(new_st >= DoctorAvailability.start_time, new_et <= DoctorAvailability.end_time)
            )
        ).first()

        if overlapping:
            raise ValueError("This time slot overlaps with an existing availability slot")

        db.commit()
        db.refresh(slot)
        return slot

    @staticmethod
    def delete_availability_slot(db: Session, slot_id: int) -> bool:
        """
        Delete an availability slot
        """
        slot = db.query(DoctorAvailability).filter(DoctorAvailability.id == slot_id).first()
        if not slot:
            raise ValueError(f"Availability slot with ID {slot_id} not found")

        db.delete(slot)
        db.commit()
        return True

    @staticmethod
    def get_available_doctors_by_date_time(
            db: Session,
            availability_date: date,
            start_time: time,
            end_time: time
    ) -> List[User]:
        """
        Find doctors available on a specific date during a given time slot
        """
        if start_time >= end_time:
            raise ValueError("Start time must be before end time")

        # Check if any of the intervals satisfy the requested start/end times
        condition = or_(
            and_(DoctorAvailability.start_time <= start_time, DoctorAvailability.end_time >= end_time),
            and_(DoctorAvailability.start_time2 != None, DoctorAvailability.start_time2 <= start_time, DoctorAvailability.end_time2 >= end_time),
            and_(DoctorAvailability.start_time3 != None, DoctorAvailability.start_time3 <= start_time, DoctorAvailability.end_time3 >= end_time),
        )

        # Get doctor users with availability during the specified time
        available_doctors = db.query(User).join(DoctorProfile).join(DoctorAvailability).filter(
            User.role == UserRole.DOCTOR,
            DoctorAvailability.availability_date == availability_date,
            DoctorAvailability.is_available == True,
            condition
        ).all()

        return available_doctors

    @classmethod  # Changed from @staticmethod for debugging purposes
    def get_public_doctor_availabilities(cls, db: Session, doctor_id: int):
        """
        Get both availability slots and appointments for a doctor
        """
        try:
            availabilities = db.query(DoctorAvailability).filter(
                DoctorAvailability.doctor_id == doctor_id
            ).all()
            
            appointments = db.query(Appointment).filter(
                Appointment.doctor_id == doctor_id
            ).all()
            
            return {
                "availabilities": availabilities,
                "appointments": appointments
            }
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise ValueError(f"Error getting public doctor data: {str(e)}")