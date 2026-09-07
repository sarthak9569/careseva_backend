import httpx
import uuid
import hmac
import hashlib
import base64
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Header, Request, status, Query
from fastapi.responses import HTMLResponse
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
    customer_id: Optional[str] = None
    customer_name: Optional[str] = "CareSeva Patient"
    customer_phone: Optional[str] = "9999999999"
    customer_email: Optional[str] = "patient@careseva.in"

class CreateOrderRequest(BaseModel):
    amount: float = Field(..., gt=0, description="Amount to be paid in INR")
    payment_option: Optional[str] = "full"
    customer_details: Optional[CashfreeCustomerDetails] = None
    customer_id: Optional[str] = None
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    customer_email: Optional[str] = None
    booking_data: Optional[Dict[str, Any]] = None
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
    
    # Extract customer info from nested customer_details or root fields
    raw_phone = (request.customer_details.customer_phone if request.customer_details and request.customer_details.customer_phone else None) or request.customer_phone or "9999999999"
    digits_phone = "".join(filter(str.isdigit, str(raw_phone)))
    clean_phone = digits_phone[-10:] if len(digits_phone) >= 10 else "9999999999"

    raw_id = (request.customer_details.customer_id if request.customer_details and request.customer_details.customer_id else None) or request.customer_id or f"cust_{uuid.uuid4().hex[:8]}"
    clean_id = raw_id if len(raw_id) >= 3 else f"cust_{raw_id}_{uuid.uuid4().hex[:4]}"

    clean_name = (request.customer_details.customer_name if request.customer_details and request.customer_details.customer_name else None) or request.customer_name or "CareSeva Patient"
    clean_email = (request.customer_details.customer_email if request.customer_details and request.customer_details.customer_email else None) or request.customer_email or "patient@careseva.in"

    payload = {
        "order_id": order_id,
        "order_amount": clean_amount,
        "order_currency": "INR",
        "customer_details": {
            "customer_id": clean_id,
            "customer_name": clean_name,
            "customer_email": clean_email,
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
                is_prod = env_str in ["PRODUCTION", "PROD"]
                
                # Whitelisted CareSeva Web Drop Checkout URL
                checkout_url = f"https://careseva.co.in/checkout?session_id={payment_session_id}&env={'production' if is_prod else 'sandbox'}&order_id={cf_data.get('order_id', order_id)}"

                return {
                    "status": "SUCCESS",
                    "order_id": cf_data.get("order_id", order_id),
                    "payment_session_id": payment_session_id,
                    "checkout_url": checkout_url,
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


@router.get("/cashfree/checkout-page", response_class=HTMLResponse)
async def cashfree_checkout_page(
    session_id: str = Query(..., description="Cashfree Payment Session ID"),
    env: str = Query("production", description="Environment: 'production' or 'sandbox'"),
    order_id: Optional[str] = Query(None, description="Order ID")
):
    """
    Renders official Cashfree JS Drop Checkout page for seamless UPI, Card, NetBanking.
    Bypasses Android Play Store trusted installer restrictions for side-loaded/test apps.
    """
    mode = "sandbox" if env.lower() == "sandbox" else "production"
    
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CareSeva™ Secure Checkout</title>
    <script src="https://sdk.cashfree.com/js/v3/cashfree.js"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
        body {{ background: #f8fafc; min-height: 100vh; display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 16px; color: #1e293b; }}
        .checkout-box {{ background: white; width: 100%; max-width: 460px; border-radius: 20px; box-shadow: 0 12px 30px rgba(0,0,0,0.08); overflow: hidden; border: 1px solid #e2e8f0; }}
        .header {{ background: linear-gradient(135deg, #4f46e5, #7c3aed); padding: 24px; text-align: center; color: white; }}
        .header h1 {{ font-size: 20px; font-weight: 700; letter-spacing: -0.5px; }}
        .header p {{ font-size: 13px; opacity: 0.9; margin-top: 4px; }}
        .body {{ padding: 32px 24px; text-align: center; }}
        .spinner {{ width: 44px; height: 44px; border: 4px solid #e2e8f0; border-top: 4px solid #4f46e5; border-radius: 50%; animation: spin 0.9s linear infinite; margin: 0 auto 16px; }}
        @keyframes spin {{ 0% {{ transform: rotate(0deg); }} 100% {{ transform: rotate(360deg); }} }}
        .loading-title {{ font-size: 16px; font-weight: 600; color: #334155; }}
        .loading-desc {{ font-size: 13px; color: #64748b; margin-top: 6px; line-height: 1.5; }}
        .order-badge {{ display: inline-block; background: #f1f5f9; padding: 6px 14px; border-radius: 8px; font-size: 12px; font-weight: 600; color: #475569; margin-top: 16px; }}
        .security-badge {{ margin-top: 24px; display: flex; align-items: center; justify-content: center; gap: 6px; font-size: 12px; color: #10b981; font-weight: 600; }}
    </style>
</head>
<body>
    <div class="checkout-box">
        <div class="header">
            <h1>CareSeva™ Payments</h1>
            <p>256-Bit SSL Encrypted & RBI Compliant</p>
        </div>
        <div class="body" id="drop-container">
            <div class="spinner"></div>
            <div class="loading-title">Loading Payment Options...</div>
            <p class="loading-desc">Connecting to Cashfree Secure Gateway (UPI, Cards, NetBanking)...</p>
            {f'<div class="order-badge">Order: {order_id}</div>' if order_id else ''}
            <div class="security-badge">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M12 1L3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5l-9-4zm-2 16l-4-4 1.41-1.41L10 14.17l6.59-6.59L18 9l-8 8z"/></svg>
                Official Cashfree Secure Drop Checkout
            </div>
        </div>
    </div>

    <script>
        window.addEventListener('DOMContentLoaded', () => {{
            try {{
                const cashfree = Cashfree({{
                    mode: "{mode}"
                }});
                
                cashfree.checkout({{
                    paymentSessionId: "{session_id}",
                    redirectTarget: "_self"
                }});
            }} catch (err) {{
                document.getElementById('drop-container').innerHTML = `
                    <div style="color: #ef4444; font-weight: bold; font-size: 16px;">Failed to initialize checkout</div>
                    <p style="color: #64748b; font-size: 13px; margin-top: 8px;">` + err.message + `</p>
                `;
            }}
        }});
    </script>
</body>
</html>"""
    return HTMLResponse(content=html_content)


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
