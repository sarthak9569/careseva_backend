from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime

class HospitalBase(BaseModel):
    name: str
    facility_type: str = "Hospital" # Hospital, Clinic
    contact_person: str
    phone: str
    email: EmailStr
    address: str
    city: str
    state: str
    pincode: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    specialties: List[str] = []
    
class HospitalCreate(HospitalBase):
    password: str

class HospitalUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    specialties: Optional[List[str]] = None
    status: Optional[str] = None
    verification_status: Optional[str] = None

class HospitalInDB(HospitalBase):
    id: str
    hashed_password: str
    status: str = "ACTIVE" # ACTIVE, INACTIVE, SUSPENDED
    verification_status: str = "PENDING" # PENDING, APPROVED, REJECTED
    created_at: datetime
    updated_at: datetime

class HospitalResponse(HospitalBase):
    id: str
    status: str
    verification_status: str
    created_at: datetime

# Department Models
class DepartmentBase(BaseModel):
    name: str
    specialty: str
    description: Optional[str] = None
    status: str = "ACTIVE"

class DepartmentCreate(DepartmentBase):
    pass

class DepartmentInDB(DepartmentBase):
    id: str
    hospital_id: str
    created_at: datetime

class DepartmentResponse(DepartmentBase):
    id: str
    hospital_id: str

# Doctor Models
class DoctorBase(BaseModel):
    name: str
    specialization: str
    qualification: str
    experience_years: int
    department_id: str
    consultation_fee: float = 0.0
    status: str = "ACTIVE"
    description: Optional[str] = None

class DoctorCreate(DoctorBase):
    pass

class DoctorInDB(DoctorBase):
    id: str
    hospital_id: str
    created_at: datetime
    
class DoctorResponse(DoctorBase):
    id: str
    hospital_id: str
    activePatientsInQueue: int = 0
    rating: float = 4.5 # Default mockup until reviews are implemented
