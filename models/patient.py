from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class PatientBase(BaseModel):
    pid: Optional[str] = None # Unique Patient ID: CS-P-10001
    name: str
    dob: Optional[str] = None # YYYY-MM-DD
    age: Optional[int] = 0
    gender: Optional[str] = "-" # Male, Female, Other
    phone: str
    email: Optional[str] = None
    blood_group: Optional[str] = None
    address: Optional[str] = None
    department_id: Optional[str] = None
    department_name: Optional[str] = None
    last_visit: Optional[str] = None # YYYY-MM-DD
    registration_source: str = "DIRECT_WALKIN" # DIRECT_WALKIN or CARESEVA_APP
    hospital_id: str
    appointment_id: Optional[str] = None
    token_number: Optional[int] = None
    payment_status: str = "DONE" # DONE or PENDING
    payment_option: Optional[str] = "full" # full or advance
    total_fee: Optional[float] = 500.0
    paid_amount: Optional[float] = 500.0
    remaining_amount: Optional[float] = 0.0

class PatientCreate(BaseModel):
    name: str
    dob: Optional[str] = None
    age: Optional[int] = None
    gender: str
    phone: str
    email: Optional[str] = None
    blood_group: Optional[str] = None
    address: Optional[str] = None
    department_id: Optional[str] = None
    department_name: Optional[str] = None
    last_visit: Optional[str] = None
    registration_source: str = "DIRECT_WALKIN"
    hospital_id: str
    payment_status: Optional[str] = "DONE"
    payment_option: Optional[str] = "full"
    total_fee: Optional[float] = 500.0
    paid_amount: Optional[float] = 500.0
    remaining_amount: Optional[float] = 0.0

class PatientInDB(PatientBase):
    id: str
    created_at: datetime
    updated_at: datetime

class PatientResponse(PatientBase):
    id: str
    created_at: datetime
    updated_at: Optional[datetime] = None
