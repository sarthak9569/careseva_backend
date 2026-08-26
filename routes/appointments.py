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

    # Automatically add to the doctor's queue
    hospital_id = appointment.hospital_id
    doctor_id = appointment.doctor_id
    department_id = appointment.department_id
    patient_id = appointment.patient_id
    patient_name = appointment.patient_name or "Unknown Patient"

    queue = await db["queues"].find_one({
        "hospital_id": hospital_id,
        "doctor_id": doctor_id,
        "status": "ACTIVE"
    })
    
    if not queue:
        # Create new queue
        from models.queue import QueueInDB
        new_queue = QueueInDB(
            id="",
            hospital_id=hospital_id,
            department_id=department_id,
            doctor_id=doctor_id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            total_tokens=0,
            current_token=0
        )
        db_queue = new_queue.dict(exclude={"id"})
        res = await db["queues"].insert_one(db_queue)
        queue_id = str(res.inserted_id)
        token_num = 1
    else:
        queue_id = str(queue["_id"])
        token_num = queue["total_tokens"] + 1
        
    # Increment total_tokens
    await db["queues"].update_one({"_id": ObjectId(queue_id)}, {"$inc": {"total_tokens": 1}})
    
    # Create entry
    from models.queue import QueueEntryInDB
    db_entry = QueueEntryInDB(
        id="",
        queue_id=queue_id,
        patient_id=patient_id,
        patient_name=patient_name,
        token_number=token_num,
        hospital_id=hospital_id,
        department_id=department_id,
        doctor_id=doctor_id,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        status="WAITING"
    )
    
    entry_dict = db_entry.dict(exclude={"id"})
    await db["queue_entries"].insert_one(entry_dict)
    
    # Broadcast to websocket
    from routes.queue import manager
    await manager.broadcast_queue_update(doctor_id, {
        "event": "new_patient",
        "total_tokens": token_num
    })

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
