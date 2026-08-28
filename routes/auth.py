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
