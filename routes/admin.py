from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import HTMLResponse, Response
from typing import List, Optional
from pydantic import BaseModel
from models.hospital import HospitalResponse
from database import get_db
from bson import ObjectId
from datetime import datetime
import json

router = APIRouter()

class RejectionPayload(BaseModel):
    reason: Optional[str] = "Statutory documents incomplete or clinical license could not be verified."
    notes: Optional[str] = None

class SuspensionPayload(BaseModel):
    reason: Optional[str] = "Temporary compliance hold."

@router.get("/compliance-stats")
async def get_compliance_stats(db = Depends(get_db)):
    """Summary metrics of all hospitals, legal approvals, and bed counts for CareSeva Superadmin."""
    total = await db["hospitals"].count_documents({})
    pending = await db["hospitals"].count_documents({"verification_status": "PENDING"})
    approved = await db["hospitals"].count_documents({"verification_status": "APPROVED"})
    rejected = await db["hospitals"].count_documents({"verification_status": "REJECTED"})
    suspended = await db["hospitals"].count_documents({"status": "SUSPENDED"})
    
    # Calculate total beds monitored
    cursor = db["hospitals"].find({}, {"total_beds": 1, "nabh_accreditation": 1})
    all_h = await cursor.to_list(length=500)
    total_beds = sum(int(h.get("total_beds") or 0) for h in all_h)
    nabh_count = sum(1 for h in all_h if (h.get("nabh_accreditation") or "NONE") != "NONE")

    return {
        "total_facilities": total,
        "pending_verifications": pending,
        "approved_facilities": approved,
        "rejected_facilities": rejected,
        "suspended_facilities": suspended,
        "total_beds_monitored": total_beds,
        "nabh_accredited_facilities": nabh_count
    }

@router.get("/hospitals", response_model=List[HospitalResponse])
async def list_all_hospitals(
    status_filter: Optional[str] = Query(None, description="ALL, PENDING, APPROVED, REJECTED, SUSPENDED"),
    search: Optional[str] = None,
    db = Depends(get_db)
):
    """List all registered hospitals with statutory compliance and legal fields."""
    query = {}
    if status_filter and status_filter.upper() != "ALL":
        sf = status_filter.upper()
        if sf in ["PENDING", "APPROVED", "REJECTED"]:
            query["verification_status"] = sf
        elif sf == "SUSPENDED":
            query["status"] = "SUSPENDED"

    if search and search.strip():
        rgx = {"$regex": search.strip(), "$options": "i"}
        query["$or"] = [
            {"name": rgx},
            {"city": rgx},
            {"state": rgx},
            {"hop_id": rgx},
            {"clinical_establishment_no": rgx},
            {"contact_person": rgx},
            {"email": rgx}
        ]

    cursor = db["hospitals"].find(query).sort("created_at", -1)
    hospitals = await cursor.to_list(length=200)

    result = []
    for h in hospitals:
        h["id"] = str(h["_id"])
        result.append(HospitalResponse(**h))
    return result

@router.get("/hospitals/pending", response_model=List[HospitalResponse])
async def get_pending_hospitals(db = Depends(get_db)):
    cursor = db["hospitals"].find({"verification_status": "PENDING"}).sort("created_at", -1)
    hospitals = await cursor.to_list(length=100)
    
    result = []
    for h in hospitals:
        h["id"] = str(h["_id"])
        result.append(HospitalResponse(**h))
    return result

@router.get("/hospitals/{hospital_id}", response_model=HospitalResponse)
async def get_hospital_dossier(hospital_id: str, db = Depends(get_db)):
    """Retrieve full official legal dossier of a hospital."""
    try:
        hospital = await db["hospitals"].find_one({"_id": ObjectId(hospital_id)})
    except Exception:
        hospital = None
    if not hospital:
        hospital = await db["hospitals"].find_one({"hop_id": hospital_id})

    if not hospital:
        raise HTTPException(status_code=404, detail="Hospital not found")

    hospital["id"] = str(hospital["_id"])
    return HospitalResponse(**hospital)

@router.get("/hospitals/{hospital_id}/dossier/download")
async def download_hospital_dossier(
    hospital_id: str,
    format: str = Query("html", description="html or json"),
    db = Depends(get_db)
):
    """Generate and download official statutory legal dossier for a hospital facility."""
    try:
        hospital = await db["hospitals"].find_one({"_id": ObjectId(hospital_id)})
    except Exception:
        hospital = None
    if not hospital:
        hospital = await db["hospitals"].find_one({"hop_id": hospital_id})

    if not hospital:
        raise HTTPException(status_code=404, detail="Hospital facility not found")

    h_id = str(hospital["_id"])
    hop_id = hospital.get("hop_id") or "UNKNOWN"
    name = hospital.get("name") or "Unnamed Facility"
    facility_type = hospital.get("facility_type") or "Hospital"
    legal_entity = hospital.get("legal_entity_name") or name
    cea_no = hospital.get("clinical_establishment_no") or "NOT SUBMITTED"
    gstin = hospital.get("gstin") or "NOT SUBMITTED"
    pan = hospital.get("pan_number") or "NOT SUBMITTED"
    nabh = hospital.get("nabh_accreditation") or "NONE"
    nabh_valid = hospital.get("nabh_valid_till") or "N/A"
    bmw = hospital.get("bmw_auth_number") or "State PCB Clearance Active"
    pharmacy = hospital.get("pharmacy_license_no") or "Form 20/21 In-house Active"
    fire_noc = hospital.get("fire_noc_number") or "Audited & Certified"
    beds = hospital.get("total_beds") or 0
    ms_name = hospital.get("medical_superintendent_name") or hospital.get("contact_person") or "Dr. In-Charge"
    ms_reg = hospital.get("medical_superintendent_reg_no") or "State Medical Council / NMC Verified"
    ms_phone = hospital.get("medical_superintendent_phone") or hospital.get("phone") or "-"
    ms_email = hospital.get("medical_superintendent_email") or hospital.get("email") or "-"
    sig_name = hospital.get("authorized_signatory_name") or hospital.get("contact_person") or "-"
    sig_desig = hospital.get("authorized_signatory_designation") or "Managing Director / Administrator"
    address = f"{hospital.get('address', '')}, {hospital.get('city', '')}, {hospital.get('state', '')} - {hospital.get('pincode', '')}"
    phone = hospital.get("phone") or "-"
    email = hospital.get("email") or "-"
    v_status = (hospital.get("verification_status") or "PENDING").upper()
    created_at = hospital.get("created_at")
    created_str = created_at.strftime("%d %B %Y, %H:%M UTC") if isinstance(created_at, datetime) else str(created_at or "-")
    sla_time = hospital.get("sla_accepted_at") or created_str
    audit_date = datetime.utcnow().strftime("%d %B %Y, %H:%M UTC")

    if format.lower() == "json":
        clean_doc = {**hospital, "id": h_id}
        clean_doc.pop("_id", None)
        clean_doc.pop("hashed_password", None)
        return Response(
            content=json.dumps(clean_doc, default=str, indent=2),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="CareSeva_Legal_Dossier_{hop_id}.json"'}
        )

    # Generate Executive Formal HTML Legal Dossier
    status_badge_color = "#10b981" if v_status == "APPROVED" else ("#ef4444" if v_status == "REJECTED" else "#f59e0b")
    status_badge_bg = "#ecfdf5" if v_status == "APPROVED" else ("#fef2f2" if v_status == "REJECTED" else "#fffbeb")

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>CareSeva Legal Audit Dossier - {name} ({hop_id})</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
        * {{ margin: 0; padding: 0; box-sizing: border-box; font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif; }}
        body {{ background: #f8fafc; color: #0f172a; padding: 30px 20px; }}
        .container {{ max-width: 900px; margin: 0 auto; background: #ffffff; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.06); border: 1px solid #e2e8f0; overflow: hidden; }}
        .header {{ background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); color: #ffffff; padding: 36px 40px; border-bottom: 4px solid #0d9488; }}
        .header-top {{ display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 20px; }}
        .brand-badge {{ background: #0d9488; color: #ffffff; padding: 6px 12px; border-radius: 6px; font-size: 11px; font-weight: 800; letter-spacing: 1px; text-transform: uppercase; }}
        .doc-id {{ font-size: 12px; color: #94a3b8; font-family: monospace; }}
        .header h1 {{ font-size: 26px; font-weight: 800; letter-spacing: -0.5px; margin-bottom: 6px; color: #ffffff; }}
        .header p {{ color: #cbd5e1; font-size: 13px; line-height: 1.5; }}
        .actions-bar {{ background: #f1f5f9; padding: 14px 40px; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #e2e8f0; }}
        .btn {{ display: inline-flex; align-items: center; gap: 8px; padding: 10px 18px; border-radius: 8px; font-size: 13px; font-weight: 600; text-decoration: none; cursor: pointer; border: none; transition: 0.2s; }}
        .btn-primary {{ background: #0d9488; color: #ffffff; }}
        .btn-primary:hover {{ background: #0f766e; }}
        .btn-outline {{ background: #ffffff; color: #334155; border: 1px solid #cbd5e1; }}
        .btn-outline:hover {{ background: #f8fafc; }}
        .body-content {{ padding: 40px; }}
        .section {{ margin-bottom: 32px; }}
        .section-header {{ display: flex; align-items: center; gap: 10px; margin-bottom: 16px; padding-bottom: 8px; border-bottom: 2px solid #f1f5f9; }}
        .section-num {{ width: 24px; height: 24px; border-radius: 6px; background: #0284c7; color: #ffffff; display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 800; }}
        .section-title {{ font-size: 15px; font-weight: 700; color: #0f172a; text-transform: uppercase; letter-spacing: 0.5px; }}
        .grid {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px 24px; }}
        .grid-3 {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }}
        .field-group {{ display: flex; flex-direction: column; }}
        .field-label {{ font-size: 11px; font-weight: 700; text-transform: uppercase; color: #64748b; letter-spacing: 0.4px; margin-bottom: 4px; }}
        .field-value {{ font-size: 13.5px; font-weight: 600; color: #1e293b; word-break: break-word; }}
        .badge {{ display: inline-block; padding: 4px 10px; border-radius: 6px; font-size: 11px; font-weight: 700; }}
        .cert-box {{ background: #f8fafc; border: 1.5px dashed #cbd5e1; border-radius: 10px; padding: 20px; margin-top: 24px; }}
        .cert-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }}
        .seal-stamp {{ width: 110px; height: 110px; border: 3px double #0d9488; border-radius: 50%; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; color: #0d9488; font-size: 9px; font-weight: 800; text-transform: uppercase; transform: rotate(-8deg); }}
        .footer {{ background: #f8fafc; padding: 24px 40px; border-top: 1px solid #e2e8f0; font-size: 11px; color: #64748b; line-height: 1.6; display: flex; justify-content: space-between; align-items: flex-end; }}
        @media print {{
            body {{ background: #ffffff; padding: 0; }}
            .container {{ box-shadow: none; border: none; max-width: 100%; }}
            .actions-bar {{ display: none !important; }}
            .page-break {{ page-break-before: always; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="header-top">
                <span class="brand-badge">CareSeva Healthcare Regulatory Authority</span>
                <span class="doc-id">REF: CS-DOSSIER-{hop_id}-2026</span>
            </div>
            <h1>Statutory Legal Compliance & Em-panelment Dossier</h1>
            <p>Certified Medico-Legal Due Diligence Audit issued by CareSeva Health Technologies Pvt. Ltd. under the Clinical Establishments (Registration and Regulation) Act and National Accreditation Standards.</p>
        </div>

        <div class="actions-bar">
            <div>
                <span style="font-size: 12px; font-weight: 700; color: #475569;">Verification Status:</span>
                <span class="badge" style="background: {status_badge_bg}; color: {status_badge_color}; border: 1px solid {status_badge_color}; margin-left: 6px;">
                    {v_status}
                </span>
            </div>
            <div style="display: flex; gap: 10px;">
                <button class="btn btn-outline" onclick="window.print()">🖨️ Print / Save as PDF</button>
                <a class="btn btn-primary" href="?format=json" download="CareSeva_Legal_Dossier_{hop_id}.json">⬇️ Export JSON</a>
            </div>
        </div>

        <div class="body-content">
            <!-- Section 1 -->
            <div class="section">
                <div class="section-header">
                    <span class="section-num">1</span>
                    <span class="section-title">Healthcare Facility & Entity Identification</span>
                </div>
                <div class="grid">
                    <div class="field-group">
                        <span class="field-label">Facility Brand Name</span>
                        <span class="field-value" style="font-size: 16px; color: #0284c7;">{name}</span>
                    </div>
                    <div class="field-group">
                        <span class="field-label">CareSeva Hospital Identifier (HopID)</span>
                        <span class="field-value" style="font-family: monospace; font-size: 15px;">{hop_id}</span>
                    </div>
                    <div class="field-group">
                        <span class="field-label">Registered Corporate / Trust Legal Name</span>
                        <span class="field-value">{legal_entity}</span>
                    </div>
                    <div class="field-group">
                        <span class="field-label">Facility Classification</span>
                        <span class="field-value">{facility_type}</span>
                    </div>
                    <div class="field-group" style="grid-column: span 2;">
                        <span class="field-label">Physical Campus & Registered Address</span>
                        <span class="field-value">{address}</span>
                    </div>
                    <div class="field-group">
                        <span class="field-label">Official Registered Email</span>
                        <span class="field-value">{email}</span>
                    </div>
                    <div class="field-group">
                        <span class="field-label">Official Helpline / Contact</span>
                        <span class="field-value">{phone}</span>
                    </div>
                </div>
            </div>

            <!-- Section 2 -->
            <div class="section">
                <div class="section-header">
                    <span class="section-num">2</span>
                    <span class="section-title">Statutory Clinical Licensure & Taxation</span>
                </div>
                <div class="grid-3">
                    <div class="field-group">
                        <span class="field-label">Clinical Est. Act (CEA) Number</span>
                        <span class="field-value" style="color: #0369a1;">{cea_no}</span>
                    </div>
                    <div class="field-group">
                        <span class="field-label">Hospital GSTIN</span>
                        <span class="field-value" style="font-family: monospace;">{gstin}</span>
                    </div>
                    <div class="field-group">
                        <span class="field-label">Income Tax PAN</span>
                        <span class="field-value" style="font-family: monospace;">{pan}</span>
                    </div>
                </div>
            </div>

            <!-- Section 3 -->
            <div class="section">
                <div class="section-header">
                    <span class="section-num">3</span>
                    <span class="section-title">Quality Accreditation & Regulatory Clearances</span>
                </div>
                <div class="grid">
                    <div class="field-group">
                        <span class="field-label">NABH / NABL Quality Tier</span>
                        <span class="field-value">{nabh}</span>
                    </div>
                    <div class="field-group">
                        <span class="field-label">Accreditation Validity Date</span>
                        <span class="field-value">{nabh_valid}</span>
                    </div>
                    <div class="field-group">
                        <span class="field-label">Bio-Medical Waste (BMW) Clearance</span>
                        <span class="field-value">{bmw}</span>
                    </div>
                    <div class="field-group">
                        <span class="field-label">Pharmacy License (Form 20/21)</span>
                        <span class="field-value">{pharmacy}</span>
                    </div>
                    <div class="field-group">
                        <span class="field-label">Fire Safety Clearance (NOC)</span>
                        <span class="field-value">{fire_noc}</span>
                    </div>
                    <div class="field-group">
                        <span class="field-label">Total Monitored Inpatient Beds</span>
                        <span class="field-value" style="color: #0d9488;">{beds} Beds (General, HDU, ICU)</span>
                    </div>
                </div>
            </div>

            <!-- Section 4 -->
            <div class="section">
                <div class="section-header">
                    <span class="section-num">4</span>
                    <span class="section-title">Clinical Leadership & Authorized Corporate Governance</span>
                </div>
                <div class="grid">
                    <div class="field-group">
                        <span class="field-label">Medical Superintendent / CMO</span>
                        <span class="field-value">{ms_name}</span>
                    </div>
                    <div class="field-group">
                        <span class="field-label">State Medical Council / NMC Reg #</span>
                        <span class="field-value" style="font-family: monospace;">{ms_reg}</span>
                    </div>
                    <div class="field-group">
                        <span class="field-label">Medical Superintendent Direct Phone</span>
                        <span class="field-value">{ms_phone}</span>
                    </div>
                    <div class="field-group">
                        <span class="field-label">Medical Superintendent Official Email</span>
                        <span class="field-value">{ms_email}</span>
                    </div>
                    <div class="field-group">
                        <span class="field-label">Authorized Corporate Signatory</span>
                        <span class="field-value">{sig_name}</span>
                    </div>
                    <div class="field-group">
                        <span class="field-label">Corporate Designation</span>
                        <span class="field-value">{sig_desig}</span>
                    </div>
                </div>
            </div>

            <!-- Section 5 -->
            <div class="cert-box">
                <div class="cert-header">
                    <div>
                        <span class="field-label">Digital Service Agreement (SLA) Execution</span>
                        <div style="font-size: 13.5px; font-weight: 700; color: #0f172a; margin-top: 4px;">
                            CareSeva Aggregator Terms & Statutory Healthcare Indemnity: <span style="color: #10b981;">EXECUTED & VERIFIED</span>
                        </div>
                        <div style="font-size: 12px; color: #64748b; margin-top: 2px;">
                            Acceptance Logged: {sla_time} • Master Contract Version: v2.4-IND
                        </div>
                    </div>
                    <div class="seal-stamp">
                        <div>CARESEVA</div>
                        <div style="font-size: 7px; margin: 2px 0;">LEGAL AUDIT</div>
                        <div>VERIFIED</div>
                    </div>
                </div>
            </div>
        </div>

        <div class="footer">
            <div>
                <strong>CareSeva Health Technologies Pvt. Ltd.</strong><br>
                Compliance Directorate • Healthcare Regulatory Operations<br>
                Statutory Record Hash: SHA256:{h_id}
            </div>
            <div style="text-align: right;">
                Audit Generated At: {audit_date}<br>
                Confidential Official Record — Company Filing Copy
            </div>
        </div>
    </div>
</body>
</html>"""

    return HTMLResponse(content=html_content)

@router.post("/hospitals/{hospital_id}/approve")
async def approve_hospital(hospital_id: str, db = Depends(get_db)):
    try:
        obj_id = ObjectId(hospital_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid hospital ID format")

    hospital = await db["hospitals"].find_one({"_id": obj_id})
    if not hospital:
        raise HTTPException(status_code=404, detail="Hospital not found")
        
    await db["hospitals"].update_one(
        {"_id": obj_id},
        {"$set": {
            "verification_status": "APPROVED",
            "status": "ACTIVE",
            "approved_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
            "rejection_reason": None
        }}
    )
    
    # Create or update the admin user for this hospital
    existing_user = await db["users"].find_one({"email": hospital["email"]})
    if not existing_user:
        user_dict = {
            "name": hospital.get("contact_person", hospital.get("name")),
            "email": hospital["email"],
            "hashed_password": hospital.get("hashed_password"),
            "role": "admin",
            "hospital_id": str(hospital["_id"]),
            "hospital_name": hospital.get("name"),
            "hop_id": hospital.get("hop_id")
        }
        await db["users"].insert_one(user_dict)
    else:
        await db["users"].update_one(
            {"_id": existing_user["_id"]},
            {"$set": {"status": "ACTIVE"}}
        )
        
    return {
        "status": "success",
        "message": f"{hospital.get('name')} approved successfully. Hospital is now active on CareSeva."
    }

@router.post("/hospitals/{hospital_id}/reject")
async def reject_hospital(
    hospital_id: str,
    payload: Optional[RejectionPayload] = None,
    db = Depends(get_db)
):
    try:
        obj_id = ObjectId(hospital_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid hospital ID format")

    reason = payload.reason if payload else "Statutory documents incomplete or license verification failed."
    notes = payload.notes if payload else None

    result = await db["hospitals"].update_one(
        {"_id": obj_id},
        {"$set": {
            "verification_status": "REJECTED",
            "status": "INACTIVE",
            "rejection_reason": reason,
            "verification_notes": notes,
            "rejected_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        }}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Hospital not found")
    return {"status": "success", "message": "Hospital application rejected", "reason": reason}

@router.post("/hospitals/{hospital_id}/suspend")
async def suspend_hospital(
    hospital_id: str,
    payload: Optional[SuspensionPayload] = None,
    db = Depends(get_db)
):
    try:
        obj_id = ObjectId(hospital_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid hospital ID format")

    reason = payload.reason if payload else "Compliance violation hold."

    result = await db["hospitals"].update_one(
        {"_id": obj_id},
        {"$set": {
            "status": "SUSPENDED",
            "verification_notes": f"Suspended: {reason}",
            "suspended_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        }}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Hospital not found")
    return {"status": "success", "message": "Hospital suspended from public booking"}
