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

    # RESTRICTION: Restrict multiple appointment booking from same PID on the same day for the same doctor.
    # User CAN book multiple appointments for different doctors using the same PID.
    doctor_id = appointment.doctor_id
    patient_id = appointment.patient_id
    patient_phone = appointment.patient_phone or ""

    resolved_pid = None
    if patient_id and str(patient_id).startswith("CS-P-"):
        resolved_pid = str(patient_id)

    # Resolve PID from users or patients collection if not direct
    if not resolved_pid and patient_phone:
        user_doc = await db["users"].find_one({"phone": patient_phone})
        if user_doc and user_doc.get("pid"):
            resolved_pid = user_doc["pid"]
    if not resolved_pid and patient_id:
        try:
            user_doc = await db["users"].find_one({"_id": ObjectId(patient_id)})
            if user_doc and user_doc.get("pid"):
                resolved_pid = user_doc["pid"]
        except Exception:
            pass
    if not resolved_pid and patient_phone:
        p_doc = await db["patients"].find_one({"hospital_id": appointment.hospital_id, "phone": patient_phone})
        if p_doc and p_doc.get("pid"):
            resolved_pid = p_doc["pid"]

    # Match conditions for this patient
    match_conditions = []
    if resolved_pid:
        match_conditions.append({"patient_id": resolved_pid})
    if patient_id:
        match_conditions.append({"patient_id": patient_id})
    if patient_phone:
        match_conditions.append({"patient_phone": patient_phone})

    # RESTRICTION LOGIC:
    # Multiple appointments on the same PID are allowed when booking for someone else (family/others).
    # Restriction applies only if user chooses 'myself' for the same doctor on the same day.
    booking_for = (appt_data.get("booking_for") or "myself").strip().lower()

    if match_conditions and doctor_id:
        doctor_doc = None
        try:
            doctor_doc = await db["doctors"].find_one({"_id": ObjectId(doctor_id)})
        except Exception:
            pass
        doc_name = doctor_doc.get("name") if doctor_doc else (appointment.doctor_name or "this doctor")
        pid_display = f" (PID: {resolved_pid})" if resolved_pid else ""

        if booking_for == "myself":
            # Restrict ONLY if user chooses 'myself' and already has a booking for themselves
            existing_self_booking = await db["appointments"].find_one({
                "doctor_id": doctor_id,
                "appointment_date": appt_data["appointment_date"],
                "status": {"$nin": ["CANCELLED", "NO_SHOW"]},
                "booking_for": {"$in": ["myself", None, ""]},
                "$or": match_conditions
            })

            if existing_self_booking:
                raise HTTPException(
                    status_code=400,
                    detail=f"You already have an appointment booked for yourself with {doc_name} on {appt_data['appointment_date']}{pid_display}. Multiple appointments for yourself with the same doctor on the same day are not allowed. You can book for family members or someone else."
                )
        else:
            # User chose 'someone_else' on this PID -> ALLOW multiple appointments!
            # Only prevent duplicate booking for the exact same patient's name on the same day:
            p_name = (appointment.patient_name or "").strip()
            if p_name:
                import re
                existing_duplicate = await db["appointments"].find_one({
                    "doctor_id": doctor_id,
                    "appointment_date": appt_data["appointment_date"],
                    "status": {"$nin": ["CANCELLED", "NO_SHOW"]},
                    "patient_name": {"$regex": f"^{re.escape(p_name)}$", "$options": "i"},
                    "$or": match_conditions
                })
                if existing_duplicate:
                    raise HTTPException(
                        status_code=400,
                        detail=f"An appointment is already booked for '{p_name}' with {doc_name} on {appt_data['appointment_date']} under this account. Duplicate bookings for the same person are not allowed."
                    )

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
    patient_phone = appointment.patient_phone or ""

    # Ensure patient is recorded in central patients registry with a PID
    try:
        existing_patient = None
        if patient_phone:
            existing_patient = await db["patients"].find_one({
                "hospital_id": hospital_id,
                "phone": patient_phone
            })
        if not existing_patient and patient_name:
            existing_patient = await db["patients"].find_one({
                "hospital_id": hospital_id,
                "name": patient_name
            })

        payment_status = appt_data.get("payment_status", "DONE")
        payment_option = appt_data.get("payment_option", "full")
        total_fee = float(appt_data.get("total_fee") or 500.0)
        if total_fee <= 0:
            total_fee = 500.0
        paid_amount = float(appt_data.get("paid_amount") or 0.0)
        if paid_amount <= 0:
            paid_amount = total_fee if payment_status == "DONE" else (total_fee * 0.2)
        remaining_amount = float(appt_data.get("remaining_amount") or 0.0)
        if remaining_amount <= 0 and payment_status != "DONE":
            remaining_amount = total_fee - paid_amount

        # Also ensure the appointment record has these non-zero numbers
        await db["appointments"].update_one(
            {"_id": ObjectId(appt_id)},
            {"$set": {
                "total_fee": total_fee,
                "paid_amount": paid_amount,
                "remaining_amount": remaining_amount
            }}
        )

        if not existing_patient:
            from core.pid_generator import generate_unique_pid
            new_pid = await generate_unique_pid(db)
            await db["patients"].insert_one({
                "pid": new_pid,
                "name": patient_name,
                "phone": patient_phone,
                "age": appointment.patient_age or 0,
                "gender": appointment.patient_gender or "-",
                "department_id": department_id,
                "department_name": appt_data.get("department_name", "General"),
                "last_visit": now_ist.strftime("%Y-%m-%d"),
                "registration_source": appt_data.get("booking_source", "CARESEVA_APP"),
                "hospital_id": hospital_id,
                "appointment_id": appt_id,
                "payment_status": payment_status,
                "payment_option": payment_option,
                "total_fee": total_fee,
                "paid_amount": paid_amount,
                "remaining_amount": remaining_amount,
                "created_at": now_ist,
                "updated_at": now_ist
            })
        else:
            update_data = {
                "last_visit": now_ist.strftime("%Y-%m-%d"),
                "department_id": department_id,
                "department_name": appt_data.get("department_name", existing_patient.get("department_name", "General")),
                "appointment_id": appt_id,
                "payment_status": payment_status,
                "payment_option": payment_option,
                "total_fee": total_fee,
                "paid_amount": paid_amount,
                "remaining_amount": remaining_amount,
                "registration_source": appt_data.get("booking_source", existing_patient.get("registration_source", "CARESEVA_APP")),
                "updated_at": now_ist
            }
            if patient_name and patient_name.strip() and patient_name.strip().lower() != "unknown patient":
                update_data["name"] = patient_name.strip()
            if appointment.patient_age:
                update_data["age"] = appointment.patient_age
            if appointment.patient_gender and appointment.patient_gender != "-":
                update_data["gender"] = appointment.patient_gender

            await db["patients"].update_one(
                {"_id": existing_patient["_id"]},
                {"$set": update_data}
            )

            # Link patient PID to appointment record if present
            if existing_patient.get("pid"):
                await db["appointments"].update_one(
                    {"_id": ObjectId(appt_id)},
                    {"$set": {"patient_id": existing_patient["pid"]}}
                )
    except Exception as e:
        print(f"Error syncing patient to registry: {e}")

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
        patient_phone=patient_phone,
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

@router.get("/patient/my-appointments")
async def get_patient_appointments(
    patient_id: Optional[str] = None,
    phone: Optional[str] = None,
    db = Depends(get_db)
):
    """Retrieve all past and upcoming appointments for a patient with detailed metadata."""
    conditions = []
    if patient_id and patient_id != "dummy_patient_123":
        conditions.append({"patient_id": patient_id})
    if phone:
        clean_p = phone.strip().replace(" ", "").replace("-", "")
        if clean_p.startswith("+91"):
            clean_p = clean_p[3:]
        conditions.append({"patient_phone": clean_p})
        conditions.append({"patient_phone": phone})
        try:
            pt = await db["patients"].find_one({"phone": clean_p})
            if pt and pt.get("pid"):
                conditions.append({"patient_id": pt["pid"]})
        except Exception:
            pass

    query = {}
    if conditions:
        query["$or"] = conditions

    cursor = db["appointments"].find(query).sort("created_at", -1)
    appointments = await cursor.to_list(length=100)

    # Pre-fetch doctor mapping
    doc_cursor = db["doctors"].find({})
    doctors = await doc_cursor.to_list(length=100)
    doc_map = {str(d["_id"]): d.get("name", "Doctor") for d in doctors}

    # Pre-fetch department mapping
    dept_cursor = db["departments"].find({})
    departments = await dept_cursor.to_list(length=100)
    dept_map = {str(d["_id"]): d.get("name", "General") for d in departments}

    result = []
    for a in appointments:
        for k, v in list(a.items()):
            if isinstance(v, ObjectId):
                a[k] = str(v)

        doc_id = a.get("doctor_id")
        if doc_id and str(doc_id) in doc_map and not a.get("doctor_name"):
            a["doctor_name"] = doc_map[str(doc_id)]
        dept_id = a.get("department_id")
        if dept_id and str(dept_id) in dept_map and not a.get("department_name"):
            a["department_name"] = dept_map[str(dept_id)]

        entry = await db["queue_entries"].find_one({"appointment_id": a.get("id")})
        if entry:
            a["token_number"] = entry.get("token_number")
            if entry.get("status"):
                a["queue_status"] = entry.get("status")

        if a.get("created_at") and isinstance(a["created_at"], datetime):
            a["created_at"] = a["created_at"].isoformat()
        if a.get("updated_at") and isinstance(a["updated_at"], datetime):
            a["updated_at"] = a["updated_at"].isoformat()

        result.append(a)

    return result

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


