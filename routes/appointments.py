from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from models.queue import AppointmentCreate, AppointmentResponse, AppointmentInDB
from database import get_db
from bson import ObjectId
from datetime import datetime

router = APIRouter()

@router.post("/", response_model=AppointmentResponse)
async def create_appointment(appointment: AppointmentCreate, db = Depends(get_db)):
    db_appt = AppointmentInDB(
        **appointment.dict(),
        id="",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    
    db_dict = db_appt.dict(exclude={"id"})
    result = await db["appointments"].insert_one(db_dict)
    
    db_dict["id"] = str(result.inserted_id)
    return AppointmentResponse(**db_dict)

@router.get("/hospital/{hospital_id}", response_model=List[AppointmentResponse])
async def get_hospital_appointments(hospital_id: str, db = Depends(get_db)):
    cursor = db["appointments"].find({"hospital_id": hospital_id})
    appointments = await cursor.to_list(length=100)
    
    result = []
    for a in appointments:
        a["id"] = str(a["_id"])
        result.append(AppointmentResponse(**a))
    return result

@router.get("/patient/{patient_id}", response_model=List[AppointmentResponse])
async def get_patient_appointments(patient_id: str, db = Depends(get_db)):
    cursor = db["appointments"].find({"patient_id": patient_id})
    appointments = await cursor.to_list(length=100)
    
    result = []
    for a in appointments:
        a["id"] = str(a["_id"])
        result.append(AppointmentResponse(**a))
    return result
