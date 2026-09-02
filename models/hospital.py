from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime

class HospitalBase(BaseModel):
    name: str
    facility_type: str = "Hospital" # Hospital, Clinic, Nursing Home, Diagnostic Center
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
    
    # Statutory & Legal Credentials for CareSeva Em-panelment
    legal_entity_name: Optional[str] = None # e.g. "Apex Healthcare Pvt Ltd" or "Shri Ram Trust"
    clinical_establishment_no: Optional[str] = None # State CEA Reg Number
    gstin: Optional[str] = None # 15-digit GST Number
    pan_number: Optional[str] = None # 10-character PAN
    nabh_accreditation: Optional[str] = "NONE" # NONE, ENTRY_LEVEL, FULL_NABH, NABL, JCI
    nabh_valid_till: Optional[str] = None
    
    # Medical Governance & Clinical Leadership
    medical_superintendent_name: Optional[str] = None
    medical_superintendent_reg_no: Optional[str] = None # State Medical Council / NMC Reg #
    medical_superintendent_phone: Optional[str] = None
    medical_superintendent_email: Optional[str] = None
    
    # Authorized Signatory & Legal Contact
    authorized_signatory_name: Optional[str] = None
    authorized_signatory_designation: Optional[str] = None # Managing Director, Trustee, Superintendent
    authorized_signatory_phone: Optional[str] = None
    
    # Regulatory Permits & Capacity
    bmw_auth_number: Optional[str] = None # Bio-Medical Waste Authorization #
    pharmacy_license_no: Optional[str] = None # Form 20/21 Retail/Hospital Pharmacy License
    fire_noc_number: Optional[str] = None # Fire Safety NOC
    total_beds: Optional[int] = 0
    
    # CareSeva Digital Service Agreement (SLA) & Legal Indemnity
    sla_accepted: Optional[bool] = True
    sla_accepted_at: Optional[str] = None
    rejection_reason: Optional[str] = None
    verification_notes: Optional[str] = None
    
class HospitalCreate(HospitalBase):
    password: str

class HospitalUpdate(BaseModel):
    name: Optional[str] = None
    facility_type: Optional[str] = None
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
    legal_entity_name: Optional[str] = None
    clinical_establishment_no: Optional[str] = None
    gstin: Optional[str] = None
    pan_number: Optional[str] = None
    nabh_accreditation: Optional[str] = None
    nabh_valid_till: Optional[str] = None
    medical_superintendent_name: Optional[str] = None
    medical_superintendent_reg_no: Optional[str] = None
    medical_superintendent_phone: Optional[str] = None
    medical_superintendent_email: Optional[str] = None
    authorized_signatory_name: Optional[str] = None
    authorized_signatory_designation: Optional[str] = None
    authorized_signatory_phone: Optional[str] = None
    bmw_auth_number: Optional[str] = None
    pharmacy_license_no: Optional[str] = None
    fire_noc_number: Optional[str] = None
    total_beds: Optional[int] = None
    sla_accepted: Optional[bool] = None
    sla_accepted_at: Optional[str] = None
    rejection_reason: Optional[str] = None
    verification_notes: Optional[str] = None

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
