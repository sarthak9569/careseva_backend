import httpx
import uuid
import hmac
import hashlib
import base64
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Header, Request, status
from pydantic import BaseModel, Field
from bson import ObjectId

from core.config import settings
from database import get_db
from models.queue import AppointmentInDB
from core.pid_generator import generate_unique_pid

router = APIRouter()

IST = timezone(timedelta(hours=5, minutes=30))

def get_ist_now() -> datetime:
    return datetime.now(IST)

def get_cashfree_base_url() -> str:
    env = (settings.CASHFREE_ENV or "SANDBOX").upper()
    if env == "PRODUCTION" or env == "PROD":
        return "https://api.cashfree.com/pg"
    return "https://sandbox.cashfree.com/pg"

class CashfreeCustomerDetails(BaseModel):
    customer_id: str
    customer_name: Optional[str] = "CareSeva Patient"
    customer_phone: str
    customer_email: Optional[str] = "patient@careseva.in"

class CreateOrderRequest(BaseModel):
    amount: float = Field(..., gt=0, description="Amount to be paid in INR")
    payment_option: str = Field(default="full", description="'full' or 'advance'")
    customer_details: CashfreeCustomerDetails
    booking_data: Dict[str, Any]
    order_note: Optional[str] = "CareSeva Appointment Consultation Fee"

class VerifyOrderRequest(BaseModel):
    order_id: str
    booking_data: Dict[str, Any]
    payment_option: str = "full"
    paid_amount: float
    total_fee: float

@router.post("/cashfree/create-order")
async def create_cashfree_order(request: CreateOrderRequest):
    """
    Creates a Cashfree payment order and returns the payment_session_id.
    """
    clean_amount = round(float(request.amount), 2)
    order_id = f"CS_ORD_{int(get_ist_now().timestamp())}_{uuid.uuid4().hex[:6].upper()}"
    customer_phone = request.customer_details.customer_phone or "9999999999"
    # Clean phone to 10 digits if possible
    digits_phone = "".join(filter(str.isdigit, customer_phone))
    if len(digits_phone) >= 10:
        clean_phone = digits_phone[-10:]
    else:
        clean_phone = "9999999999"

    customer_id = request.customer_details.customer_id or f"cust_{uuid.uuid4().hex[:8]}"
    if len(customer_id) < 3:
        customer_id = f"cust_{customer_id}_{uuid.uuid4().hex[:4]}"

    payload = {
        "order_id": order_id,
        "order_amount": clean_amount,
        "order_currency": "INR",
        "customer_details": {
            "customer_id": customer_id,
            "customer_name": request.customer_details.customer_name or "CareSeva Patient",
            "customer_email": request.customer_details.customer_email or "patient@careseva.in",
            "customer_phone": clean_phone
        },
        "order_meta": {
            "return_url": f"https://careseva.in/payment-callback?order_id={order_id}"
        },
        "order_note": request.order_note
    }

    base_url = get_cashfree_base_url()
    headers = {
        "x-client-id": settings.CASHFREE_APP_ID,
        "x-client-secret": settings.CASHFREE_SECRET_KEY,
        "x-api-version": settings.CASHFREE_API_VERSION,
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    # Attempt to communicate with Cashfree PG
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(f"{base_url}/orders", json=payload, headers=headers)
            
            if resp.status_code in [200, 201]:
                cf_data = resp.json()
                payment_session_id = cf_data.get("payment_session_id")
                env_str = settings.CASHFREE_ENV.upper()
                if env_str in ["PRODUCTION", "PROD"]:
                    payment_link = f"https://payments.cashfree.com/order/#{payment_session_id}"
                else:
                    payment_link = f"https://payments-test.cashfree.com/order/#{payment_session_id}"

                return {
                    "status": "SUCCESS",
                    "order_id": cf_data.get("order_id", order_id),
                    "payment_session_id": payment_session_id,
                    "payment_link": payment_link,
                    "cf_order_id": cf_data.get("cf_order_id"),
                    "order_amount": clean_amount,
                    "order_currency": "INR",
                    "environment": env_str,
                    "is_simulated": False
                }
            else:
                error_body = resp.text
                print(f"[Cashfree API Error {resp.status_code}]: {error_body}")
                raise HTTPException(
                    status_code=resp.status_code,
                    detail=f"Cashfree Order Creation Failed: {error_body}"
                )
    except httpx.RequestError as exc:
        print(f"[Cashfree Network Error]: {exc}")
        raise HTTPException(
            status_code=502,
            detail=f"Unable to connect to Cashfree payment gateway: {str(exc)}"
        )


@router.post("/cashfree/verify-order")
async def verify_cashfree_order(
    request: VerifyOrderRequest,
    db = Depends(get_db)
):
    """
    Verifies payment order status with Cashfree and confirms appointment booking.
    """
    order_id = request.order_id
    booking_data = request.booking_data
    payment_option = request.payment_option.lower()
    
    is_paid = False
    payment_mode = "CASHFREE_PG"
    reference_id = order_id
    current_status = "UNKNOWN"

    # If running with real Cashfree credentials, query Cashfree order API
    if not ("TEST_" in settings.CASHFREE_APP_ID or order_id.startswith("sandbox_") or settings.CASHFREE_APP_ID == "YOUR_CASHFREE_APP_ID"):
        base_url = get_cashfree_base_url()
        headers = {
            "x-client-id": settings.CASHFREE_APP_ID,
            "x-client-secret": settings.CASHFREE_SECRET_KEY,
            "x-api-version": settings.CASHFREE_API_VERSION,
            "Content-Type": "application/json"
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{base_url}/orders/{order_id}", headers=headers)
                if resp.status_code == 200:
                    order_info = resp.json()
                    current_status = order_info.get("order_status", "UNKNOWN")
                    if current_status == "PAID":
                        is_paid = True
                        reference_id = str(order_info.get("cf_order_id") or order_id)
                else:
                    print(f"Cashfree verification returned {resp.status_code}: {resp.text}")
        except Exception as e:
            print(f"Error querying Cashfree verification: {e}")
    else:
        # Sandbox simulated payment verification
        is_paid = True
        current_status = "PAID (SANDBOX)"

    if not is_paid:
        raise HTTPException(
            status_code=400,
            detail=f"Payment status is '{current_status}'. Please complete your payment on Cashfree to confirm booking."
        )

    # Calculation of payment fields
    total_fee = float(request.total_fee)
    paid_amount = float(request.paid_amount)
    is_full = payment_option == "full"
    payment_status = "DONE" if is_full else "PENDING"
    remaining_amount = 0.0 if is_full else max(0.0, total_fee - paid_amount)

    now_ist = get_ist_now()

    # Create Appointment in DB
    appt_dict = {
        "hospital_id": booking_data.get("hospital_id", ""),
        "department_id": booking_data.get("department_id", ""),
        "department_name": booking_data.get("department_name", "General"),
        "doctor_id": booking_data.get("doctor_id", ""),
        "doctor_name": booking_data.get("doctor_name", ""),
        "patient_id": booking_data.get("patient_id", ""),
        "booking_for": booking_data.get("booking_for", "myself"),
        "patient_name": booking_data.get("patient_name", "Unknown Patient"),
        "patient_age": int(booking_data.get("patient_age") or 0),
        "patient_gender": booking_data.get("patient_gender", "-"),
        "patient_phone": booking_data.get("patient_phone", ""),
        "appointment_date": booking_data.get("appointment_date", now_ist.strftime("%Y-%m-%d")),
        "status": "BOOKED",
        "booking_source": "CARESEVA_APP",
        "payment_status": payment_status,
        "payment_option": payment_option,
        "payment_gateway": "CASHFREE",
        "payment_order_id": order_id,
        "payment_reference_id": reference_id,
        "total_fee": total_fee,
        "paid_amount": paid_amount,
        "remaining_amount": remaining_amount,
        "created_at": now_ist,
        "updated_at": now_ist
    }

    result = await db["appointments"].insert_one(appt_dict)
    appt_id = str(result.inserted_id)

    # Sync into patients collection
    existing_patient = None
    if appt_dict["patient_phone"]:
        existing_patient = await db["patients"].find_one({
            "hospital_id": appt_dict["hospital_id"],
            "phone": appt_dict["patient_phone"]
        })
    if not existing_patient and appt_dict["patient_name"]:
        existing_patient = await db["patients"].find_one({
            "hospital_id": appt_dict["hospital_id"],
            "name": appt_dict["patient_name"]
        })

    assigned_pid = ""
    if not existing_patient:
        assigned_pid = await generate_unique_pid(db)
        await db["patients"].insert_one({
            "pid": assigned_pid,
            "name": appt_dict["patient_name"],
            "phone": appt_dict["patient_phone"],
            "age": appt_dict["patient_age"],
            "gender": appt_dict["patient_gender"],
            "department_id": appt_dict["department_id"],
            "department_name": appt_dict["department_name"],
            "last_visit": now_ist.strftime("%Y-%m-%d"),
            "registration_source": "CARESEVA_APP",
            "hospital_id": appt_dict["hospital_id"],
            "appointment_id": appt_id,
            "payment_status": payment_status,
            "payment_option": payment_option,
            "total_fee": total_fee,
            "paid_amount": paid_amount,
            "remaining_amount": remaining_amount,
            "created_at": now_ist,
            "updated_at": now_ist
        })
    else:
        assigned_pid = existing_patient.get("pid", "")
        await db["patients"].update_one(
            {"_id": existing_patient["_id"]},
            {"$set": {
                "last_visit": now_ist.strftime("%Y-%m-%d"),
                "payment_status": payment_status,
                "payment_option": payment_option,
                "total_fee": total_fee,
                "paid_amount": paid_amount,
                "remaining_amount": remaining_amount,
                "appointment_id": appt_id,
                "updated_at": now_ist
            }}
        )

    # Update appointment with resolved PID if available
    if assigned_pid and not appt_dict.get("patient_id"):
        await db["appointments"].update_one(
            {"_id": ObjectId(appt_id)},
            {"$set": {"patient_id": assigned_pid}}
        )

    return {
        "status": "SUCCESS",
        "message": "Payment verified and appointment confirmed successfully!",
        "appointment_id": appt_id,
        "pid": assigned_pid,
        "order_id": order_id,
        "payment_status": payment_status,
        "paid_amount": paid_amount,
        "remaining_amount": remaining_amount,
        "payment_gateway": "CASHFREE"
    }


@router.post("/cashfree/webhook")
async def cashfree_webhook(
    request: Request,
    db = Depends(get_db)
):
    """
    Webhook handler for asynchronous payment updates from Cashfree.
    """
    try:
        body_bytes = await request.body()
        data = await request.json()
        print(f"[Cashfree Webhook Received]: {data.get('type')}")

        event_type = data.get("type")
        event_data = data.get("data", {})
        order_data = event_data.get("order", {})
        order_id = order_data.get("order_id")

        if event_type in ["PAYMENT_SUCCESS_WEBHOOK", "ORDER_PAID_WEBHOOK"] and order_id:
            # Update appointment status in db
            await db["appointments"].update_one(
                {"payment_order_id": order_id},
                {"$set": {
                    "payment_webhook_received": True,
                    "payment_status": "DONE",
                    "updated_at": get_ist_now()
                }}
            )
        
        return {"status": "OK"}
    except Exception as e:
        print(f"Error handling Cashfree webhook: {e}")
        return {"status": "ERROR", "detail": str(e)}
