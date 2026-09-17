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

DEFAULT_TIME_SLOTS = [
    "09:00 AM - 09:30 AM",
    "09:30 AM - 10:00 AM",
    "10:00 AM - 10:30 AM",
    "10:30 AM - 11:00 AM",
    "11:00 AM - 11:30 AM",
    "11:30 AM - 12:00 PM",
    "02:00 PM - 02:30 PM",
    "02:30 PM - 03:00 PM",
    "03:00 PM - 03:30 PM",
    "04:00 PM - 04:30 PM",
    "04:30 PM - 05:00 PM",
]

def parse_time_str(t_str: str) -> Optional[datetime.time]:
    """Parse time strings like '09:00 AM', '9:30 AM', '14:00', '02:00 PM' into time object."""
    if not t_str:
        return None
    clean = t_str.strip().upper()
    for fmt in ("%I:%M %p", "%I:%M%p", "%H:%M", "%I %p"):
        try:
            return datetime.strptime(clean, fmt).time()
        except ValueError:
            pass
    return None

def parse_slot_start_end(slot_str: str) -> tuple[Optional[datetime.time], Optional[datetime.time]]:
    """Parses '09:00 AM - 09:30 AM' or '09:00 AM' into (start_time, end_time)."""
    if not slot_str:
        return (None, None)
    parts = slot_str.split("-")
    if len(parts) >= 2:
        start_t = parse_time_str(parts[0].strip())
        end_t = parse_time_str(parts[1].strip())
        return (start_t, end_t)
    elif len(parts) == 1:
        start_t = parse_time_str(parts[0].strip())
        return (start_t, None)
    return (None, None)

def extract_slot_and_date(slot_str: Optional[str], date_str: Optional[str]) -> tuple[str, str]:
    """
    Extracts actual slot string and clean date string.
    E.g. if date_str = "Today, Sep 17 (04:30 PM - 05:00 PM)" and slot_str = "10:00 AM",
    returns ("04:30 PM - 05:00 PM", "Today, Sep 17").
    """
    final_slot = (slot_str or "").strip()
    final_date = (date_str or "").strip()

    if "(" in final_date and ")" in final_date:
        start_idx = final_date.find("(")
        end_idx = final_date.find(")")
        if end_idx > start_idx:
            extracted_slot = final_date[start_idx + 1:end_idx].strip()
            final_date = final_date[:start_idx].strip()
            if not final_slot or final_slot == "10:00 AM" or ("M" in extracted_slot and extracted_slot != final_slot):
                final_slot = extracted_slot

    return (final_slot, final_date)

def is_slot_expired(slot_str: str, appointment_date_str: str, now_ist: datetime) -> bool:
    """
    Returns True if slot_str on appointment_date_str has expired relative to now_ist.
    Past date: True.
    Future date: False.
    Today: True if current IST time >= slot start_time (or end_time).
    """
    if not appointment_date_str:
        return False
    
    actual_slot, actual_date = extract_slot_and_date(slot_str, appointment_date_str)
    if not actual_slot:
        return False

    target_date_str = str(actual_date).strip()
    d_lower = target_date_str.lower()
    if "today" in d_lower:
        target_date_str = now_ist.strftime("%Y-%m-%d")
    elif "tomorrow" in d_lower:
        target_date_str = (now_ist + timedelta(days=1)).strftime("%Y-%m-%d")
    elif "yesterday" in d_lower:
        target_date_str = (now_ist - timedelta(days=1)).strftime("%Y-%m-%d")
    
    today_str = now_ist.strftime("%Y-%m-%d")

    try:
        raw_part = target_date_str.split()[0].replace(",", "")
        target_date = datetime.strptime(raw_part, "%Y-%m-%d").date()
        today_date = now_ist.date()

        if target_date < today_date:
            return True
        elif target_date > today_date:
            return False
    except Exception:
        pass

    start_t, end_t = parse_slot_start_end(actual_slot)
    if not start_t:
        return False
    
    current_t = now_ist.time()
    if current_t >= start_t:
        return True
    return False

from core.security import get_current_user, get_optional_current_user

@router.get("/available-slots")
async def get_available_slots(
    hospital_id: Optional[str] = None,
    doctor_id: Optional[str] = None,
    date: Optional[str] = None,
    db = Depends(get_db)
):
    now_ist = get_ist_now()
    if not date:
        date_str = now_ist.strftime("%Y-%m-%d")
    else:
        d_lower = str(date).strip().lower()
        if "today" in d_lower:
            date_str = now_ist.strftime("%Y-%m-%d")
        elif "tomorrow" in d_lower:
            date_str = (now_ist + timedelta(days=1)).strftime("%Y-%m-%d")
        else:
            date_str = date.split()[0].replace(",", "")

    max_capacity_per_slot = 3
    if doctor_id:
        try:
            slot_config = await db["slot_configurations"].find_one({"doctor_id": doctor_id})
            if slot_config:
                max_capacity_per_slot = slot_config.get("max_app_tokens_per_slot", 3)
        except Exception:
            pass

    query = {
        "appointment_date": {"$regex": date_str, "$options": "i"},
        "status": {"$nin": ["CANCELLED", "NO_SHOW"]}
    }
    if doctor_id:
        query["doctor_id"] = doctor_id
    elif hospital_id:
        query["hospital_id"] = hospital_id

    existing_appts = await db["appointments"].find(query).to_list(length=500)
    
    slot_counts = {}
    for appt in existing_appts:
        slot_key = appt.get("time_slot") or appt.get("appointment_time")
        if slot_key:
            slot_counts[slot_key] = slot_counts.get(slot_key, 0) + 1

    result_slots = []
    for slot in DEFAULT_TIME_SLOTS:
        start_t, end_t = parse_slot_start_end(slot)
        expired = is_slot_expired(slot, date_str, now_ist)
        booked_cnt = slot_counts.get(slot, 0)
        is_full = booked_cnt >= max_capacity_per_slot
        
        result_slots.append({
            "slot": slot,
            "start_time": start_t.strftime("%I:%M %p") if start_t else "",
            "end_time": end_t.strftime("%I:%M %p") if end_t else "",
            "is_expired": expired,
            "is_full": is_full,
            "is_available": (not expired) and (not is_full),
            "booked_count": booked_cnt,
            "max_capacity": max_capacity_per_slot
        })

    return {
        "date": date_str,
        "doctor_id": doctor_id,
        "hospital_id": hospital_id,
        "slots": result_slots
    }

@router.post("/", response_model=AppointmentResponse)
async def create_appointment(
    appointment: AppointmentCreate,
    current_user: Optional[dict] = Depends(get_optional_current_user),
    db = Depends(get_db)
):
    appt_data = appointment.dict()
    now_ist = get_ist_now()

    # Assign booking_user_id from authenticated user token if available
    if current_user:
        auth_uid = current_user.get("sub") or current_user.get("id")
        if auth_uid and not appt_data.get("booking_user_id"):
            appt_data["booking_user_id"] = auth_uid

    # Extract actual slot and clean date if embedded like "Today, Sep 17 (04:30 PM - 05:00 PM)"
    raw_slot = appt_data.get("time_slot") or appt_data.get("appointment_time")
    raw_date = appt_data.get("appointment_date")
    actual_slot, actual_date = extract_slot_and_date(raw_slot, raw_date)

    if actual_slot:
        appt_data["time_slot"] = actual_slot
        appt_data["appointment_time"] = actual_slot

    # Normalize human labels like "Today, Aug 28" to YYYY-MM-DD
    if not actual_date:
        appt_data["appointment_date"] = now_ist.strftime("%Y-%m-%d")
    else:
        d_str = str(actual_date).strip().lower()
        if "today" in d_str:
            appt_data["appointment_date"] = now_ist.strftime("%Y-%m-%d")
        elif "tomorrow" in d_str:
            appt_data["appointment_date"] = (now_ist + timedelta(days=1)).strftime("%Y-%m-%d")
        elif "yesterday" in d_str:
            appt_data["appointment_date"] = (now_ist - timedelta(days=1)).strftime("%Y-%m-%d")
        else:
            appt_data["appointment_date"] = actual_date.split()[0].replace(",", "")

    # SLOT EXPIRATION CHECK: Prevent booking expired slots for Today
    slot_to_check = appt_data.get("time_slot") or appt_data.get("appointment_time")
    if slot_to_check and is_slot_expired(slot_to_check, appt_data["appointment_date"], now_ist):
        raise HTTPException(
            status_code=400,
            detail=f"The selected time slot '{slot_to_check}' has already passed for {appt_data['appointment_date']}. Please choose an upcoming time slot."
        )

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

    queue_date_str = appt_data.get("appointment_date", now_ist.strftime("%Y-%m-%d"))

    queue = await db["queues"].find_one({
        "hospital_id": hospital_id,
        "doctor_id": doctor_id,
        "queue_date": queue_date_str,
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
            queue_date=queue_date_str,
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
    
    # Create entry with linked appointment_id and booking_user_id
    from models.queue import QueueEntryInDB
    entry_booking_uid = appt_data.get("booking_user_id") or patient_id
    db_entry = QueueEntryInDB(
        id="",
        queue_id=queue_id,
        patient_id=patient_id,
        patient_name=patient_name,
        patient_phone=patient_phone,
        booking_user_id=entry_booking_uid,
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
    booking_user_id: Optional[str] = None,
    current_user: Optional[dict] = Depends(get_optional_current_user),
    db = Depends(get_db)
):
    """Retrieve all past and upcoming appointments for a patient with detailed metadata."""
    conditions = []
    
    # Priority 1: Check authenticated user identity
    if current_user:
        auth_uid = current_user.get("sub") or current_user.get("id")
        auth_phone = current_user.get("phone")
        auth_pid = current_user.get("pid")

        if auth_uid:
            conditions.append({"booking_user_id": auth_uid})
        if auth_pid:
            conditions.append({"patient_id": auth_pid})
        if auth_phone:
            clean_p = auth_phone.strip().replace(" ", "").replace("-", "")
            if clean_p.startswith("+91"):
                clean_p = clean_p[3:]
            conditions.append({"patient_phone": clean_p})
            conditions.append({"patient_phone": auth_phone})

    # Priority 2: Use query parameters
    if booking_user_id:
        conditions.append({"booking_user_id": booking_user_id})
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

    if not conditions:
        return []

    query = {"$or": conditions}

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

    # Pre-fetch hospital mapping
    hosp_cursor = db["hospitals"].find({})
    hospitals = await hosp_cursor.to_list(length=100)
    hosp_map = {str(h["_id"]): h.get("name", "Hospital") for h in hospitals}
    for h in hospitals:
        if h.get("hop_id"):
            hosp_map[str(h["hop_id"])] = h.get("name", "Hospital")

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
        hosp_id = a.get("hospital_id")
        if hosp_id and str(hosp_id) in hosp_map:
            a["hospital_name"] = hosp_map[str(hosp_id)]

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

@router.post("/{appointment_id}/consultation")
async def save_appointment_consultation(
    appointment_id: str,
    consultation_data: dict,
    db = Depends(get_db)
):
    """Save doctor diagnosis, prescription medications, notes, and follow-up date."""
    appt = await db["appointments"].find_one({"_id": ObjectId(appointment_id)})
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")

    now_ist = get_ist_now()
    prescription_obj = {
        "diagnosis": consultation_data.get("diagnosis", ""),
        "medicines": consultation_data.get("medicines", []),
        "notes": consultation_data.get("notes", ""),
        "follow_up_date": consultation_data.get("follow_up_date"),
        "doctor_name": appt.get("doctor_name") or consultation_data.get("doctor_name"),
        "doctor_id": appt.get("doctor_id"),
        "prescribed_at": now_ist.isoformat(),
    }

    new_status = consultation_data.get("status", "COMPLETED")

    update_fields = {
        "prescription": prescription_obj,
        "status": new_status,
        "updated_at": now_ist
    }

    await db["appointments"].update_one(
        {"_id": ObjectId(appointment_id)},
        {"$set": update_fields}
    )

    # If patient has record in patients collection, also link to medical_history
    patient_id = appt.get("patient_id")
    hospital_id = appt.get("hospital_id")
    if patient_id and hospital_id:
        try:
            await db["patients"].update_one(
                {"hospital_id": hospital_id, "$or": [{"pid": patient_id}, {"_id": ObjectId(patient_id)}]},
                {
                    "$push": {
                        "prescriptions": prescription_obj,
                        "medical_history": {
                            "date": now_ist.strftime("%Y-%m-%d"),
                            "diagnosis": prescription_obj["diagnosis"],
                            "doctor_name": prescription_obj["doctor_name"],
                            "notes": prescription_obj["notes"]
                        }
                    }
                }
            )
        except Exception:
            pass

    return {
        "message": "Consultation and prescription saved successfully",
        "appointment_id": appointment_id,
        "status": new_status,
        "prescription": prescription_obj
    }

@router.get("/patient/{patient_id}", response_model=List[AppointmentResponse])
async def get_patient_appointments_by_id(
    patient_id: str,
    current_user: Optional[dict] = Depends(get_optional_current_user),
    db = Depends(get_db)
):
    if current_user:
        auth_uid = current_user.get("sub") or current_user.get("id")
        auth_pid = current_user.get("pid")
        auth_phone = current_user.get("phone")
        if patient_id not in [auth_uid, auth_pid, auth_phone] and current_user.get("role") == "patient":
            raise HTTPException(status_code=403, detail="Access denied: You cannot view appointments for another patient.")

    cursor = db["appointments"].find({"patient_id": patient_id})
    appointments = await cursor.to_list(length=100)
    
    result = []
    for a in appointments:
        a["id"] = str(a["_id"])
        result.append(AppointmentResponse(**a))
    return result


