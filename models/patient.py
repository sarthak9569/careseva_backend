from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class PatientBase(BaseModel):
    pid: Optional[str] = None # Unique Patient ID: CS-P-10001
    name: str
    dob: Optional[str] = None # YYYY-MM-DD
    age: int
    gender: str # Male, Female, Other
    phone: str
    department_id: Optional[str] = None
    department_name: Optional[str] = None
    last_visit: Optional[str] = None # YYYY-MM-DD
    registration_source: str = "DIRECT_WALKIN" # DIRECT_WALKIN or CARESEVA_APP
    hospital_id: str
    appointment_id: Optional[str] = None
    token_number: Optional[int] = None

class PatientCreate(BaseModel):
    name: str
    dob: Optional[str] = None
    age: Optional[int] = None
    gender: str
    phone: str
    department_id: Optional[str] = None
    department_name: Optional[str] = None
    last_visit: Optional[str] = None
    registration_source: str = "DIRECT_WALKIN"
    hospital_id: str

class PatientInDB(PatientBase):
    id: str
    created_at: datetime
    updated_at: datetime

class PatientResponse(PatientBase):
    id: str
    created_at: datetime
