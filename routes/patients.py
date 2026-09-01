from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional
from models.patient import PatientCreate, PatientResponse, PatientInDB
from database import get_db
from core.pid_generator import generate_unique_pid
from bson import ObjectId
from datetime import datetime, timezone, timedelta
import re

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

@router.get("/check-duplicate")
async def check_patient_duplicate(
    hospital_id: str,
    phone: str,
    name: Optional[str] = None,
    dob: Optional[str] = None,
    age: Optional[int] = None,
    gender: Optional[str] = None,
    doctor_id: Optional[str] = None,
    department_id: Optional[str] = None,
    db = Depends(get_db)
):
    """Pre-check if an appointment already exists for this patient identity on today's date."""
    now_ist = get_ist_now()
    appointment_date = now_ist.strftime("%Y-%m-%d")
    input_phone = phone.strip()
    input_name = (name or "").strip()
    input_dob = (dob or "").replace("-", "/").strip()
    input_age = int(age or 0)
    input_gender = (gender or "").strip().lower()

    if not input_phone:
        return {"has_duplicate": False}

    existing_patients = await db["patients"].find({
        "hospital_id": hospital_id,
        "phone": input_phone
    }).to_list(50)

    matched_patient = None
    for ep in existing_patients:
        ep_name = str(ep.get("name") or "").strip().lower()
        ep_gender = str(ep.get("gender") or "").strip().lower()
        ep_dob = str(ep.get("dob") or "").replace("-", "/").strip()
        ep_age = int(ep.get("age") or 0)

        name_match = not input_name or (ep_name == input_name.lower()) or (ep_name in input_name.lower()) or (input_name.lower() in ep_name)
        gender_match = not input_gender or (not ep_gender) or (ep_gender == input_gender) or (ep_gender in ("other", "-"))
        dob_match = bool(ep_dob and input_dob and ep_dob == input_dob)
        age_match = bool(ep_age > 0 and input_age > 0 and abs(ep_age - input_age) <= 1)
        age_dob_match = dob_match or age_match or (not ep_dob and ep_age == 0) or (not input_dob and input_age == 0)

        if name_match and gender_match and age_dob_match:
            matched_patient = ep
            break

    if not matched_patient:
        return {"has_duplicate": False}

    # Resolve doctor
    target_doctor_id = doctor_id
    if not target_doctor_id and department_id:
        doc = await db["doctors"].find_one({"hospital_id": hospital_id, "department_id": department_id, "status": "ACTIVE"})
        if not doc:
            doc = await db["doctors"].find_one({"hospital_id": hospital_id, "department_id": department_id})
        if doc:
            target_doctor_id = str(doc["_id"])

    if not target_doctor_id:
        return {"has_duplicate": False, "matched_patient": {"pid": matched_patient.get("pid"), "name": matched_patient.get("name")}}

    matched_pid = matched_patient.get("pid")
    appt_query = {
        "hospital_id": hospital_id,
        "doctor_id": target_doctor_id,
        "appointment_date": appointment_date,
        "status": {"$nin": ["CANCELLED", "NO_SHOW"]},
        "$or": [
            {"patient_phone": input_phone},
            {"patient_id": matched_pid},
            {"patient_id": str(matched_patient.get("_id"))},
            {"patient_name": {"$regex": f"^{re.escape(input_name)}$", "$options": "i"}}
        ]
    }
    existing_appt = await db["appointments"].find_one(appt_query)
    if existing_appt:
        q_entry = await db["queue_entries"].find_one({"appointment_id": str(existing_appt.get("_id"))})
        token_num = q_entry.get("token_number") if q_entry else (existing_appt.get("token_number") or "Assigned")
        return {
            "has_duplicate": True,
            "existing_appointment": {
                "appointment_id": str(existing_appt.get("_id")),
                "pid": matched_pid or existing_appt.get("patient_id") or "CS-P-PENDING",
                "patient_name": existing_appt.get("patient_name") or input_name,
                "patient_phone": input_phone,
                "doctor_name": existing_appt.get("doctor_name") or "Attending Specialist",
                "department_name": existing_appt.get("department_name") or "General",
                "appointment_date": appointment_date,
                "time_slot": existing_appt.get("time_slot") or "Regular OPD",
                "status": existing_appt.get("status") or "CONFIRMED",
                "booking_source": existing_appt.get("booking_source") or "CareSeva App",
                "token_number": token_num,
                "total_fee": float(existing_appt.get("total_fee") or 500.0),
                "payment_status": existing_appt.get("payment_status") or "DONE"
            }
        }

    return {"has_duplicate": False, "matched_patient": {"pid": matched_pid, "name": matched_patient.get("name")}}

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

    hospital_id = str(data.get("hospital_id") or "")
    dept_id = str(data.get("department_id") or "")
    input_phone = str(data.get("phone") or "").strip()
    input_name = str(data.get("name") or "").strip()
    input_dob = str(data.get("dob") or "").replace("-", "/").strip()
    input_age = int(data.get("age") or 0)
    input_gender = str(data.get("gender") or "").strip().lower()
    appointment_date = now_ist.strftime("%Y-%m-%d")

    # Resolve target doctor
    doctor = None
    if data.get("doctor_id"):
        try:
            doctor = await db["doctors"].find_one({"_id": ObjectId(data["doctor_id"])})
        except Exception:
            pass
    if not doctor and dept_id:
        doctor = await db["doctors"].find_one({
            "hospital_id": hospital_id,
            "department_id": dept_id,
            "status": "ACTIVE"
        })
    if not doctor and dept_id:
        doctor = await db["doctors"].find_one({
            "hospital_id": hospital_id,
            "department_id": dept_id
        })
    if not doctor:
        doctor = await db["doctors"].find_one({"hospital_id": hospital_id})

    doctor_id = str(doctor["_id"]) if doctor else (data.get("doctor_id") or "walkin_doctor")
    doctor_name = doctor.get("name") if doctor else (data.get("doctor_name") or "Duty Doctor")
    
    # Resolve department name
    if not data.get("department_name"):
        if doctor and doctor.get("department_name"):
            data["department_name"] = doctor.get("department_name")
        elif dept_id:
            try:
                dept = await db["departments"].find_one({"_id": ObjectId(dept_id)})
                if dept:
                    data["department_name"] = dept.get("name", "General")
            except Exception:
                data["department_name"] = "General"
        else:
            data["department_name"] = "General"

    dept_name = data["department_name"]

    # 1. Check if phone number matches any existing patient in this hospital
    matched_patient = None
    if input_phone:
        existing_patients = await db["patients"].find({
            "hospital_id": hospital_id,
            "phone": input_phone
        }).to_list(50)

        for ep in existing_patients:
            ep_name = str(ep.get("name") or "").strip().lower()
            ep_gender = str(ep.get("gender") or "").strip().lower()
            ep_dob = str(ep.get("dob") or "").replace("-", "/").strip()
            ep_age = int(ep.get("age") or 0)

            # Check if all fields match:
            # Name match (case-insensitive)
            name_match = (ep_name == input_name.lower()) or (ep_name in input_name.lower()) or (input_name.lower() in ep_name)
            
            # Gender match
            gender_match = (not ep_gender) or (ep_gender == input_gender) or (ep_gender in ("other", "-"))
            
            # DOB or Age match
            dob_match = bool(ep_dob and input_dob and ep_dob == input_dob)
            age_match = bool(ep_age > 0 and input_age > 0 and abs(ep_age - input_age) <= 1)
            age_dob_match = dob_match or age_match or (not ep_dob and ep_age == 0)

            if name_match and gender_match and age_dob_match:
                matched_patient = ep
                break

    # 2. If matched patient exists, check for duplicate appointment with the same doctor on the same day:
    if matched_patient:
        matched_pid = matched_patient.get("pid")
        
        appt_query = {
            "hospital_id": hospital_id,
            "doctor_id": doctor_id,
            "appointment_date": appointment_date,
            "status": {"$nin": ["CANCELLED", "NO_SHOW"]},
            "$or": [
                {"patient_phone": input_phone},
                {"patient_id": matched_pid},
                {"patient_id": str(matched_patient.get("_id"))},
                {"patient_name": {"$regex": f"^{re.escape(input_name)}$", "$options": "i"}}
            ]
        }
        existing_appt = await db["appointments"].find_one(appt_query)

        if existing_appt:
            q_entry = await db["queue_entries"].find_one({
                "appointment_id": str(existing_appt.get("_id"))
            })
            token_num = q_entry.get("token_number") if q_entry else (existing_appt.get("token_number") or existing_appt.get("token") or "Assigned")

            raise HTTPException(
                status_code=409,
                detail={
                    "code": "DUPLICATE_APPOINTMENT",
                    "message": f"Patient already has an active appointment with {doctor_name} on {appointment_date}.",
                    "existing_appointment": {
                        "appointment_id": str(existing_appt.get("_id")),
                        "pid": matched_pid or existing_appt.get("patient_id") or "CS-P-PENDING",
                        "patient_name": existing_appt.get("patient_name") or input_name,
                        "patient_phone": input_phone,
                        "doctor_name": doctor_name,
                        "department_name": existing_appt.get("department_name") or dept_name,
                        "appointment_date": appointment_date,
                        "time_slot": existing_appt.get("time_slot") or "Regular OPD",
                        "status": existing_appt.get("status") or "CONFIRMED",
                        "booking_source": existing_appt.get("booking_source") or "CareSeva App",
                        "token_number": token_num,
                        "total_fee": float(existing_appt.get("total_fee") or 500.0),
                        "payment_status": existing_appt.get("payment_status") or "DONE"
                    }
                }
            )

    # 3. Patient is allowed to book (either new patient, or existing patient booking a DIFFERENT doctor)
    raw_fee = data.get("total_fee") or (doctor.get("consultation_fee") if doctor else 500.0) or 500.0
    total_fee = float(raw_fee)
    payment_status = data.get("payment_status") or "DONE"
    paid_amount = total_fee if payment_status == "DONE" else (total_fee * 0.2)
    remaining_amount = 0.0 if payment_status == "DONE" else (total_fee * 0.8)

    data["total_fee"] = total_fee
    data["payment_status"] = payment_status
    data["paid_amount"] = paid_amount
    data["remaining_amount"] = remaining_amount
    data["department_name"] = dept_name

    if matched_patient:
        # Re-use existing PID and existing patient document
        unique_pid = matched_patient.get("pid")
        patient_db_id = str(matched_patient["_id"])
        data["pid"] = unique_pid
        data["id"] = patient_db_id

        await db["patients"].update_one(
            {"_id": matched_patient["_id"]},
            {"$set": {
                "last_visit": appointment_date,
                "department_id": dept_id,
                "department_name": dept_name,
                "updated_at": now_ist,
                "total_fee": total_fee,
                "paid_amount": paid_amount,
                "remaining_amount": remaining_amount,
                "payment_status": payment_status
            }}
        )
        db_dict = {**matched_patient, **data, "id": patient_db_id}
    else:
        # Generate brand new unique PID
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
        patient_db_id = str(result.inserted_id)
        db_dict["id"] = patient_db_id

    # 4. Create Walk-in Appointment
    appt_dict = {
        "hospital_id": hospital_id,
        "department_id": dept_id,
        "department_name": dept_name,
        "doctor_id": doctor_id,
        "doctor_name": doctor_name,
        "patient_id": unique_pid,
        "patient_name": data["name"],
        "patient_age": data.get("age"),
        "patient_gender": data.get("gender"),
        "patient_phone": data.get("phone"),
        "booking_for": "myself",
        "appointment_date": appointment_date,
        "status": "BOOKED",
        "booking_source": "DIRECT_WALKIN",
        "payment_status": payment_status,
        "payment_option": "full" if payment_status == "DONE" else "advance",
        "total_fee": total_fee,
        "paid_amount": paid_amount,
        "remaining_amount": remaining_amount,
        "created_at": now_ist,
        "updated_at": now_ist
    }
    appt_res = await db["appointments"].insert_one(appt_dict)
    appt_id = str(appt_res.inserted_id)

    # 5. Add to Doctor's Queue
    queue = await db["queues"].find_one({
        "hospital_id": hospital_id,
        "doctor_id": doctor_id,
        "status": "ACTIVE"
    })

    if not queue:
        from models.queue import QueueInDB
        new_queue = QueueInDB(
            id="",
            hospital_id=hospital_id,
            department_id=dept_id,
            doctor_id=doctor_id,
            created_at=now_ist,
            updated_at=now_ist,
            total_tokens=0,
            current_token=0
        )
        q_dict = new_queue.dict(exclude={"id"})
        res_q = await db["queues"].insert_one(q_dict)
        queue_id = str(res_q.inserted_id)
        token_num = 1
    else:
        queue_id = str(queue["_id"])
        token_num = (queue.get("total_tokens") or 0) + 1

    await db["queues"].update_one({"_id": ObjectId(queue_id)}, {"$inc": {"total_tokens": 1}})

    from models.queue import QueueEntryInDB
    db_entry = QueueEntryInDB(
        id="",
        queue_id=queue_id,
        patient_id=unique_pid,
        patient_name=data["name"],
        token_number=token_num,
        hospital_id=hospital_id,
        department_id=dept_id,
        doctor_id=doctor_id,
        appointment_id=appt_id,
        status="WAITING",
        created_at=now_ist,
        updated_at=now_ist
    )
    await db["queue_entries"].insert_one(db_entry.dict(exclude={"id"}))

    # Broadcast to WebSocket
    try:
        from routes.queue import manager
        await manager.broadcast_queue_update(doctor_id, {
            "event": "new_patient",
            "token_number": token_num,
            "patient_name": data["name"],
            "appointment_id": appt_id
        })
    except Exception:
        pass

    db_dict["appointment_id"] = appt_id
    db_dict["token_number"] = token_num

    return PatientResponse(**db_dict)


@router.patch("/{patient_id}/complete-payment", response_model=PatientResponse)
async def complete_patient_payment(patient_id: str, db = Depends(get_db)):
    """Counter fee settlement: Marks remaining 80% fee as paid and updates status to DONE."""
    query = {}
    try:
        query = {"_id": ObjectId(patient_id)}
    except Exception:
        query = {"pid": patient_id}

    patient = await db["patients"].find_one(query)
    if not patient and "pid" not in query:
        patient = await db["patients"].find_one({"pid": patient_id})

    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    total_fee = float(patient.get("total_fee") or 500.0)
    now_ist = datetime.now(IST)

    update_fields = {
        "payment_status": "DONE",
        "paid_amount": total_fee,
        "remaining_amount": 0.0,
        "updated_at": now_ist
    }

    await db["patients"].update_one({"_id": patient["_id"]}, {"$set": update_fields})

    # If linked appointment exists, also update appointment payment_status to DONE
    if patient.get("appointment_id"):
        try:
            await db["appointments"].update_one(
                {"_id": ObjectId(patient["appointment_id"])},
                {"$set": {
                    "payment_status": "DONE",
                    "paid_amount": total_fee,
                    "remaining_amount": 0.0,
                    "updated_at": now_ist
                }}
            )
        except Exception:
            pass

    updated = await db["patients"].find_one({"_id": patient["_id"]})
    updated["id"] = str(updated["_id"])
    return PatientResponse(**updated)

@router.get("/hospital/{hospital_id}", response_model=List[PatientResponse])
async def get_hospital_patients(hospital_id: str, search: Optional[str] = None, db = Depends(get_db)):
    """Fetch all patients for a hospital with fast batch queries and optimized consolidation."""
    now_ist = get_ist_now()

    query = {"hospital_id": hospital_id}
    if search:
        s = search.strip()
        query["$or"] = [
            {"name": {"$regex": s, "$options": "i"}},
            {"pid": {"$regex": s, "$options": "i"}},
            {"phone": {"$regex": s, "$options": "i"}},
            {"department_name": {"$regex": s, "$options": "i"}}
        ]

    # Sorted by most recent activity/visit (updated_at) descending, falling back to created_at
    cursor = db["patients"].find(query).sort([("updated_at", -1), ("created_at", -1)])
    patients = await cursor.to_list(length=500)

    # If patients collection is empty for this hospital, do an automatic initial sync from appointments
    if not patients and not search:
        try:
            appts = await db["appointments"].find({"hospital_id": hospital_id}).to_list(100)
            for a in appts:
                phone = a.get("patient_phone")
                name = a.get("patient_name")
                appt_id = str(a.get("_id"))
                
                pid = a.get("patient_id")
                if not pid or not pid.startswith("CS-P-"):
                    pid = await generate_unique_pid(db)

                new_p = {
                    "pid": pid,
                    "name": name or "Unknown Patient",
                    "phone": phone or "",
                    "email": None,
                    "blood_group": None,
                    "dob": None,
                    "age": a.get("patient_age") or 0,
                    "gender": a.get("patient_gender") or "-",
                    "department_id": a.get("department_id"),
                    "department_name": a.get("department_name") or "General",
                    "last_visit": a.get("appointment_date") or now_ist.strftime("%Y-%m-%d"),
                    "registration_source": a.get("booking_source") or "CARESEVA_APP",
                    "hospital_id": hospital_id,
                    "appointment_id": appt_id,
                    "payment_status": a.get("payment_status") or "DONE",
                    "payment_option": a.get("payment_option") or "full",
                    "total_fee": float(a.get("total_fee") or 500.0),
                    "paid_amount": float(a.get("paid_amount") or 500.0),
                    "remaining_amount": float(a.get("remaining_amount") or 0.0),
                    "created_at": a.get("created_at") or now_ist,
                    "updated_at": a.get("updated_at") or now_ist
                }
                await db["patients"].insert_one(new_p)

            cursor = db["patients"].find(query).sort([("updated_at", -1), ("created_at", -1)])
            patients = await cursor.to_list(length=500)
        except Exception as e:
            print(f"Error during automatic appointment patient sync: {e}")

    # Fast batch enrichment of user profiles (dob, age, blood_group) in a single query
    phones_to_check = list({
        p["phone"] for p in patients 
        if p.get("phone") and (not p.get("blood_group") or not p.get("dob") or not p.get("age"))
    })
    if phones_to_check:
        try:
            users = await db["users"].find({"phone": {"$in": phones_to_check}}).to_list(len(phones_to_check))
            users_by_phone = {u["phone"]: u for u in users if u.get("phone")}
            for p in patients:
                user = users_by_phone.get(p.get("phone"))
                if user:
                    if not p.get("blood_group") and user.get("blood_group"):
                        p["blood_group"] = user.get("blood_group")
                    if not p.get("dob") and user.get("dob"):
                        p["dob"] = user.get("dob")
                    if (not p.get("age") or p.get("age") == 0) and user.get("age"):
                        p["age"] = user.get("age")
        except Exception as e:
            print(f"Error during batch user enrichment: {e}")

    seen_identities = set()
    deduped_patients = []
    for p in patients:
        phone = (p.get("phone") or "").strip()
        name = (p.get("name") or "").strip().lower()
        key = (phone, name) if phone and name else str(p.get("_id"))
        if key not in seen_identities:
            seen_identities.add(key)
            deduped_patients.append(p)

    result = []
    for p in deduped_patients:
        p["id"] = str(p["_id"])
        result.append(PatientResponse(**p))
    return result

@router.get("/hospital/{hospital_id}/directory")
async def get_hospital_patient_directory(hospital_id: str, db = Depends(get_db)):
    """Comprehensive Medico-Legal Patient Master Register & Directory for Government Compliance with batch queries."""
    from collections import defaultdict

    patients = await db["patients"].find({"hospital_id": hospital_id}).sort("created_at", -1).to_list(length=500)
    if not patients:
        await get_hospital_patients(hospital_id, db=db)
        patients = await db["patients"].find({"hospital_id": hospital_id}).sort("created_at", -1).to_list(length=500)

    # 1. Batch fetch users by phone in a single query
    phones = list({p["phone"] for p in patients if p.get("phone")})
    users_by_phone = {}
    if phones:
        try:
            users = await db["users"].find({"phone": {"$in": phones}}).to_list(len(phones))
            users_by_phone = {u["phone"]: u for u in users if u.get("phone")}
        except Exception:
            pass

    # 2. Batch fetch all appointments for this hospital in a single query
    all_appts = await db["appointments"].find({"hospital_id": hospital_id}).sort("created_at", -1).to_list(1000)
    appts_by_phone = defaultdict(list)
    appts_by_pid = defaultdict(list)
    appts_by_name = defaultdict(list)
    for a in all_appts:
        if a.get("patient_phone"):
            appts_by_phone[a["patient_phone"]].append(a)
        if a.get("patient_id"):
            appts_by_pid[a["patient_id"]].append(a)
        if a.get("patient_name"):
            appts_by_name[a["patient_name"].strip().lower()].append(a)

    directory = []

    for p in patients:
        phone = p.get("phone")
        pid = p.get("pid")
        name = p.get("name") or "Unknown"
        user = users_by_phone.get(phone)

        # Retrieve appointments in memory with deduplication
        seen_ids = set()
        appts = []
        candidates = (
            (appts_by_phone.get(phone, []) if phone else []) +
            (appts_by_pid.get(pid, []) if pid else []) +
            (appts_by_name.get(name.strip().lower(), []) if name else [])
        )
        for cand in candidates:
            cid = str(cand["_id"])
            if cid not in seen_ids:
                seen_ids.add(cid)
                appts.append(cand)

        depts = list({a.get("department_name") for a in appts if a.get("department_name")})
        if not depts and p.get("department_name"):
            depts = [p.get("department_name")]

        total_billed = sum(float(a.get("total_fee") or 500.0) for a in appts) or float(p.get("total_fee") or 500.0)
        total_paid = sum(float(a.get("paid_amount") or 500.0) for a in appts) or float(p.get("paid_amount") or 500.0)
        balance_due = max(0.0, total_billed - total_paid)

        history = []
        for a in appts:
            dt_str = a.get("appointment_date")
            if not dt_str and a.get("created_at"):
                c_at = a.get("created_at")
                dt_str = c_at.strftime("%Y-%m-%d") if isinstance(c_at, datetime) else str(c_at)[:10]
            history.append({
                "appointment_id": str(a.get("_id")),
                "date": dt_str or "-",
                "time_slot": a.get("time_slot") or "Regular OPD",
                "doctor_name": a.get("doctor_name") or "Attending Specialist",
                "department_name": a.get("department_name") or "General",
                "status": a.get("status") or "CONFIRMED",
                "payment_status": a.get("payment_status") or "DONE",
                "booking_source": a.get("booking_source") or p.get("registration_source") or "CARESEVA_APP",
                "total_fee": float(a.get("total_fee") or 500.0),
                "paid_amount": float(a.get("paid_amount") or 500.0),
                "remaining_amount": float(a.get("remaining_amount") or 0.0),
            })

        created_dt = p.get("created_at")
        created_str = created_dt.strftime("%Y-%m-%d %H:%M") if isinstance(created_dt, datetime) else str(created_dt or "-")

        entry = {
            "id": str(p.get("_id")),
            "pid": pid or "CS-P-PENDING",
            "name": name,
            "phone": phone or "-",
            "email": (user.get("email") if user else None) or p.get("email") or "-",
            "age": p.get("age") or (user.get("age") if user else 0),
            "dob": (user.get("dob") if user else None) or p.get("dob") or "-",
            "gender": p.get("gender") or (user.get("gender") if user else "-"),
            "blood_group": (user.get("blood_group") if user else None) or p.get("blood_group") or "Not Specified",
            "registration_source": p.get("registration_source") or "CARESEVA_APP",
            "total_visits": len(appts) or 1,
            "departments": depts,
            "first_visit": history[-1]["date"] if history else (p.get("last_visit") or "-"),
            "last_visit": history[0]["date"] if history else (p.get("last_visit") or "-"),
            "total_billed": total_billed,
            "total_paid": total_paid,
            "balance_due": balance_due,
            "history": history,
            "compliance_status": "VERIFIED_RECORD",
            "registered_at": created_str,
            "registry_code": f"GOV-REG-{pid or 'CS'}"
        }
        directory.append(entry)

    return directory
