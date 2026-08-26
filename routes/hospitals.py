from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from models.hospital import HospitalCreate, HospitalResponse, HospitalInDB, HospitalUpdate
from database import get_db
from routes.auth import get_password_hash
from bson import ObjectId
from datetime import datetime

router = APIRouter()

@router.post("/register", response_model=HospitalResponse)
async def register_hospital(hospital: HospitalCreate, db = Depends(get_db)):
    try:
        # Check if email is already registered
        existing_hospital = await db["hospitals"].find_one({"email": hospital.email})
        if existing_hospital:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered for a hospital"
            )
        
        # Hash password
        hashed_password = get_password_hash(hospital.password)
        hospital_dict = hospital.dict()
        del hospital_dict["password"]
        
        # Prepare DB model
        db_hospital = HospitalInDB(
            **hospital_dict,
            id="", # Will be set by mongo
            hashed_password=hashed_password,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        # Insert into database
        db_dict = db_hospital.dict(exclude={"id"})
        result = await db["hospitals"].insert_one(db_dict)
        
        db_dict["id"] = str(result.inserted_id)
        return HospitalResponse(**db_dict)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {str(e)}"
        )

@router.get("/", response_model=List[HospitalResponse])
async def get_active_hospitals(db = Depends(get_db)):
    cursor = db["hospitals"].find({"status": "ACTIVE", "verification_status": "APPROVED"})
    hospitals = await cursor.to_list(length=100)
    
    result = []
    for h in hospitals:
        h["id"] = str(h["_id"])
        result.append(HospitalResponse(**h))
    return result

@router.get("/{hospital_id}", response_model=HospitalResponse)
async def get_hospital(hospital_id: str, db = Depends(get_db)):
    hospital = await db["hospitals"].find_one({"_id": ObjectId(hospital_id)})
    if not hospital:
        raise HTTPException(status_code=404, detail="Hospital not found")
    
    hospital["id"] = str(hospital["_id"])
    return HospitalResponse(**hospital)

@router.put("/{hospital_id}", response_model=HospitalResponse)
async def update_hospital(hospital_id: str, hospital_update: HospitalUpdate, db = Depends(get_db)):
    hospital = await db["hospitals"].find_one({"_id": ObjectId(hospital_id)})
    if not hospital:
        raise HTTPException(status_code=404, detail="Hospital not found")
        
    update_data = hospital_update.dict(exclude_unset=True)
    if not update_data:
        hospital["id"] = str(hospital["_id"])
        return HospitalResponse(**hospital)
        
    update_data["updated_at"] = datetime.utcnow()
    
    await db["hospitals"].update_one(
        {"_id": ObjectId(hospital_id)},
        {"$set": update_data}
    )
    
    updated_hospital = await db["hospitals"].find_one({"_id": ObjectId(hospital_id)})
    updated_hospital["id"] = str(updated_hospital["_id"])
    return HospitalResponse(**updated_hospital)
