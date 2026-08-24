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
    result = await db["hospitals"].update_one(
        {"_id": ObjectId(hospital_id)},
        {"$set": {"verification_status": "APPROVED", "status": "ACTIVE"}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Hospital not found")
    return {"status": "success", "message": "Hospital approved"}

@router.post("/hospitals/{hospital_id}/reject")
async def reject_hospital(hospital_id: str, db = Depends(get_db)):
    result = await db["hospitals"].update_one(
        {"_id": ObjectId(hospital_id)},
        {"$set": {"verification_status": "REJECTED", "status": "INACTIVE"}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Hospital not found")
    return {"status": "success", "message": "Hospital rejected"}
