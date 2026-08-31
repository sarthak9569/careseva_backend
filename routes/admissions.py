from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional
from models.admission import AdmissionCreate, AdmissionResponse, AdmissionInDB, AdmissionUpdate
from database import get_db
from core.pid_generator import generate_unique_pid
from bson import ObjectId
from datetime import datetime, timezone, timedelta
import asyncio

router = APIRouter()

IST = timezone(timedelta(hours=5, minutes=30))

def get_ist_now() -> datetime:
    return datetime.now(IST)

async def generate_unique_ipd(db) -> str:
    counter = await db["counters"].find_one_and_update(
        {"_id": "ipd_admission_number"},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=True
    )
    seq = counter.get("seq", 1)
    if seq < 101:
        await db["counters"].update_one(
            {"_id": "ipd_admission_number"},
            {"$set": {"seq": 101}}
        )
        seq = 101
    year = get_ist_now().year
    return f"IPD-{year}-{seq:04d}"

def calculate_age_from_dob(dob_str: str) -> int:
    try:
        clean_dob = dob_str.strip().replace("/", "-")
        dob = datetime.strptime(clean_dob, "%Y-%m-%d").date()
        today = get_ist_now().date()
        age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        return max(0, age)
    except Exception:
        return 0

@router.post("/", response_model=AdmissionResponse)
async def admit_patient(admission: AdmissionCreate, db = Depends(get_db)):
    data = admission.dict()
    now_ist = get_ist_now()

    # Calculate exact age if dob given
    if data.get("patient_dob") and (data.get("patient_age") is None or data.get("patient_age") == 0):
        data["patient_age"] = calculate_age_from_dob(data["patient_dob"])
    elif data.get("patient_age") is None:
        data["patient_age"] = 0

    # Ensure admission_date & admission_time
    if not data.get("admission_date"):
        data["admission_date"] = now_ist.strftime("%Y-%m-%d")
    if not data.get("admission_time"):
        data["admission_time"] = now_ist.strftime("%I:%M %p")

    hospital_id = data["hospital_id"]
    dept_id = data.get("department_id")

    # Resolve department name
    if dept_id and not data.get("department_name"):
        try:
            dept = await db["departments"].find_one({"_id": ObjectId(dept_id)})
            if dept:
                data["department_name"] = dept.get("name", "General Medicine")
        except Exception:
            data["department_name"] = "General Medicine"

    # Resolve doctor name if doctor_id given
    if data.get("doctor_id") and not data.get("doctor_name"):
        try:
            doc = await db["doctors"].find_one({"_id": ObjectId(data["doctor_id"])})
            if doc:
                data["doctor_name"] = doc.get("name", "Attending Physician")
        except Exception:
            pass

    # Ensure patient has a PID in patients collection
    patient_id = data.get("patient_id")
    if not patient_id:
        existing = None
        if data.get("patient_phone"):
            existing = await db["patients"].find_one({
                "hospital_id": hospital_id,
                "phone": data["patient_phone"]
            })
        if existing:
            patient_id = existing.get("pid") or str(existing["_id"])
        else:
            unique_pid = await generate_unique_pid(db)
            new_p = {
                "pid": unique_pid,
                "name": data["patient_name"],
                "age": data["patient_age"],
                "gender": data["patient_gender"],
                "phone": data["patient_phone"],
                "hospital_id": hospital_id,
                "department_id": dept_id,
                "department_name": data.get("department_name", "General"),
                "registration_source": "HMS_IPD_ADMISSION",
                "payment_status": data.get("payment_status", "DONE"),
                "created_at": now_ist,
                "updated_at": now_ist
            }
            res = await db["patients"].insert_one(new_p)
            patient_id = unique_pid

    data["patient_id"] = patient_id

    # Generate sequential IPD Number
    ipd_no = await generate_unique_ipd(db)
    data["ipd_number"] = ipd_no
    data["status"] = "ICU" if "icu" in (data.get("ward_type", "").lower()) else "ADMITTED"

    # Remove temporary creation fields not in base model
    data.pop("patient_dob", None)

    db_admission = AdmissionInDB(
        **data,
        id="",
        created_at=now_ist,
        updated_at=now_ist
    )

    db_dict = db_admission.dict(exclude={"id"})
    result = await db["admissions"].insert_one(db_dict)
    db_dict["id"] = str(result.inserted_id)

    return AdmissionResponse(**db_dict)

@router.get("/hospital/{hospital_id}", response_model=List[AdmissionResponse])
async def get_hospital_admissions(
    hospital_id: str,
    department_id: Optional[str] = None,
    date: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    db = Depends(get_db)
):
    query = {"hospital_id": hospital_id}
    if department_id:
        query["department_id"] = department_id

    if date:
        query["admission_date"] = date

    if status and status != "All":
        if status.upper() == "ADMITTED":
            query["status"] = {"$in": ["ADMITTED", "ICU", "OBSERVATION"]}
        elif status.upper() == "ICU":
            query["status"] = "ICU"
        elif status.upper() == "OBSERVATION":
            query["status"] = "OBSERVATION"
        elif status.upper() == "DISCHARGED":
            query["status"] = "DISCHARGED"
        else:
            query["status"] = status

    if search:
        search_rgx = {"$regex": search, "$options": "i"}
        query["$or"] = [
            {"patient_name": search_rgx},
            {"ipd_number": search_rgx},
            {"patient_id": search_rgx},
            {"patient_phone": search_rgx},
            {"bed_number": search_rgx},
            {"provisional_diagnosis": search_rgx},
            {"doctor_name": search_rgx}
        ]

    cursor = db["admissions"].find(query).sort("created_at", -1)
    admissions = await cursor.to_list(length=300)

    result = []
    for a in admissions:
        a["id"] = str(a["_id"])
        result.append(AdmissionResponse(**a))
    return result

@router.get("/hospital/{hospital_id}/overview")
async def get_admissions_department_overview(hospital_id: str, db = Depends(get_db)):
    await _seed_initial_admissions_if_empty(hospital_id, db)

    dept_cursor = db["departments"].find({"hospital_id": hospital_id})
    departments = await dept_cursor.to_list(length=100)

    if not departments:
        return []

    async def fetch_admissions_dept_stats(d):
        dept_id = str(d["_id"])

        # Active Inpatients (Admitted, ICU, Observation)
        t_active = db["admissions"].count_documents({
            "hospital_id": hospital_id,
            "department_id": dept_id,
            "status": {"$in": ["ADMITTED", "ICU", "OBSERVATION"]}
        })
        t_icu = db["admissions"].count_documents({
            "hospital_id": hospital_id,
            "department_id": dept_id,
            "status": "ICU"
        })
        t_discharged = db["admissions"].count_documents({
            "hospital_id": hospital_id,
            "department_id": dept_id,
            "status": "DISCHARGED"
        })
        t_total = db["admissions"].count_documents({
            "hospital_id": hospital_id,
            "department_id": dept_id
        })
        t_docs = db["doctors"].find({
            "hospital_id": hospital_id,
            "department_id": dept_id,
            "status": "ACTIVE"
        }).to_list(length=50)

        active_count, icu_count, discharged_count, total_count, docs = await asyncio.gather(
            t_active, t_icu, t_discharged, t_total, t_docs
        )

        # Standard bed capacity assumptions per department for display
        total_beds = 20 if "icu" in d.get("name", "").lower() else 30
        occupied_beds = min(active_count, total_beds)
        available_beds = max(0, total_beds - occupied_beds)

        return {
            "id": dept_id,
            "name": d.get("name", "General"),
            "specialty": d.get("specialty", ""),
            "active_admissions": active_count,
            "icu_count": icu_count,
            "discharged_count": discharged_count,
            "total_admissions": total_count,
            "total_beds": total_beds,
            "available_beds": available_beds,
            "active_doctors_count": len(docs)
        }

    tasks = [fetch_admissions_dept_stats(d) for d in departments]
    result = await asyncio.gather(*tasks)
    return result

@router.patch("/{admission_id}/status")
async def update_admission_status(admission_id: str, update_data: AdmissionUpdate, db = Depends(get_db)):
    data = update_data.dict(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=400, detail="No update data provided")

    data["updated_at"] = get_ist_now()
    if data.get("status") == "DISCHARGED" and not data.get("discharge_date"):
        data["discharge_date"] = get_ist_now().strftime("%Y-%m-%d %I:%M %p")

    result = await db["admissions"].update_one(
        {"_id": ObjectId(admission_id)},
        {"$set": data}
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Admission record not found")

    updated = await db["admissions"].find_one({"_id": ObjectId(admission_id)})
    updated["id"] = str(updated["_id"])
    return AdmissionResponse(**updated)

@router.get("/{admission_id}", response_model=AdmissionResponse)
async def get_admission_by_id(admission_id: str, db = Depends(get_db)):
    record = await db["admissions"].find_one({"_id": ObjectId(admission_id)})
    if not record:
        raise HTTPException(status_code=404, detail="Admission record not found")
    record["id"] = str(record["_id"])
    return AdmissionResponse(**record)
