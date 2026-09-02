from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import List, Optional
from pydantic import BaseModel
from models.hospital import HospitalResponse
from database import get_db
from bson import ObjectId
from datetime import datetime

router = APIRouter()

class RejectionPayload(BaseModel):
    reason: Optional[str] = "Statutory documents incomplete or clinical license could not be verified."
    notes: Optional[str] = None

class SuspensionPayload(BaseModel):
    reason: Optional[str] = "Temporary compliance hold."

@router.get("/compliance-stats")
async def get_compliance_stats(db = Depends(get_db)):
    """Summary metrics of all hospitals, legal approvals, and bed counts for CareSeva Superadmin."""
    total = await db["hospitals"].count_documents({})
    pending = await db["hospitals"].count_documents({"verification_status": "PENDING"})
    approved = await db["hospitals"].count_documents({"verification_status": "APPROVED"})
    rejected = await db["hospitals"].count_documents({"verification_status": "REJECTED"})
    suspended = await db["hospitals"].count_documents({"status": "SUSPENDED"})
    
    # Calculate total beds monitored
    cursor = db["hospitals"].find({}, {"total_beds": 1, "nabh_accreditation": 1})
    all_h = await cursor.to_list(length=500)
    total_beds = sum(int(h.get("total_beds") or 0) for h in all_h)
    nabh_count = sum(1 for h in all_h if (h.get("nabh_accreditation") or "NONE") != "NONE")

    return {
        "total_facilities": total,
        "pending_verifications": pending,
        "approved_facilities": approved,
        "rejected_facilities": rejected,
        "suspended_facilities": suspended,
        "total_beds_monitored": total_beds,
        "nabh_accredited_facilities": nabh_count
    }

@router.get("/hospitals", response_model=List[HospitalResponse])
async def list_all_hospitals(
    status_filter: Optional[str] = Query(None, description="ALL, PENDING, APPROVED, REJECTED, SUSPENDED"),
    search: Optional[str] = None,
    db = Depends(get_db)
):
    """List all registered hospitals with statutory compliance and legal fields."""
    query = {}
    if status_filter and status_filter.upper() != "ALL":
        sf = status_filter.upper()
        if sf in ["PENDING", "APPROVED", "REJECTED"]:
            query["verification_status"] = sf
        elif sf == "SUSPENDED":
            query["status"] = "SUSPENDED"

    if search and search.strip():
        rgx = {"$regex": search.strip(), "$options": "i"}
        query["$or"] = [
            {"name": rgx},
            {"city": rgx},
            {"state": rgx},
            {"hop_id": rgx},
            {"clinical_establishment_no": rgx},
            {"contact_person": rgx},
            {"email": rgx}
        ]

    cursor = db["hospitals"].find(query).sort("created_at", -1)
    hospitals = await cursor.to_list(length=200)

    result = []
    for h in hospitals:
        h["id"] = str(h["_id"])
        result.append(HospitalResponse(**h))
    return result

@router.get("/hospitals/pending", response_model=List[HospitalResponse])
async def get_pending_hospitals(db = Depends(get_db)):
    cursor = db["hospitals"].find({"verification_status": "PENDING"}).sort("created_at", -1)
    hospitals = await cursor.to_list(length=100)
    
    result = []
    for h in hospitals:
        h["id"] = str(h["_id"])
        result.append(HospitalResponse(**h))
    return result

@router.get("/hospitals/{hospital_id}", response_model=HospitalResponse)
async def get_hospital_dossier(hospital_id: str, db = Depends(get_db)):
    """Retrieve full official legal dossier of a hospital."""
    try:
        hospital = await db["hospitals"].find_one({"_id": ObjectId(hospital_id)})
    except Exception:
        hospital = None
    if not hospital:
        hospital = await db["hospitals"].find_one({"hop_id": hospital_id})

    if not hospital:
        raise HTTPException(status_code=404, detail="Hospital not found")

    hospital["id"] = str(hospital["_id"])
    return HospitalResponse(**hospital)

@router.post("/hospitals/{hospital_id}/approve")
async def approve_hospital(hospital_id: str, db = Depends(get_db)):
    try:
        obj_id = ObjectId(hospital_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid hospital ID format")

    hospital = await db["hospitals"].find_one({"_id": obj_id})
    if not hospital:
        raise HTTPException(status_code=404, detail="Hospital not found")
        
    await db["hospitals"].update_one(
        {"_id": obj_id},
        {"$set": {
            "verification_status": "APPROVED",
            "status": "ACTIVE",
            "approved_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
            "rejection_reason": None
        }}
    )
    
    # Create or update the admin user for this hospital
    existing_user = await db["users"].find_one({"email": hospital["email"]})
    if not existing_user:
        user_dict = {
            "name": hospital.get("contact_person", hospital.get("name")),
            "email": hospital["email"],
            "hashed_password": hospital.get("hashed_password"),
            "role": "admin",
            "hospital_id": str(hospital["_id"]),
            "hospital_name": hospital.get("name"),
            "hop_id": hospital.get("hop_id")
        }
        await db["users"].insert_one(user_dict)
    else:
        await db["users"].update_one(
            {"_id": existing_user["_id"]},
            {"$set": {"status": "ACTIVE"}}
        )
        
    return {
        "status": "success",
        "message": f"{hospital.get('name')} approved successfully. Hospital is now active on CareSeva."
    }

@router.post("/hospitals/{hospital_id}/reject")
async def reject_hospital(
    hospital_id: str,
    payload: Optional[RejectionPayload] = None,
    db = Depends(get_db)
):
    try:
        obj_id = ObjectId(hospital_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid hospital ID format")

    reason = payload.reason if payload else "Statutory documents incomplete or license verification failed."
    notes = payload.notes if payload else None

    result = await db["hospitals"].update_one(
        {"_id": obj_id},
        {"$set": {
            "verification_status": "REJECTED",
            "status": "INACTIVE",
            "rejection_reason": reason,
            "verification_notes": notes,
            "rejected_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        }}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Hospital not found")
    return {"status": "success", "message": "Hospital application rejected", "reason": reason}

@router.post("/hospitals/{hospital_id}/suspend")
async def suspend_hospital(
    hospital_id: str,
    payload: Optional[SuspensionPayload] = None,
    db = Depends(get_db)
):
    try:
        obj_id = ObjectId(hospital_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid hospital ID format")

    reason = payload.reason if payload else "Compliance violation hold."

    result = await db["hospitals"].update_one(
        {"_id": obj_id},
        {"$set": {
            "status": "SUSPENDED",
            "verification_notes": f"Suspended: {reason}",
            "suspended_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        }}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Hospital not found")
    return {"status": "success", "message": "Hospital suspended from public booking"}
