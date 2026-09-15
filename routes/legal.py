from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from datetime import datetime
from database import get_db
from core.security import get_optional_current_user, get_current_user

router = APIRouter()

# ---------------------------------------------------------
# LEGAL DOCUMENTS DICTIONARY (v1.0)
# ---------------------------------------------------------

PATIENT_TERMS_V1 = """# CareSeva™ Mobile Application – Terms & Conditions

**Document Version:** 1.0  
**Effective Date:** September 15, 2026  
**Operating Legal Entity:** Softkrest Infotech (Proprietor: Mr. Sarthak Srivastava)  
**MSME Udyam Registration No.:** UDYAM-UP-75-0200308 (Ministry of MSME, Govt. of India)  
**Registered Trademark:** CARESEVA™ (Trade Mark Application No: 14991641, Class 42)  
**Registered Office Address:** Srivastava Niwas, Churamanpur, Bhullanpur, Kashi Vidyapeeth, Varanasi, Uttar Pradesh – 221108, India  
**Official Email:** softkrestinfotech@gmail.com  
**Official Helpline:** +91 9369309644  

---

## 1. ACCEPTANCE OF TERMS
CareSeva™ is owned and operated exclusively by **Softkrest Infotech**. By using the CareSeva™ Mobile Application, you agree to these Terms and Conditions.

## 2. PLATFORM ROLE & NON-MEDICAL PROVIDER DISCLAIMER
CareSeva™ is a software technology platform connecting patients with hospitals/doctors for appointment scheduling, OPD tokens, queue status, and health records. Softkrest Infotech is **NOT** a healthcare provider or hospital. Medical treatment, diagnosis, and prescriptions are solely the responsibility of treating doctors/hospitals.

## 3. EMERGENCY MEDICAL CARE DISCLAIMER
**DO NOT USE CARESEVA™ FOR EMERGENCY MEDICAL CARE.** In emergencies, immediately call **112** or **108** or proceed directly to the nearest hospital casualty/emergency room.

## 4. ACCOUNT & OTP SECURITY
Users register via mobile OTP authentication and are solely responsible for maintaining mobile device security and OTP confidentiality.

## 5. BOOKING FOR DEPENDENTS & FAMILY
Users booking appointments for family members warrant that they have obtained consent from the patient to share their details.

## 6. OPD TOKENS & QUEUE TRACKING
Queue positions and estimated wait times are dynamic and calculated from real-time hospital inputs. Hospital emergency cases or doctor delays may alter token order.

## 7. PAYMENTS & REFUNDS
Online payments are processed securely via licensed payment gateways (e.g. Razorpay/UPI). Refunds are subject to hospital cancellation policies.

## 8. PROHIBITED CONDUCT
Fraudulent token creation, queue manipulation, scraping, API reverse engineering, or accessing other users' data is strictly prohibited.

## 9. INTELLECTUAL PROPERTY
CareSeva™ logo, software code, and platform architecture are the exclusive property of **Softkrest Infotech** (Class 42, App No: 14991641).

## 10. GOVERNING LAW & GRIEVANCES
Governed by Indian law under Varanasi, UP jurisdiction. Grievances may be directed to `softkrestinfotech@gmail.com`.
"""

PATIENT_PRIVACY_V1 = """# CareSeva™ Mobile Application – Privacy Policy

**Document Version:** 1.0  
**Effective Date:** September 15, 2026  
**Data Fiduciary:** Softkrest Infotech (Proprietor: Mr. Sarthak Srivastava)  
**Udyam Registration:** UDYAM-UP-75-0200308 | **Trademark:** CARESEVA™ Class 42  
**Contact Email:** softkrestinfotech@gmail.com | **Helpline:** +91 9369309644  

---

## 1. DATA FIDUCIARY IDENTITY
Under the Digital Personal Data Protection (DPDP) Act 2023, **Softkrest Infotech** acts as the Data Fiduciary for CareSeva™ mobile app users.

## 2. DATA COLLECTED
- **Personal:** Name, mobile number, age, gender, address.
- **Health:** Selected hospital, OPD token history, appointments, prescriptions.
- **Technical:** IP address, device model, push notification tokens.

## 3. PURPOSE OF PROCESSING
Authentication, token generation, queue status alerts, customer support, and payment verification.

## 4. STRICT PATIENT DATA ISOLATION
CareSeva™ uses server-side JWT authentication and database scoping. Patient A cannot access Patient B's data under any circumstances. We **never** sell user data to advertisers.

## 5. CONTROLLED THIRD-PARTY SHARING
Data is shared exclusively with treating hospitals/doctors, Razorpay payment gateway, Fast2SMS/Twilio SMS gateways, and secure cloud hosts (Railway/MongoDB).

## 6. DATA PRINCIPAL RIGHTS (DPDP ACT 2023)
Users have rights to Access, Correct, Request Account Erasure/Deletion, and Withdraw Consent. Contact `softkrestinfotech@gmail.com` to request data erasure.

## 7. GRIEVANCE OFFICER
**Data Protection Officer:** Mr. Sarthak Srivastava, Softkrest Infotech, Srivastava Niwas, Churamanpur, Bhullanpur, Kashi Vidyapeeth, Varanasi, UP – 221108.
"""

HMS_TERMS_V1 = """# CareSeva™ Hospital Management System (HMS) – Terms of Service

**Document Version:** 1.0  
**Effective Date:** September 15, 2026  
**SaaS Service Provider:** Softkrest Infotech (Proprietor: Mr. Sarthak Srivastava)  
**Udyam Reg:** UDYAM-UP-75-0200308 | **Trademark:** CARESEVA™ Class 42  
**Email:** softkrestinfotech@gmail.com | **Phone:** +91 9369309644  

---

## 1. B2B SaaS PLATFORM AGREEMENT
Governs usage of CareSeva™ HMS by registered Hospitals, Administrators, Doctors, Receptionists, and Staff.

## 2. HOSPITAL CLINICAL & OPERATIONAL RESPONSIBILITY
Hospitals and doctors assume sole clinical responsibility for medical diagnoses, prescriptions, treatment outcomes, doctor NMC licensing, and staff authorization.

## 3. ACCOUNT SECURITY & RBAC
Individual credentials must be issued for all staff (Admin, Doctor, Receptionist). Sharing passwords is strictly prohibited. Promptly revoke credentials when staff resigns.

## 4. PATIENT CONFIDENTIALITY & DATA INTEGRITY
Hospital staff must maintain patient confidentiality and process records solely for clinical treatment. Staff shall not scrape, export, or access records of unrelated organizations.

## 5. B2B INDEMNIFICATION
Hospital agrees to defend and indemnify Softkrest Infotech, Mr. Sarthak Srivastava, and employees against any medical malpractice suits, patient claims, or hospital-level data breach liabilities.

## 6. JURISDICTION
Governed by Indian Law under exclusive Varanasi, Uttar Pradesh jurisdiction.
"""

HMS_PRIVACY_V1 = """# CareSeva™ HMS – Privacy & Data Processing Notice

**Document Version:** 1.0  
**Effective Date:** September 15, 2026  
**Data Processor:** Softkrest Infotech (Proprietor: Mr. Sarthak Srivastava)  
**Udyam Reg:** UDYAM-UP-75-0200308 | **Contact:** softkrestinfotech@gmail.com  

---

## 1. LEGAL PROCESSING ROLES
Hospital acts as Data Controller/Fiduciary for patient clinical data; Softkrest Infotech acts as SaaS Data Processor operating secure infrastructure.

## 2. HMS DATA CATEGORIES
Hospital profile, Doctor/Staff credentials, Patient treatment records, OPD tokens, and Immutable Audit Logs.

## 3. MULTI-TENANT DATABASE ISOLATION
Strict row-level organization access controls. Hospital A staff cannot view or query Hospital B patient records or queues.

## 4. STAFF AUDIT LOGGING
HMS records immutable audit logs of login events, patient file views, prescription creations, and user credential modifications.

## 5. DATA RETENTION & EXPORT
Hospital data is retained during active subscription. Upon termination, CSV/JSON export is available for 30 days prior to permanent database purging.
"""

DOCUMENTS_MAP = {
    "patient_terms": {"title": "CareSeva Patient Terms & Conditions", "version": "v1.0", "content": PATIENT_TERMS_V1},
    "patient_privacy": {"title": "CareSeva Patient Privacy Policy", "version": "v1.0", "content": PATIENT_PRIVACY_V1},
    "hms_terms": {"title": "CareSeva HMS Terms of Service", "version": "v1.0", "content": HMS_TERMS_V1},
    "hms_privacy": {"title": "CareSeva HMS Privacy & Data Processing Notice", "version": "v1.0", "content": HMS_PRIVACY_V1},
}

# ---------------------------------------------------------
# SCHEMAS
# ---------------------------------------------------------

class ConsentRequest(BaseModel):
    document_type: str = Field(..., description="patient_terms, patient_privacy, hms_terms, or hms_privacy")
    version: str = Field("v1.0", description="Document version accepted")
    user_type: str = Field("patient", description="patient or hms_user")
    organization_id: Optional[str] = None

class ConsentResponse(BaseModel):
    status: str
    message: str
    accepted_at: str
    document_type: str
    version: str

# ---------------------------------------------------------
# ENDPOINTS
# ---------------------------------------------------------

@router.get("/documents/{doc_type}")
async def get_legal_document(doc_type: str):
    """Fetch the latest legal document text by doc_type."""
    if doc_type not in DOCUMENTS_MAP:
        raise HTTPException(
            status_code=404,
            detail=f"Legal document type '{doc_type}' not found. Valid types: {list(DOCUMENTS_MAP.keys())}"
        )
    return DOCUMENTS_MAP[doc_type]

@router.get("/documents")
async def list_legal_documents():
    """List all available legal documents and their current active versions."""
    return {
        "entity": "Softkrest Infotech",
        "udyam": "UDYAM-UP-75-0200308",
        "trademark": "CARESEVA™ Class 42 (App No: 14991641)",
        "documents": [
            {"type": k, "title": v["title"], "version": v["version"]}
            for k, v in DOCUMENTS_MAP.items()
        ]
    }

@router.post("/consent", response_model=ConsentResponse)
async def record_user_consent(
    request_data: ConsentRequest,
    req: Request,
    db = Depends(get_db),
    current_user: Optional[dict] = Depends(get_optional_current_user)
):
    """Record timestamped user consent for a specific legal document version (v1.0)."""
    if request_data.document_type not in DOCUMENTS_MAP:
        raise HTTPException(status_code=400, detail="Invalid document_type")
    
    user_id = current_user.get("_id") if current_user else "anonymous_device"
    client_ip = req.client.host if req.client else "unknown"
    now_str = datetime.utcnow().isoformat()

    consent_record = {
        "user_id": str(user_id),
        "user_type": request_data.user_type,
        "document_type": request_data.document_type,
        "version": request_data.version,
        "organization_id": request_data.organization_id,
        "client_ip": client_ip,
        "accepted_at": now_str,
    }

    # Upsert into legal_consents collection
    await db.legal_consents.update_one(
        {
            "user_id": str(user_id),
            "document_type": request_data.document_type,
            "version": request_data.version
        },
        {"$set": consent_record},
        upsert=True
    )

    return ConsentResponse(
        status="success",
        message="Consent recorded successfully",
        accepted_at=now_str,
        document_type=request_data.document_type,
        version=request_data.version
    )

@router.get("/consent-status")
async def get_consent_status(
    doc_type: str = "patient_terms",
    db = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Check if the authenticated user has accepted a specific document version."""
    user_id = str(current_user["_id"])
    record = await db.legal_consents.find_one({
        "user_id": user_id,
        "document_type": doc_type,
        "version": "v1.0"
    })

    if record:
        return {
            "has_accepted": True,
            "accepted_at": record.get("accepted_at"),
            "version": record.get("version")
        }
    return {
        "has_accepted": False,
        "accepted_at": None,
        "version": "v1.0"
    }
