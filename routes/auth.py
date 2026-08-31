from fastapi import APIRouter, Depends, HTTPException, status
from passlib.context import CryptContext
from models.user import UserCreate, UserInDB, UserResponse, UserLogin
from database import get_db

router = APIRouter()
import bcrypt

def get_password_hash(password: str) -> str:
    # bcrypt limits passwords to 72 bytes. 
    # Truncate if longer.
    if len(password) > 72:
        password = password[:72]
    pwd_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pwd_bytes, salt).decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    pwd_bytes = plain_password.encode('utf-8')
    hash_bytes = hashed_password.encode('utf-8')
    return bcrypt.checkpw(pwd_bytes, hash_bytes)

@router.post("/register", response_model=UserResponse)
async def register(user: UserCreate, db = Depends(get_db)):
    try:
        # Check if user already exists
        existing_user = await db["users"].find_one({"email": user.email})
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
        
        # Hash password and save to DB
        hashed_password = get_password_hash(user.password)
        user_dict = user.dict()
        del user_dict["password"]
        user_dict["hashed_password"] = hashed_password
        
        # Generate unique PID if role is patient
        from core.pid_generator import generate_unique_pid
        from datetime import datetime, timezone, timedelta
        IST = timezone(timedelta(hours=5, minutes=30))
        now_ist = datetime.now(IST)

        unique_pid = None
        if user.role == "patient":
            unique_pid = await generate_unique_pid(db)
            user_dict["pid"] = unique_pid
            
            # Sync to central patients registry
            await db["patients"].insert_one({
                "pid": unique_pid,
                "name": user.name,
                "email": user.email,
                "phone": user_dict.get("phone", ""),
                "registration_source": "CARESEVA_APP",
                "hospital_id": user_dict.get("hospital_id", "6a8ea49ef17ddb14088aa5f7"),
                "created_at": now_ist,
                "updated_at": now_ist
            })

        # Create the db model
        db_user = UserInDB(**user_dict)
        
        # Insert into database
        result = await db["users"].insert_one(db_user.dict())
        
        # Return response
        return UserResponse(
            id=str(result.inserted_id),
            name=user.name,
            email=user.email,
            role=user.role,
            pid=unique_pid,
            hospital_id=user_dict.get("hospital_id")
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {str(e)}"
        )

@router.post("/login", response_model=UserResponse)
async def login(user: UserLogin, db = Depends(get_db)):
    db_user = await db["users"].find_one({"email": user.email})
    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
    
    if not verify_password(user.password, db_user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
        
    return UserResponse(
        id=str(db_user["_id"]),
        name=db_user["name"],
        email=db_user["email"],
        role=db_user["role"],
        hospital_id=db_user.get("hospital_id")
    )

from pydantic import BaseModel

class DoctorLogin(BaseModel):
    hop_id: str
    doc_id: str

@router.post("/doctor-login", response_model=UserResponse)
async def doctor_login(login_data: DoctorLogin, db = Depends(get_db)):
    # 1. Find the hospital by HopID
    hospital = await db["hospitals"].find_one({"hop_id": login_data.hop_id, "status": "ACTIVE"})
    if not hospital:
        raise HTTPException(status_code=401, detail="Invalid HopID or Hospital not found")
        
    hospital_id = str(hospital["_id"])
    
    # 2. Find the doctor by DocID within this hospital
    doctor = await db["doctors"].find_one({"hospital_id": hospital_id, "doc_id": login_data.doc_id, "status": "ACTIVE"})
    if not doctor:
        raise HTTPException(status_code=401, detail="Invalid DocID or Doctor not found")
        
    return UserResponse(
        id=str(doctor["_id"]),
        name=doctor["name"],
        email=f"{login_data.doc_id.lower()}@careseva.com", # Mock email for doctor session
        role="doctor",
        hospital_id=hospital_id
    )

import random
from datetime import datetime, timezone, timedelta
from typing import Optional

class SendOtpRequest(BaseModel):
    phone: str

class VerifyOtpAndRegisterRequest(BaseModel):
    phone: str
    otp: str
    name: str
    email: Optional[str] = None
    password: Optional[str] = "careseva123"

class LoginWithOtpRequest(BaseModel):
    phone: str
    otp: str

@router.post("/send-otp")
async def send_otp(req: SendOtpRequest, db = Depends(get_db)):
    clean_phone = req.phone.strip().replace(" ", "").replace("-", "")
    if clean_phone.startswith("+91"):
        clean_phone = clean_phone[3:]
    elif clean_phone.startswith("91") and len(clean_phone) == 12:
        clean_phone = clean_phone[2:]
        
    if len(clean_phone) < 10:
        raise HTTPException(status_code=400, detail="Invalid phone number. Must be at least 10 digits.")

    # Generate 6-digit OTP
    otp_code = str(random.randint(100000, 999999))
    now_ist = datetime.now(timezone(timedelta(hours=5, minutes=30)))

    # Store OTP in database with 10-minute expiry
    await db["otps"].update_one(
        {"phone": clean_phone},
        {"$set": {
            "phone": clean_phone,
            "otp": otp_code,
            "created_at": now_ist,
            "expires_at": now_ist + timedelta(minutes=10)
        }},
        upsert=True
    )

    return {
        "status": "success",
        "message": f"OTP sent successfully to +91 {clean_phone}",
        "otp": otp_code, # Provided for instant testing/demo in app
        "demo_otp": "123456"
    }

@router.post("/verify-otp-and-register", response_model=UserResponse)
async def verify_otp_and_register(req: VerifyOtpAndRegisterRequest, db = Depends(get_db)):
    clean_phone = req.phone.strip().replace(" ", "").replace("-", "")
    if clean_phone.startswith("+91"):
        clean_phone = clean_phone[3:]
    elif clean_phone.startswith("91") and len(clean_phone) == 12:
        clean_phone = clean_phone[2:]

    # Check OTP (accept demo '123456' / '1234' or saved OTP)
    is_valid = req.otp.strip() in ["123456", "1234"]
    if not is_valid:
        record = await db["otps"].find_one({"phone": clean_phone, "otp": req.otp.strip()})
        if record:
            is_valid = True

    if not is_valid:
        raise HTTPException(status_code=400, detail="Invalid or expired OTP. Please try again.")

    from core.pid_generator import generate_unique_pid
    now_ist = datetime.now(timezone(timedelta(hours=5, minutes=30)))

    email = req.email.strip() if req.email and req.email.strip() else f"patient_{clean_phone[-6:]}@careseva.com"

    # Check if user already exists with this phone or email
    existing_user = await db["users"].find_one({
        "$or": [{"phone": clean_phone}, {"email": email}]
    })

    unique_pid = None
    if existing_user:
        unique_pid = existing_user.get("pid")
        if not unique_pid:
            unique_pid = await generate_unique_pid(db)
        
        await db["users"].update_one(
            {"_id": existing_user["_id"]},
            {"$set": {
                "name": req.name.strip(),
                "phone": clean_phone,
                "email": email,
                "pid": unique_pid
            }}
        )
        user_id = str(existing_user["_id"])
    else:
        unique_pid = await generate_unique_pid(db)
        hashed_password = get_password_hash(req.password or "careseva123")
        res = await db["users"].insert_one({
            "name": req.name.strip(),
            "email": email,
            "phone": clean_phone,
            "hashed_password": hashed_password,
            "role": "patient",
            "pid": unique_pid,
            "hospital_id": "6a8ea49ef17ddb14088aa5f7",
            "created_at": now_ist
        })
        user_id = str(res.inserted_id)

    # Sync or update to central patients registry
    existing_patient = await db["patients"].find_one({"phone": clean_phone})
    if not existing_patient:
        await db["patients"].insert_one({
            "pid": unique_pid,
            "name": req.name.strip(),
            "email": email,
            "phone": clean_phone,
            "registration_source": "CARESEVA_APP",
            "hospital_id": "6a8ea49ef17ddb14088aa5f7",
            "created_at": now_ist,
            "updated_at": now_ist
        })
    else:
        await db["patients"].update_one(
            {"_id": existing_patient["_id"]},
            {"$set": {
                "name": req.name.strip(),
                "email": email,
                "pid": unique_pid,
                "updated_at": now_ist
            }}
        )

    return UserResponse(
        id=user_id,
        name=req.name.strip(),
        email=email,
        phone=clean_phone,
        role="patient",
        pid=unique_pid,
        hospital_id="6a8ea49ef17ddb14088aa5f7"
    )

@router.post("/login-with-otp", response_model=UserResponse)
async def login_with_otp(req: LoginWithOtpRequest, db = Depends(get_db)):
    clean_phone = req.phone.strip().replace(" ", "").replace("-", "")
    if clean_phone.startswith("+91"):
        clean_phone = clean_phone[3:]
    elif clean_phone.startswith("91") and len(clean_phone) == 12:
        clean_phone = clean_phone[2:]

    is_valid = req.otp.strip() in ["123456", "1234"]
    if not is_valid:
        record = await db["otps"].find_one({"phone": clean_phone, "otp": req.otp.strip()})
        if record:
            is_valid = True

    if not is_valid:
        raise HTTPException(status_code=400, detail="Invalid OTP code.")

    # Find user by phone
    db_user = await db["users"].find_one({"phone": clean_phone})
    if not db_user:
        # Also check patients registry
        pt = await db["patients"].find_one({"phone": clean_phone})
        if pt:
            # Auto-create user account from patient registry
            from core.pid_generator import generate_unique_pid
            pid = pt.get("pid") or await generate_unique_pid(db)
            email = pt.get("email") or f"patient_{clean_phone[-6:]}@careseva.com"
            res = await db["users"].insert_one({
                "name": pt.get("name", "Registered Patient"),
                "phone": clean_phone,
                "email": email,
                "hashed_password": get_password_hash("careseva123"),
                "role": "patient",
                "pid": pid,
                "hospital_id": pt.get("hospital_id", "6a8ea49ef17ddb14088aa5f7")
            })
            return UserResponse(
                id=str(res.inserted_id),
                name=pt.get("name", "Registered Patient"),
                email=email,
                phone=clean_phone,
                role="patient",
                pid=pid,
                hospital_id=pt.get("hospital_id", "6a8ea49ef17ddb14088aa5f7")
            )
        raise HTTPException(status_code=404, detail="No account registered with this phone number.")

    return UserResponse(
        id=str(db_user["_id"]),
        name=db_user["name"],
        email=db_user["email"],
        phone=db_user.get("phone", clean_phone),
        role=db_user.get("role", "patient"),
        pid=db_user.get("pid"),
        hospital_id=db_user.get("hospital_id")
    )
