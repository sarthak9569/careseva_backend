from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class QueueBase(BaseModel):
    hospital_id: str
    department_id: str
    doctor_id: str
    status: str = "ACTIVE" # ACTIVE, PAUSED, CLOSED

class QueueCreate(QueueBase):
    pass

class QueueInDB(QueueBase):
    id: str
    current_token: int = 0
    total_tokens: int = 0
    created_at: datetime
    updated_at: datetime

class QueueResponse(QueueBase):
    id: str
    current_token: int
    total_tokens: int

# Queue Entry Model (The patient's position in queue)
class QueueEntryBase(BaseModel):
    queue_id: str
    patient_id: str
    token_number: int
    status: str = "WAITING" # WAITING, CALLED, IN_CONSULTATION, COMPLETED, CANCELLED, NO_SHOW

class QueueEntryCreate(BaseModel):
    queue_id: str
    patient_id: str

class QueueEntryInDB(QueueEntryBase):
    id: str
    hospital_id: str
    department_id: str
    doctor_id: str
    created_at: datetime
    updated_at: datetime

class QueueEntryResponse(QueueEntryBase):
    id: str
    hospital_id: str
    department_id: str
    doctor_id: str
    created_at: datetime

# Appointment Model
class AppointmentBase(BaseModel):
    hospital_id: str
    department_id: str
    doctor_id: str
    patient_id: str
    booking_for: str = "myself" # 'myself' or 'someone_else'
    patient_name: Optional[str] = None
    patient_age: Optional[int] = None
    patient_gender: Optional[str] = None
    patient_phone: Optional[str] = None
    appointment_date: str # YYYY-MM-DD
    status: str = "BOOKED" # BOOKED, COMPLETED, CANCELLED

class AppointmentCreate(AppointmentBase):
    pass

class AppointmentInDB(AppointmentBase):
    id: str
    created_at: datetime
    updated_at: datetime

class AppointmentResponse(AppointmentBase):
    id: str
    created_at: datetime
