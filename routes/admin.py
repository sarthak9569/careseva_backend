from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from models.hospital import HospitalResponse
from database import get_db
from bson import ObjectId

router = APIRouter()

@router.get("/hospitals/pending", response_model=List[HospitalResponse])
async def get_pending_hospitals(db = Depends(get_db)):
    cursor = db["hospitals"].find({"verification_status": "PENDING"})
    hospitals = await cursor.to_list(length=100)
    
    result = []
    for h in hospitals:
        h["id"] = str(h["_id"])
        result.append(HospitalResponse(**h))
    return result

@router.post("/hospitals/{hospital_id}/approve")
async def approve_hospital(hospital_id: str, db = Depends(get_db)):
    hospital = await db["hospitals"].find_one({"_id": ObjectId(hospital_id)})
    if not hospital:
        raise HTTPException(status_code=404, detail="Hospital not found")
        
    result = await db["hospitals"].update_one(
        {"_id": ObjectId(hospital_id)},
        {"$set": {"verification_status": "APPROVED", "status": "ACTIVE"}}
    )
    
    # Create the admin user for this hospital if it doesn't exist
    existing_user = await db["users"].find_one({"email": hospital["email"]})
    if not existing_user:
        user_dict = {
            "name": hospital.get("contact_person", hospital.get("name")),
            "email": hospital["email"],
            "hashed_password": hospital.get("hashed_password"),
            "role": "admin",
            "hospital_id": str(hospital["_id"]),
            "hospital_name": hospital.get("name")
        }
        await db["users"].insert_one(user_dict)
        
    return {"status": "success", "message": "Hospital approved and admin user created"}

@router.post("/hospitals/{hospital_id}/reject")
async def reject_hospital(hospital_id: str, db = Depends(get_db)):
    result = await db["hospitals"].update_one(
        {"_id": ObjectId(hospital_id)},
        {"$set": {"verification_status": "REJECTED", "status": "INACTIVE"}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Hospital not found")
    return {"status": "success", "message": "Hospital rejected"}
