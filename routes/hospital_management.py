from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from models.hospital import DepartmentCreate, DepartmentResponse, DepartmentInDB, DoctorCreate, DoctorResponse, DoctorInDB
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
    cursor = db["departments"].find({"hospital_id": hospital_id, "status": "ACTIVE"})
    departments = await cursor.to_list(length=100)
    
    result = []
    for d in departments:
        d["id"] = str(d["_id"])
        result.append(DepartmentResponse(**d))
    return result

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
    cursor = db["doctors"].find({"hospital_id": hospital_id, "status": "ACTIVE"})
    doctors = await cursor.to_list(length=100)
    
    result = []
    for d in doctors:
        d["id"] = str(d["_id"])
        d["activePatientsInQueue"] = 0 # would be calculated dynamically in real world
        d["rating"] = 4.5
        result.append(DoctorResponse(**d))
    return result
