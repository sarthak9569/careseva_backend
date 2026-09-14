from pydantic import BaseModel, EmailStr
from typing import Optional

class UserCreate(BaseModel):
    name: str
    email: Optional[str] = None
    password: str = "careseva123"
    role: str = "patient" # 'patient', 'hospital_admin', 'doctor'
    phone: Optional[str] = None
    dob: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    blood_group: Optional[str] = None
    terms_accepted: Optional[bool] = False
    
    # Optional hospital fields if role is 'hospital_admin'
    hospital_name: Optional[str] = None
    hospital_code: Optional[str] = None
    hospital_id: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None

class UserLogin(BaseModel):
    email: Optional[str] = None
    password: Optional[str] = None

class UserInDB(BaseModel):
    name: str
    email: Optional[str] = None
    hashed_password: str
    role: str
    phone: Optional[str] = None
    pid: Optional[str] = None
    dob: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    blood_group: Optional[str] = None
    terms_accepted: Optional[bool] = True
    terms_accepted_at: Optional[str] = None
    otp_verified: Optional[bool] = True
    hospital_name: Optional[str] = None
    hospital_code: Optional[str] = None
    hospital_id: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None

class UserResponse(BaseModel):
    id: str
    name: str
    email: Optional[str] = None
    role: str
    phone: Optional[str] = None
    pid: Optional[str] = None
    dob: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    blood_group: Optional[str] = None
    terms_accepted: Optional[bool] = True
    terms_accepted_at: Optional[str] = None
    otp_verified: Optional[bool] = True
    hospital_id: Optional[str] = None
    hop_id: Optional[str] = None
    hospital_name: Optional[str] = None
    verification_status: Optional[str] = "APPROVED"
    rejection_reason: Optional[str] = None
    access_token: Optional[str] = None
    token_type: Optional[str] = "bearer"
