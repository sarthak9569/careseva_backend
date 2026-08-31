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
    hop_id: Optional[str] = None
    
class HospitalCreate(HospitalBase):
    password: str

class HospitalUpdate(BaseModel):
    name: Optional[str] = None
    contact_person: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    specialties: Optional[List[str]] = None
    status: Optional[str] = None
    verification_status: Optional[str] = None
    hop_id: Optional[str] = None

class HospitalInDB(HospitalBase):
    id: str
    hashed_password: str
    status: str = "ACTIVE" # ACTIVE, INACTIVE, SUSPENDED
    verification_status: str = "PENDING" # PENDING, APPROVED, REJECTED
    created_at: datetime
    updated_at: datetime
    hop_id: str

class HospitalResponse(HospitalBase):
    id: str
    status: str
    verification_status: str
    created_at: datetime
    hop_id: str

# Department Models
class DepartmentBase(BaseModel):
    name: str
    specialty: str
    description: Optional[str] = None
    consultation_fee: float = 0.0
    status: str = "ACTIVE"

class DepartmentCreate(DepartmentBase):
    pass

class DepartmentUpdate(BaseModel):
    name: Optional[str] = None
    specialty: Optional[str] = None
    description: Optional[str] = None
    consultation_fee: Optional[float] = None
    status: Optional[str] = None

class DepartmentInDB(DepartmentBase):
    id: str
    hospital_id: str
    created_at: datetime

class DepartmentResponse(DepartmentBase):
    id: str
    hospital_id: str
    doctor_count: int = 0

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
    doc_id: Optional[str] = None

class DoctorCreate(DoctorBase):
    pass

class DoctorUpdate(BaseModel):
    name: Optional[str] = None
    specialization: Optional[str] = None
    qualification: Optional[str] = None
    experience_years: Optional[int] = None
    department_id: Optional[str] = None
    consultation_fee: Optional[float] = None
    status: Optional[str] = None
    description: Optional[str] = None
    doc_id: Optional[str] = None

class DoctorInDB(DoctorBase):
    id: str
    hospital_id: str
    created_at: datetime
    doc_id: str
    
class DoctorResponse(DoctorBase):
    id: str
    hospital_id: str
    activePatientsInQueue: int = 0
    rating: float = 4.5 # Default mockup until reviews are implemented
    doc_id: str
