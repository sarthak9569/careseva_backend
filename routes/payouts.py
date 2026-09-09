from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone, timedelta
from bson import ObjectId
import uuid
import time

from database import get_db
from core.config import settings
from core.cashfree_payouts import payouts_client
from models.payout import BankDetailsUpdate, DisbursePayoutRequest

router = APIRouter()

IST = timezone(timedelta(hours=5, minutes=30))

def get_ist_now() -> datetime:
    return datetime.now(IST)

@router.post("/hospital/{hospital_id}/bank-details")
async def update_hospital_bank_details(
    hospital_id: str,
    bank_data: BankDetailsUpdate,
    db = Depends(get_db)
):
    """
    Save or update bank account and UPI details for a hospital/facility and sync with Cashfree Payouts.
    """
    # Find hospital
    hospital = None
    try:
        hospital = await db["hospitals"].find_one({"_id": ObjectId(hospital_id)})
    except Exception:
        pass
    if not hospital:
        hospital = await db["hospitals"].find_one({"hop_id": hospital_id})

    if not hospital:
        raise HTTPException(status_code=404, detail="Hospital not found")

    h_obj_id = hospital["_id"]
    h_id_str = str(h_obj_id)
    hop_id = hospital.get("hop_id") or f"HOSP_{h_id_str[:8]}"
    bene_id = f"BENE_{hop_id.replace('-', '_')}"

    update_dict = bank_data.dict(exclude_unset=True)
    update_dict["payout_beneficiary_id"] = bene_id
    update_dict["updated_at"] = get_ist_now()

    # Attempt to sync with Cashfree Payouts beneficiary API
    name = (
        bank_data.bank_account_holder
        or hospital.get("legal_entity_name")
        or hospital.get("name")
        or "Hospital Facility"
    )
    email = hospital.get("email", "hospital@careseva.in")
    phone = hospital.get("phone", "9999999999")
    address = f"{hospital.get('address', '')}, {hospital.get('city', '')}"

    cf_resp = await payouts_client.add_beneficiary(
        bene_id=bene_id,
        name=name,
        email=email,
        phone=phone,
        bank_account=bank_data.bank_account_number,
        ifsc=bank_data.bank_ifsc,
        vpa=bank_data.upi_id,
        address=address
    )

    if cf_resp.get("status") in ["SUCCESS", "OK"] or cf_resp.get("subCode") in ["200", "409"]:
        update_dict["payout_beneficiary_status"] = "VERIFIED"
    else:
        update_dict["payout_beneficiary_status"] = "PENDING_VERIFICATION"

    await db["hospitals"].update_one(
        {"_id": h_obj_id},
        {"$set": update_dict}
    )

    return {
        "status": "success",
        "message": "Bank details updated successfully and synced with Cashfree Payouts",
        "beneficiary_id": bene_id,
        "beneficiary_status": update_dict["payout_beneficiary_status"],
        "cashfree_response": cf_resp
    }


@router.post("/hospital/{hospital_id}/sync-beneficiary")
async def sync_hospital_beneficiary(
    hospital_id: str,
    db = Depends(get_db)
):
    """
    Force register/sync the hospital as a Beneficiary on Cashfree Payouts.
    """
    hospital = None
    try:
        hospital = await db["hospitals"].find_one({"_id": ObjectId(hospital_id)})
    except Exception:
        pass
    if not hospital:
        hospital = await db["hospitals"].find_one({"hop_id": hospital_id})

    if not hospital:
        raise HTTPException(status_code=404, detail="Hospital not found")

    hop_id = hospital.get("hop_id") or f"HOSP_{str(hospital['_id'])[:8]}"
    bene_id = hospital.get("payout_beneficiary_id") or f"BENE_{hop_id.replace('-', '_')}"

    name = (
        hospital.get("bank_account_holder")
        or hospital.get("legal_entity_name")
        or hospital.get("name")
        or "Hospital Facility"
    )

    cf_resp = await payouts_client.add_beneficiary(
        bene_id=bene_id,
        name=name,
        email=hospital.get("email", "hospital@careseva.in"),
        phone=hospital.get("phone", "9999999999"),
        bank_account=hospital.get("bank_account_number"),
        ifsc=hospital.get("bank_ifsc"),
        vpa=hospital.get("upi_id"),
        address=f"{hospital.get('address', '')}, {hospital.get('city', '')}"
    )

    is_ok = cf_resp.get("status") in ["SUCCESS", "OK"] or cf_resp.get("subCode") in ["200", "409"]
    new_status = "VERIFIED" if is_ok else "PENDING_VERIFICATION"

    await db["hospitals"].update_one(
        {"_id": hospital["_id"]},
        {"$set": {
            "payout_beneficiary_id": bene_id,
            "payout_beneficiary_status": new_status,
            "updated_at": get_ist_now()
        }}
    )

    return {
        "status": "success" if is_ok else "warning",
        "beneficiary_id": bene_id,
        "beneficiary_status": new_status,
        "cashfree_response": cf_resp
    }


@router.get("/hospital/{hospital_id}/unsettled-summary")
async def get_hospital_unsettled_summary(
    hospital_id: str,
    db = Depends(get_db)
):
    """
    Calculates total unsettled revenue for a hospital from patient online payments.
    Currently gives 100% full amount to the hospital (0% platform fee).
    """
    hospital = None
    try:
        hospital = await db["hospitals"].find_one({"_id": ObjectId(hospital_id)})
    except Exception:
        pass
    if not hospital:
        hospital = await db["hospitals"].find_one({"hop_id": hospital_id})

    if not hospital:
        raise HTTPException(status_code=404, detail="Hospital not found")

    h_id_str = str(hospital["_id"])
    hop_id = hospital.get("hop_id")

    # Match all paid appointments not yet settled to the hospital
    query = {
        "$or": [{"hospital_id": h_id_str}, {"hospital_id": hop_id}],
        "payment_status": "DONE",
        "payout_settlement_status": {"$ne": "SETTLED"}
    }

    cursor = db["appointments"].find(query)
    unsettled_appts = await cursor.to_list(length=10000)

    gross_collected = 0.0
    appt_summaries = []
    for a in unsettled_appts:
        paid = float(a.get("paid_amount") or a.get("total_fee") or 0.0)
        gross_collected += paid
        appt_summaries.append({
            "appointment_id": str(a["_id"]),
            "patient_name": a.get("patient_name", "Patient"),
            "doctor_name": a.get("doctor_name", "Doctor"),
            "appointment_date": a.get("appointment_date"),
            "paid_amount": paid,
            "payment_order_id": a.get("payment_order_id")
        })

    # Fee calculation (Currently 0% CareSeva platform fee -> 100% to hospital)
    pct_fee = (gross_collected * (settings.PLATFORM_FEE_PERCENTAGE / 100.0))
    flat_fee = (len(unsettled_appts) * settings.PLATFORM_FEE_FLAT) if gross_collected > 0 else 0.0
    total_platform_fee = round(pct_fee + flat_fee, 2)
    net_hospital_payout = round(max(0.0, gross_collected - total_platform_fee), 2)

    return {
        "hospital_id": h_id_str,
        "hop_id": hop_id,
        "hospital_name": hospital.get("name"),
        "bank_account_number": hospital.get("bank_account_number"),
        "bank_ifsc": hospital.get("bank_ifsc"),
        "bank_account_holder": hospital.get("bank_account_holder"),
        "bank_name": hospital.get("bank_name"),
        "upi_id": hospital.get("upi_id"),
        "payout_beneficiary_id": hospital.get("payout_beneficiary_id"),
        "payout_beneficiary_status": hospital.get("payout_beneficiary_status", "UNREGISTERED"),
        "unsettled_appointments_count": len(unsettled_appts),
        "gross_collected": round(gross_collected, 2),
        "platform_fee": total_platform_fee,
        "platform_fee_percentage": settings.PLATFORM_FEE_PERCENTAGE,
        "net_payout_amount": net_hospital_payout,
        "currency": "INR",
        "appointments": appt_summaries[:50] # Top 50 recent
    }


@router.post("/disburse")
async def disburse_payout(
    request: DisbursePayoutRequest,
    db = Depends(get_db)
):
    """
    Executes a direct payout/disbursement to the hospital's bank account or UPI via Cashfree Payouts.
    """
    hospital_id = request.hospital_id
    hospital = None
    try:
        hospital = await db["hospitals"].find_one({"_id": ObjectId(hospital_id)})
    except Exception:
        pass
    if not hospital:
        hospital = await db["hospitals"].find_one({"hop_id": hospital_id})

    if not hospital:
        raise HTTPException(status_code=404, detail="Hospital facility not found")

    h_id_str = str(hospital["_id"])
    hop_id = hospital.get("hop_id") or f"HOSP_{h_id_str[:8]}"
    bene_id = hospital.get("payout_beneficiary_id") or f"BENE_{hop_id.replace('-', '_')}"

    # Verify hospital has banking/UPI info
    bank_acc = hospital.get("bank_account_number")
    bank_ifsc = hospital.get("bank_ifsc")
    upi_id = hospital.get("upi_id")

    transfer_mode = (request.transfer_mode or hospital.get("payout_preferred_mode") or "banktransfer").lower()

    if transfer_mode == "upi" and not upi_id:
        if bank_acc and bank_ifsc:
            transfer_mode = "banktransfer"
        else:
            raise HTTPException(status_code=400, detail="Hospital has no UPI ID or Bank Account configured. Please update bank details first.")
    elif transfer_mode == "banktransfer" and not (bank_acc and bank_ifsc):
        if upi_id:
            transfer_mode = "upi"
        else:
            raise HTTPException(status_code=400, detail="Hospital has no Bank Account Number & IFSC configured. Please update bank details first.")

    # Find unsettled appointments
    query = {
        "$or": [{"hospital_id": h_id_str}, {"hospital_id": hop_id}],
        "payment_status": "DONE",
        "payout_settlement_status": {"$ne": "SETTLED"}
    }
    cursor = db["appointments"].find(query)
    unsettled_appts = await cursor.to_list(length=10000)

    gross_sum = sum(float(a.get("paid_amount") or a.get("total_fee") or 0.0) for a in unsettled_appts)
    
    # Calculate payout amount
    if request.amount and float(request.amount) > 0:
        payout_amount = round(float(request.amount), 2)
        platform_fee = 0.0
    else:
        if gross_sum <= 0:
            raise HTTPException(status_code=400, detail="No unsettled patient payments found for this hospital.")
        pct_fee = (gross_sum * (settings.PLATFORM_FEE_PERCENTAGE / 100.0))
        flat_fee = (len(unsettled_appts) * settings.PLATFORM_FEE_FLAT)
        platform_fee = round(pct_fee + flat_fee, 2)
        payout_amount = round(max(1.0, gross_sum - platform_fee), 2)

    transfer_id = f"CS_PAY_{int(time.time())}_{uuid.uuid4().hex[:6].upper()}"

    # Ensure beneficiary is registered
    await payouts_client.add_beneficiary(
        bene_id=bene_id,
        name=hospital.get("bank_account_holder") or hospital.get("name"),
        email=hospital.get("email", "hospital@careseva.in"),
        phone=hospital.get("phone", "9999999999"),
        bank_account=bank_acc,
        ifsc=bank_ifsc,
        vpa=upi_id
    )

    # Initiate Payout Transfer
    cf_resp = await payouts_client.request_transfer(
        transfer_id=transfer_id,
        bene_id=bene_id,
        amount=payout_amount,
        remarks=request.remarks or f"CareSeva Settlement to {hospital.get('name')}",
        transfer_mode=transfer_mode
    )

    cf_data = cf_resp.get("data", {})
    transfer_status = "SUCCESS" if (cf_resp.get("status") == "SUCCESS" or cf_resp.get("subCode") == "200") else "PENDING"
    if cf_resp.get("status") == "ERROR" and not cf_resp.get("is_simulated"):
        transfer_status = "FAILED"

    utr = cf_data.get("utr") or (f"UTR_SIM_{transfer_id}" if cf_resp.get("is_simulated") else None)
    cf_transfer_id = cf_data.get("referenceId") or cf_data.get("transferId") or transfer_id
    now_ist = get_ist_now()

    appt_ids = [str(a["_id"]) for a in unsettled_appts]

    payout_record = {
        "transfer_id": transfer_id,
        "cf_transfer_id": cf_transfer_id,
        "hospital_id": h_id_str,
        "hop_id": hop_id,
        "hospital_name": hospital.get("name"),
        "amount": payout_amount,
        "gross_amount": gross_sum if not request.amount else payout_amount,
        "platform_fee": platform_fee,
        "currency": "INR",
        "transfer_mode": transfer_mode,
        "status": transfer_status,
        "utr": utr,
        "account_number": bank_acc if transfer_mode == "banktransfer" else None,
        "ifsc": bank_ifsc if transfer_mode == "banktransfer" else None,
        "upi_id": upi_id if transfer_mode == "upi" else None,
        "appointment_ids": appt_ids,
        "remarks": request.remarks,
        "raw_response": cf_resp,
        "created_at": now_ist,
        "updated_at": now_ist
    }

    await db["payouts"].insert_one(payout_record)

    # If payout succeeded or is pending, mark appointments as settled
    if transfer_status in ["SUCCESS", "PENDING"]:
        if appt_ids:
            await db["appointments"].update_many(
                {"_id": {"$in": [ObjectId(aid) for aid in appt_ids]}},
                {"$set": {
                    "payout_settlement_status": "SETTLED",
                    "payout_transfer_id": transfer_id,
                    "payout_settled_at": now_ist
                }}
            )

    return {
        "status": "SUCCESS" if transfer_status in ["SUCCESS", "PENDING"] else "FAILED",
        "transfer_id": transfer_id,
        "transfer_status": transfer_status,
        "amount": payout_amount,
        "utr": utr,
        "hospital_name": hospital.get("name"),
        "transfer_mode": transfer_mode,
        "settled_appointments_count": len(appt_ids),
        "message": f"Disbursement of ₹{payout_amount} to {hospital.get('name')} {transfer_status.lower()}",
        "cashfree_response": cf_resp
    }


@router.get("/transactions")
async def list_payout_transactions(
    hospital_id: Optional[str] = None,
    status_filter: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    db = Depends(get_db)
):
    """
    List all payout disbursement transactions.
    """
    query = {}
    if hospital_id:
        query["$or"] = [{"hospital_id": hospital_id}, {"hop_id": hospital_id}]
    if status_filter:
        query["status"] = status_filter.upper()

    cursor = db["payouts"].find(query).sort("created_at", -1).limit(limit)
    transactions = await cursor.to_list(length=limit)

    for t in transactions:
        t["id"] = str(t["_id"])
        t.pop("_id", None)

    return transactions


@router.get("/transfer-status/{transfer_id}")
async def get_live_transfer_status(
    transfer_id: str,
    db = Depends(get_db)
):
    """
    Checks real-time transfer status from Cashfree Payouts API.
    """
    cf_resp = await payouts_client.get_transfer_status(transfer_id)
    
    # Check if transfer status exists
    data = cf_resp.get("data", {})
    transfer_info = data.get("transfer", {})
    live_status = transfer_info.get("status")
    utr = transfer_info.get("utr")

    if live_status:
        update_fields = {"status": live_status, "updated_at": get_ist_now()}
        if utr:
            update_fields["utr"] = utr
        await db["payouts"].update_one(
            {"transfer_id": transfer_id},
            {"$set": update_fields}
        )

    return {
        "transfer_id": transfer_id,
        "status": live_status or "UNKNOWN",
        "utr": utr,
        "cashfree_response": cf_resp
    }


@router.get("/wallet-balance")
async def get_payout_wallet_balance():
    """
    Retrieves the current available balance in CareSeva's Cashfree Payouts account.
    """
    return await payouts_client.get_wallet_balance()


@router.post("/webhook")
async def cashfree_payout_webhook(
    request: Request,
    db = Depends(get_db)
):
    """
    Handles asynchronous transfer status updates from Cashfree Payouts.
    """
    try:
        data = await request.json()
        print(f"[Cashfree Payout Webhook]: {data.get('event') or data.get('type')}")

        transfer_id = data.get("transferId") or (data.get("data", {}).get("transfer", {}).get("transferId"))
        event_status = data.get("event") or data.get("status")
        utr = data.get("utr") or (data.get("data", {}).get("transfer", {}).get("utr"))

        if transfer_id and event_status:
            normalized_status = "SUCCESS" if "SUCCESS" in event_status.upper() else ("FAILED" if "FAIL" in event_status.upper() else "PENDING")
            set_dict = {"status": normalized_status, "updated_at": get_ist_now()}
            if utr:
                set_dict["utr"] = utr
            await db["payouts"].update_one(
                {"transfer_id": transfer_id},
                {"$set": set_dict}
            )

        return {"status": "OK"}
    except Exception as e:
        print(f"Error handling Cashfree Payout Webhook: {e}")
        return {"status": "ERROR", "detail": str(e)}
