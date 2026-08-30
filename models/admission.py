from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class AdmissionBase(BaseModel):
    ipd_number: Optional[str] = None  # Unique IPD Admission Number e.g. IPD-2026-0001
    patient_id: Optional[str] = None  # Central Patient UHID/PID e.g. CS-P-10001
    patient_name: str
    patient_phone: str
    patient_age: int
    patient_gender: str  # Male, Female, Other
    patient_blood_group: Optional[str] = "Unknown"  # A+, A-, B+, B-, AB+, AB-, O+, O-, Unknown
    patient_address: Optional[str] = None
    hospital_id: str
    department_id: str
    department_name: Optional[str] = "General Medicine"
    doctor_id: Optional[str] = None
    doctor_name: Optional[str] = "Attending Physician"
    ward_type: str = "General Ward"  # General Ward, Semi-Private, Deluxe Private, ICU / CCU, Emergency Ward
    room_number: Optional[str] = None
    bed_number: str  # e.g., Bed 102-A, ICU-04
    admission_type: str = "PLANNED"  # EMERGENCY, PLANNED, DAYCARE, TRANSFER
    admission_date: Optional[str] = None  # YYYY-MM-DD
    admission_time: Optional[str] = None  # e.g. 10:30 AM
    provisional_diagnosis: str
    chief_complaints: Optional[str] = None
    kin_name: Optional[str] = None  # Next of Kin / Guardian
    kin_relation: Optional[str] = None  # Spouse, Father, Mother, Child, Sibling, Guardian
    kin_phone: Optional[str] = None
    payer_type: str = "CASH"  # CASH, TPA / INSURANCE, AYUSHMAN / GOVT SCHEME
    insurance_provider: Optional[str] = None
    advance_deposit: float = 0.0
    payment_status: str = "DONE"  # DONE, PARTIAL, PENDING
    discharge_date: Optional[str] = None
    discharge_summary: Optional[str] = None
    status: str = "ADMITTED"  # ADMITTED, ICU, OBSERVATION, DISCHARGED, TRANSFERRED
    notes: Optional[str] = None

class AdmissionCreate(BaseModel):
    patient_id: Optional[str] = None
    patient_name: str
    patient_phone: str
    patient_age: Optional[int] = None
    patient_dob: Optional[str] = None
    patient_gender: str
    patient_blood_group: Optional[str] = "Unknown"
    patient_address: Optional[str] = None
    hospital_id: str
    department_id: str
    department_name: Optional[str] = None
    doctor_id: Optional[str] = None
    doctor_name: Optional[str] = None
    ward_type: str = "General Ward"
    room_number: Optional[str] = None
    bed_number: str
    admission_type: str = "PLANNED"
    admission_date: Optional[str] = None
    provisional_diagnosis: str
    chief_complaints: Optional[str] = None
    kin_name: Optional[str] = None
    kin_relation: Optional[str] = None
    kin_phone: Optional[str] = None
    payer_type: str = "CASH"
    insurance_provider: Optional[str] = None
    advance_deposit: Optional[float] = 0.0
    payment_status: Optional[str] = "DONE"
    notes: Optional[str] = None

class AdmissionUpdate(BaseModel):
    ward_type: Optional[str] = None
    room_number: Optional[str] = None
    bed_number: Optional[str] = None
    status: Optional[str] = None
    doctor_id: Optional[str] = None
    doctor_name: Optional[str] = None
    discharge_date: Optional[str] = None
    discharge_summary: Optional[str] = None
    notes: Optional[str] = None
    payment_status: Optional[str] = None
    advance_deposit: Optional[float] = None

class AdmissionInDB(AdmissionBase):
    id: str
    created_at: datetime
    updated_at: datetime

class AdmissionResponse(AdmissionBase):
    id: str
    created_at: datetime
    updated_at: datetime
