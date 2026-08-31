from pydantic import BaseModel, EmailStr
from typing import Optional

class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str
    role: str = "patient" # 'patient', 'hospital_admin', 'doctor'
    phone: Optional[str] = None
    
    # Optional hospital fields if role is 'hospital_admin'
    hospital_name: Optional[str] = None
    hospital_code: Optional[str] = None
    hospital_id: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserInDB(BaseModel):
    name: str
    email: EmailStr
    hashed_password: str
    role: str
    phone: Optional[str] = None
    pid: Optional[str] = None
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
    email: EmailStr
    role: str
    phone: Optional[str] = None
    pid: Optional[str] = None
    hospital_id: Optional[str] = None
