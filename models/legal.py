from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class LegalConsentCreate(BaseModel):
    user_id: str
    user_type: str  # 'patient' or 'hms_user'
    organization_id: Optional[str] = None
    document_type: str  # 'patient_terms', 'patient_privacy', 'hms_terms', 'hms_privacy'
    version: str = "v1.0"
    ip_address: Optional[str] = "127.0.0.1"

class LegalConsentInDB(BaseModel):
    id: Optional[str] = None
    user_id: str
    user_type: str
    organization_id: Optional[str] = None
    document_type: str
    version: str
    accepted_at: str
    ip_address: Optional[str] = None

class LegalConsentResponse(BaseModel):
    status: str
    message: str
    consent_id: str
    user_id: str
    document_type: str
    version: str
    accepted_at: str
