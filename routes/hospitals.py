from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from models.hospital import HospitalCreate, HospitalResponse, HospitalInDB, HospitalUpdate
from database import get_db
from routes.auth import get_password_hash
from bson import ObjectId
from datetime import datetime
import random
import string
import urllib.request
import json
import asyncio

router = APIRouter()

def generate_hop_id():
    return f"CARE-{''.join(random.choices(string.digits, k=4))}"

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
        # Prepare hospital dictionary
        hospital_dict = hospital.dict()
        hospital_dict.pop("password", None)
        hospital_dict.pop("hop_id", None)
        hospital_dict.pop("id", None)
        
        # Default legal SLA acceptance timestamp if not supplied
        if not hospital_dict.get("sla_accepted_at"):
            hospital_dict["sla_accepted_at"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

        # Generate unique HopID
        hop_id = generate_hop_id()
        while await db["hospitals"].find_one({"hop_id": hop_id}):
            hop_id = generate_hop_id()
            
        # Prepare DB model with PENDING verification status
        db_hospital = HospitalInDB(
            **hospital_dict,
            id="", # Will be set by mongo
            hashed_password=hashed_password,
            status="INACTIVE", # Remains inactive until superadmin verifies legal credentials
            verification_status="PENDING",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            hop_id=hop_id
        )
        
        # Insert into database
        db_dict = db_hospital.dict(exclude={"id"})
        result = await db["hospitals"].insert_one(db_dict)
        
        db_dict["id"] = str(result.inserted_id)
        
        # Also create an admin user in users collection for login (auth.py uses users collection)
        admin_user = {
            "name": hospital.contact_person or hospital.name,
            "email": hospital.email,
            "role": "admin",
            "hashed_password": hashed_password,
            "hospital_id": db_dict["id"],
            "hospital_name": hospital.name,
            "hop_id": hop_id
        }
        await db["users"].insert_one(admin_user)
        
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

@router.get("/reverse-geocode")
async def reverse_geocode(lat: float, lng: float):
    """Reverse geocode latitude and longitude to auto-fill City, State, Pincode, and Address."""
    def _fetch_geo_sync():
        url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lng}&zoom=18&addressdetails=1"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "CareSeva-Hospital-Registry/1.0"}
        )
        with urllib.request.urlopen(req, timeout=6.0) as resp:
            return json.loads(resp.read().decode())

    try:
        data = await asyncio.to_thread(_fetch_geo_sync)
        addr = data.get("address", {})
        
        # City fallback hierarchy (city -> town -> municipality -> suburb -> state_district -> county)
        city = (
            addr.get("city") or 
            addr.get("town") or 
            addr.get("municipality") or 
            addr.get("suburb") or 
            addr.get("state_district") or 
            addr.get("county") or 
            ""
        )
        state = addr.get("state", "")
        pincode = addr.get("postcode", "")
        
        # Format friendly road/neighborhood address
        road = addr.get("road") or addr.get("pedestrian") or ""
        suburb = addr.get("suburb") or addr.get("neighbourhood") or ""
        parts = [p for p in [road, suburb] if p]
        address_str = ", ".join(parts) if parts else data.get("display_name", "")

        return {
            "city": city,
            "state": state,
            "pincode": pincode,
            "address": address_str,
            "display_name": data.get("display_name", "")
        }
    except Exception as e:
        print(f"Reverse geocode error: {e}")
    
    return {"city": "", "state": "", "pincode": "", "address": "", "display_name": ""}

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
