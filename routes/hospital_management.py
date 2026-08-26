from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from models.hospital import DepartmentCreate, DepartmentUpdate, DepartmentResponse, DepartmentInDB, DoctorCreate, DoctorUpdate, DoctorResponse, DoctorInDB
from database import get_db
from bson import ObjectId
from datetime import datetime

router = APIRouter()

@router.post("/{hospital_id}/departments", response_model=DepartmentResponse)
async def create_department(hospital_id: str, department: DepartmentCreate, db = Depends(get_db)):
    db_dept = DepartmentInDB(
        **department.dict(),
        id="",
        hospital_id=hospital_id,
        created_at=datetime.utcnow()
    )
    
    db_dict = db_dept.dict(exclude={"id"})
    result = await db["departments"].insert_one(db_dict)
    
    db_dict["id"] = str(result.inserted_id)
    return DepartmentResponse(**db_dict)

@router.get("/{hospital_id}/departments", response_model=List[DepartmentResponse])
async def get_departments(hospital_id: str, db = Depends(get_db)):
    cursor = db["departments"].find({"hospital_id": hospital_id})
    departments = await cursor.to_list(length=100)
    
    result = []
    for d in departments:
        d["id"] = str(d["_id"])
        result.append(DepartmentResponse(**d))
    return result

@router.put("/{hospital_id}/departments/{dept_id}", response_model=DepartmentResponse)
async def update_department(hospital_id: str, dept_id: str, dept_update: DepartmentUpdate, db = Depends(get_db)):
    dept = await db["departments"].find_one({"_id": ObjectId(dept_id), "hospital_id": hospital_id})
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")
        
    update_data = dept_update.dict(exclude_unset=True)
    if not update_data:
        dept["id"] = str(dept["_id"])
        return DepartmentResponse(**dept)
        
    await db["departments"].update_one(
        {"_id": ObjectId(dept_id)},
        {"$set": update_data}
    )
    
    updated_dept = await db["departments"].find_one({"_id": ObjectId(dept_id)})
    updated_dept["id"] = str(updated_dept["_id"])
    return DepartmentResponse(**updated_dept)

@router.post("/{hospital_id}/doctors", response_model=DoctorResponse)
async def create_doctor(hospital_id: str, doctor: DoctorCreate, db = Depends(get_db)):
    db_doc = DoctorInDB(
        **doctor.dict(),
        id="",
        hospital_id=hospital_id,
        created_at=datetime.utcnow()
    )
    
    db_dict = db_doc.dict(exclude={"id"})
    result = await db["doctors"].insert_one(db_dict)
    
    db_dict["id"] = str(result.inserted_id)
    db_dict["activePatientsInQueue"] = 0
    db_dict["rating"] = 4.5
    return DoctorResponse(**db_dict)

@router.get("/{hospital_id}/doctors", response_model=List[DoctorResponse])
async def get_doctors(hospital_id: str, db = Depends(get_db)):
    cursor = db["doctors"].find({"hospital_id": hospital_id})
    doctors = await cursor.to_list(length=100)
    
    result = []
    for d in doctors:
        d["id"] = str(d["_id"])
        d["activePatientsInQueue"] = 0 # would be calculated dynamically in real world
        d["rating"] = 4.5
        result.append(DoctorResponse(**d))
    return result

@router.put("/{hospital_id}/doctors/{doc_id}", response_model=DoctorResponse)
async def update_doctor(hospital_id: str, doc_id: str, doc_update: DoctorUpdate, db = Depends(get_db)):
    doctor = await db["doctors"].find_one({"_id": ObjectId(doc_id), "hospital_id": hospital_id})
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")
        
    update_data = doc_update.dict(exclude_unset=True)
    if not update_data:
        doctor["id"] = str(doctor["_id"])
        doctor["activePatientsInQueue"] = 0
        doctor["rating"] = 4.5
        return DoctorResponse(**doctor)
        
    await db["doctors"].update_one(
        {"_id": ObjectId(doc_id)},
        {"$set": update_data}
    )
    
    updated_doc = await db["doctors"].find_one({"_id": ObjectId(doc_id)})
    updated_doc["id"] = str(updated_doc["_id"])
    updated_doc["activePatientsInQueue"] = 0
    updated_doc["rating"] = 4.5
    return DoctorResponse(**updated_doc)

@router.delete("/{hospital_id}/doctors/{doc_id}")
async def delete_doctor(hospital_id: str, doc_id: str, db = Depends(get_db)):
    doctor = await db["doctors"].find_one({"_id": ObjectId(doc_id), "hospital_id": hospital_id})
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")
        
    await db["doctors"].update_one(
        {"_id": ObjectId(doc_id)},
        {"$set": {"status": "INACTIVE"}}
    )
    
    return {"message": "Doctor deleted successfully"}

@router.get("/{hospital_id}/dashboard-stats")
async def get_dashboard_stats(hospital_id: str, db = Depends(get_db)):
    # 1. Total Patients (unique patient IDs in appointments for this hospital)
    # Using aggregation pipeline
    pipeline = [
        {"$match": {"hospital_id": hospital_id}},
        {"$group": {"_id": "$patient_id"}}
    ]
    unique_patients_cursor = db["appointments"].aggregate(pipeline)
    unique_patients = await unique_patients_cursor.to_list(length=10000)
    total_patients = len(unique_patients)
    
    # 2. Appointments Today
    today_start_str = datetime.utcnow().strftime("%Y-%m-%d")
    appointments_today_count = await db["appointments"].count_documents({
        "hospital_id": hospital_id,
        "appointment_date": today_start_str
    })
    
    # 3. Available Doctors
    available_doctors_count = await db["doctors"].count_documents({
        "hospital_id": hospital_id,
        "status": "ACTIVE"
    })
    
    # 4. Today's Revenue (mocked based on appointments today * 50)
    todays_revenue = appointments_today_count * 50
    
    # 5. Recent Appointments
    recent_cursor = db["appointments"].find({"hospital_id": hospital_id}).sort("created_at", -1).limit(5)
    recent_appts = await recent_cursor.to_list(length=5)
    
    recent_list = []
    for a in recent_appts:
        # Fetch doctor details
        doctor = await db["doctors"].find_one({"_id": ObjectId(a["doctor_id"])}) if "doctor_id" in a and a["doctor_id"] else None
        doctor_name = doctor["name"] if doctor else "Unknown Doctor"
        
        # Fetch department details
        dept = await db["departments"].find_one({"_id": ObjectId(a["department_id"])}) if "department_id" in a and a["department_id"] else None
        dept_name = dept["name"] if dept else "Unknown Dept"
        
        patient_name = a.get("patient_name") or "Unknown Patient"
        
        recent_list.append({
            "id": str(a["_id"]),
            "patient_name": patient_name,
            "doctor_name": doctor_name,
            "department_name": dept_name,
            "status": a.get("status", "SCHEDULED"),
            "time": a.get("created_at").strftime("%H:%M") if a.get("created_at") else "10:00 AM"
        })
        
    return {
        "total_patients": total_patients,
        "appointments_today": appointments_today_count,
        "available_doctors": available_doctors_count,
        "todays_revenue": todays_revenue,
        "recent_appointments": recent_list
    }
