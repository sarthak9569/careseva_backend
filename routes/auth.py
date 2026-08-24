from fastapi import APIRouter, Depends, HTTPException, status
from passlib.context import CryptContext
from models.user import UserCreate, UserInDB, UserResponse
from database import get_db

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_password_hash(password):
    # bcrypt limits passwords to 72 bytes. 
    # Truncate if longer to avoid passlib errors.
    if len(password) > 72:
        password = password[:72]
    return pwd_context.hash(password)

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
            role=user.role
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {str(e)}"
        )
