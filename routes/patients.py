from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional
from models.patient import PatientCreate, PatientResponse, PatientInDB
from database import get_db
from core.pid_generator import generate_unique_pid
from bson import ObjectId
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))

def get_ist_now() -> datetime:
    return datetime.now(IST)

def calculate_age_from_dob(dob_str: str) -> int:
    """Calculate exact age using full YYYY/MM/DD comparison"""
    try:
        clean_dob = dob_str.strip().replace("/", "-")
        dob = datetime.strptime(clean_dob, "%Y-%m-%d").date()
        today = get_ist_now().date()
        age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        return max(0, age)
    except Exception:
        return 0

router = APIRouter()

@router.post("/", response_model=PatientResponse)
async def register_patient(patient: PatientCreate, db = Depends(get_db)):
    data = patient.dict()
    now_ist = get_ist_now()

    # Calculate exact age using YYYY/MM/DD if dob is provided
    if data.get("dob") and (data.get("age") is None or data.get("age") == 0):
        data["age"] = calculate_age_from_dob(data["dob"])
    elif data.get("age") is None:
        data["age"] = 0

    # Ensure last_visit is recorded as today in IST if not given
    if not data.get("last_visit"):
        data["last_visit"] = now_ist.strftime("%Y-%m-%d")

    # If department_name is not provided, fetch from department_id
    if data.get("department_id") and not data.get("department_name"):
        try:
            dept = await db["departments"].find_one({"_id": ObjectId(data["department_id"])})
            if dept:
                data["department_name"] = dept.get("name", "General")
        except Exception:
            data["department_name"] = "General"

    # Generate unique PID
    unique_pid = await generate_unique_pid(db)
    data["pid"] = unique_pid

    db_patient = PatientInDB(
        **data,
        id="",
        created_at=now_ist,
        updated_at=now_ist
    )

    db_dict = db_patient.dict(exclude={"id"})
    result = await db["patients"].insert_one(db_dict)
    db_dict["id"] = str(result.inserted_id)

    return PatientResponse(**db_dict)

@router.get("/hospital/{hospital_id}", response_model=List[PatientResponse])
async def get_hospital_patients(hospital_id: str, search: Optional[str] = None, db = Depends(get_db)):
    query = {"hospital_id": hospital_id}
    if search:
        s = search.strip()
        query["$or"] = [
            {"name": {"$regex": s, "$options": "i"}},
            {"pid": {"$regex": s, "$options": "i"}},
            {"phone": {"$regex": s, "$options": "i"}},
            {"department_name": {"$regex": s, "$options": "i"}}
        ]

    # Sorted strictly by created_at descending (timestamp order to help maintain queue)
    cursor = db["patients"].find(query).sort("created_at", -1)
    patients = await cursor.to_list(length=500)

    result = []
    for p in patients:
        p["id"] = str(p["_id"])
        result.append(PatientResponse(**p))
    return result
