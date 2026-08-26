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
