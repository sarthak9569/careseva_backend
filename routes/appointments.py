from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional
from models.queue import AppointmentCreate, AppointmentResponse, AppointmentInDB
from database import get_db
from bson import ObjectId
from datetime import datetime, timezone, timedelta

router = APIRouter()

IST = timezone(timedelta(hours=5, minutes=30))

def get_ist_now() -> datetime:
    return datetime.now(IST)

@router.post("/", response_model=AppointmentResponse)
async def create_appointment(appointment: AppointmentCreate, db = Depends(get_db)):
    appt_data = appointment.dict()
    now_ist = get_ist_now()

    # Normalize human labels like "Today, Aug 28" to YYYY-MM-DD
    if not appt_data.get("appointment_date"):
        appt_data["appointment_date"] = now_ist.strftime("%Y-%m-%d")
    else:
        d_str = str(appt_data["appointment_date"]).strip().lower()
        if "today" in d_str:
            appt_data["appointment_date"] = now_ist.strftime("%Y-%m-%d")
        elif "tomorrow" in d_str:
            appt_data["appointment_date"] = (now_ist + timedelta(days=1)).strftime("%Y-%m-%d")
        elif "yesterday" in d_str:
            appt_data["appointment_date"] = (now_ist - timedelta(days=1)).strftime("%Y-%m-%d")

    db_appt = AppointmentInDB(
        **appt_data,
        id="",
        created_at=get_ist_now(),
        updated_at=get_ist_now()
    )
    
    db_dict = db_appt.dict(exclude={"id"})
    result = await db["appointments"].insert_one(db_dict)
    
    appt_id = str(result.inserted_id)
    db_dict["id"] = appt_id

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
            created_at=get_ist_now(),
            updated_at=get_ist_now(),
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
    
    # Create entry with linked appointment_id
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
        appointment_id=appt_id,
        created_at=get_ist_now(),
        updated_at=get_ist_now(),
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
async def get_hospital_appointments(
    hospital_id: str, 
    department_id: str = None,
    date: str = None,
    status: str = None,
    db = Depends(get_db)
):
    query = {"hospital_id": hospital_id}
    if department_id:
        query["department_id"] = department_id
    if date:
        try:
            target_d = datetime.strptime(date, "%Y-%m-%d").date()
            # In IST, date spans from target_d 00:00 to 23:59:59 (in UTC: minus 5h30m)
            day_start_ist = datetime(target_d.year, target_d.month, target_d.day, 0, 0, 0, tzinfo=IST)
            day_end_ist = datetime(target_d.year, target_d.month, target_d.day, 23, 59, 59, 999999, tzinfo=IST)
            day_start_utc = day_start_ist.astimezone(timezone.utc).replace(tzinfo=None)
            day_end_utc = day_end_ist.astimezone(timezone.utc).replace(tzinfo=None)
            
            query["$or"] = [
                {"appointment_date": date},
                {"appointment_date": {"$regex": date, "$options": "i"}},
                {"created_at": {"$gte": day_start_utc, "$lte": day_end_utc}},
                {"created_at": {"$gte": day_start_ist, "$lte": day_end_ist}}
            ]
        except Exception:
            query["appointment_date"] = date

    if status and status != "All":
        if status.upper() == "WAITING":
            query["status"] = {"$in": ["WAITING", "BOOKED"]}
        elif status.upper() == "BOOKED":
            query["status"] = "BOOKED"
        elif status.upper() == "COMPLETED":
            query["status"] = "COMPLETED"
        elif status.upper() == "CANCELLED":
            query["status"] = "CANCELLED"
        else:
            query["status"] = status
        
    cursor = db["appointments"].find(query).sort("created_at", -1)
    appointments = await cursor.to_list(length=300)
    
    # Pre-fetch department mapping for quick lookup
    dept_cursor = db["departments"].find({"hospital_id": hospital_id})
    departments = await dept_cursor.to_list(length=100)
    dept_map = {str(d["_id"]): d.get("name", "General") for d in departments}

    result = []
    for a in appointments:
        a["id"] = str(a["_id"])
        dept_id = a.get("department_id")
        if dept_id and str(dept_id) in dept_map:
            a["department_name"] = dept_map[str(dept_id)]
        elif not a.get("department_name"):
            a["department_name"] = "General"

        if not a.get("booking_source"):
            a["booking_source"] = "CARESEVA_APP"

        result.append(AppointmentResponse(**a))
    return result

@router.get("/doctor/{doctor_id}", response_model=List[AppointmentResponse])
async def get_doctor_appointments(
    doctor_id: str,
    date: str = None,
    status: str = None,
    db = Depends(get_db)
):
    query = {"doctor_id": doctor_id}
    if date:
        try:
            target_d = datetime.strptime(date, "%Y-%m-%d").date()
            day_start_ist = datetime(target_d.year, target_d.month, target_d.day, 0, 0, 0, tzinfo=IST)
            day_end_ist = datetime(target_d.year, target_d.month, target_d.day, 23, 59, 59, 999999, tzinfo=IST)
            day_start_utc = day_start_ist.astimezone(timezone.utc).replace(tzinfo=None)
            day_end_utc = day_end_ist.astimezone(timezone.utc).replace(tzinfo=None)
            
            query["$or"] = [
                {"appointment_date": date},
                {"appointment_date": {"$regex": date, "$options": "i"}},
                {"created_at": {"$gte": day_start_utc, "$lte": day_end_utc}},
                {"created_at": {"$gte": day_start_ist, "$lte": day_end_ist}}
            ]
        except Exception:
            query["appointment_date"] = date

    if status and status != "All":
        if status.upper() == "WAITING":
            query["status"] = {"$in": ["WAITING", "BOOKED"]}
        else:
            query["status"] = status

    cursor = db["appointments"].find(query).sort("created_at", -1)
    appointments = await cursor.to_list(length=200)

    result = []
    for a in appointments:
        a["id"] = str(a["_id"])
        result.append(AppointmentResponse(**a))
    return result

@router.put("/{appointment_id}/status")
async def update_appointment_status(
    appointment_id: str,
    status_update: dict,
    db = Depends(get_db)
):
    new_status = status_update.get("status")
    if not new_status:
        raise HTTPException(status_code=400, detail="Status field is required")
        
    appt = await db["appointments"].find_one({"_id": ObjectId(appointment_id)})
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")
        
    await db["appointments"].update_one(
        {"_id": ObjectId(appointment_id)},
        {"$set": {"status": new_status, "updated_at": get_ist_now()}}
    )

    # Also update queue entries status if linked
    if "patient_id" in appt and "doctor_id" in appt:
        queue_entry_status = new_status
        if new_status == "BOOKED":
            queue_entry_status = "WAITING"
        await db["queue_entries"].update_many(
            {"doctor_id": appt["doctor_id"], "patient_id": appt["patient_id"]},
            {"$set": {"status": queue_entry_status, "updated_at": get_ist_now()}}
        )
    
    return {"message": "Status updated successfully", "status": new_status}

@router.get("/patient/{patient_id}", response_model=List[AppointmentResponse])
async def get_patient_appointments(patient_id: str, db = Depends(get_db)):
    cursor = db["appointments"].find({"patient_id": patient_id})
    appointments = await cursor.to_list(length=100)
    
    result = []
    for a in appointments:
        a["id"] = str(a["_id"])
        result.append(AppointmentResponse(**a))
    return result


