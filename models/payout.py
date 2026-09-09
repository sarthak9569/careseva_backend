from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime

class BankDetailsUpdate(BaseModel):
    bank_account_number: Optional[str] = None
    bank_ifsc: Optional[str] = None
    bank_account_holder: Optional[str] = None
    bank_name: Optional[str] = None
    upi_id: Optional[str] = None
    payout_preferred_mode: Optional[str] = "banktransfer" # "banktransfer" or "upi"

class DisbursePayoutRequest(BaseModel):
    hospital_id: str
    amount: Optional[float] = Field(None, description="Optional custom amount. If null/0, all unsettled payments are disbursed.")
    transfer_mode: Optional[str] = "banktransfer" # "banktransfer" or "upi"
    remarks: Optional[str] = "CareSeva Consultation Settlement"

class PayoutTransaction(BaseModel):
    transfer_id: str
    hospital_id: str
    hospital_name: str
    amount: float
    currency: str = "INR"
    transfer_mode: str = "banktransfer" # banktransfer or upi
    status: str = "SUCCESS" # SUCCESS, PENDING, FAILED, REVERSED
    cf_transfer_id: Optional[str] = None
    utr: Optional[str] = None
    account_number: Optional[str] = None
    ifsc: Optional[str] = None
    upi_id: Optional[str] = None
    platform_fee: float = 0.0
    gross_amount: float = 0.0
    appointment_ids: List[str] = []
    remarks: Optional[str] = None
    raw_response: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime
