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

    # Automatically queue the patient into the respective department (Book walk-in appointment)
    if data.get("department_id"):
        try:
            hospital_id = data["hospital_id"]
            dept_id = data["department_id"]
            
            # Find an active doctor for this department
            doctor = await db["doctors"].find_one({
                "hospital_id": hospital_id,
                "department_id": dept_id,
                "status": "ACTIVE"
            })
            if not doctor:
                doctor = await db["doctors"].find_one({
                    "hospital_id": hospital_id,
                    "department_id": dept_id
                })
            if not doctor:
                doctor = await db["doctors"].find_one({"hospital_id": hospital_id})

            doctor_id = str(doctor["_id"]) if doctor else "walkin_doctor"
            doctor_name = doctor.get("name") if doctor else "Duty Doctor"

            # Parse fee from doctor or input
            raw_fee = data.get("total_fee") or (doctor.get("consultation_fee") if doctor else 500.0) or 500.0
            total_fee = float(raw_fee)
            payment_status = data.get("payment_status") or "DONE"
            paid_amount = total_fee if payment_status == "DONE" else (total_fee * 0.2)
            remaining_amount = 0.0 if payment_status == "DONE" else (total_fee * 0.8)

            db_dict["total_fee"] = total_fee
            db_dict["payment_status"] = payment_status
            db_dict["paid_amount"] = paid_amount
            db_dict["remaining_amount"] = remaining_amount
            await db["patients"].update_one(
                {"_id": ObjectId(db_dict["id"])},
                {"$set": {
                    "total_fee": total_fee,
                    "payment_status": payment_status,
                    "paid_amount": paid_amount,
                    "remaining_amount": remaining_amount
                }}
            )

            # 1. Create Appointment
            appointment_date = now_ist.strftime("%Y-%m-%d")
            appt_dict = {
                "hospital_id": hospital_id,
                "department_id": dept_id,
                "department_name": data.get("department_name", "General"),
                "doctor_id": doctor_id,
                "doctor_name": doctor_name,
                "patient_id": db_dict["id"],
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

            # 2. Add to Queue
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
                patient_id=db_dict["id"],
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
            from routes.queue import manager
            await manager.broadcast_queue_update(doctor_id, {
                "event": "new_patient",
                "token_number": token_num,
                "patient_name": data["name"],
                "appointment_id": appt_id
            })

            db_dict["appointment_id"] = appt_id
            db_dict["token_number"] = token_num
        except Exception as e:
            print(f"Error auto-queuing patient into department: {e}")

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

    result = []
    for p in patients:
        p["id"] = str(p["_id"])
        result.append(PatientResponse(**p))
    return result
