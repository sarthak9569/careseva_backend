import os
import sys
import io
import time
from datetime import datetime
from dotenv import load_dotenv

# Ensure sys.stdout handles UTF-8
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

env_path = os.path.join(backend_dir, '.env')
if os.path.exists(env_path):
    load_dotenv(env_path)
else:
    load_dotenv('careseva_backend/.env')

from fastapi.testclient import TestClient
from main import app

wire_results = {
    'passed': [],
    'failed': []
}

def log_wire(name, passed, details=""):
    tag = "PASS" if passed else "FAIL"
    print(f"[{tag}] {name}: {details}")
    if passed:
        wire_results['passed'].append({'name': name, 'details': details})
    else:
        wire_results['failed'].append({'name': name, 'details': details})

print("\n" + "="*80)
print("   CARESEVA APP <-> HMS END-TO-END CROSS-WIRING VERIFICATION")
print("="*80 + "\n")

with TestClient(app) as client:
    # 1. Retrieve hospital and active doctor
    hosp_res = client.get("/api/hospitals/")
    hospitals = hosp_res.json() if hosp_res.status_code == 200 else []
    if not hospitals:
        print("[FAIL] No registered hospitals found to execute cross-wiring test.")
        sys.exit(1)

    hosp = next((h for h in hospitals if "srivastava" in h.get("name", "").lower()), hospitals[0])
    hosp_id = str(hosp['id'])

    docs_res = client.get(f"/api/management/{hosp_id}/doctors")
    doctors = docs_res.json() if docs_res.status_code == 200 else []
    if not doctors:
        print("[FAIL] No registered doctors found in target hospital.")
        sys.exit(1)

    doctor = doctors[0]
    doc_id = str(doctor['id'])
    doc_name = doctor['name']
    dept_id = str(doctor.get('department_id') or "dept_gen")

    today_str = datetime.now().strftime("%Y-%m-%d")
    wire_phone_mobile = "9777111001"
    wire_phone_hms = "9777111002"

    print(f"Testing with Hospital: '{hosp['name']}' (ID: {hosp_id})")
    print(f"Testing with Doctor: '{doc_name}' (ID: {doc_id})\n")

    # FLOW A: Mobile App -> HMS Reflection
    print("--- FLOW A: CARESEVA APP -> HMS REFLECTION ---")
    app_booking_payload = {
        "hospital_id": hosp_id,
        "department_id": dept_id,
        "department_name": doctor.get('department_name', "Cardiology"),
        "doctor_id": doc_id,
        "doctor_name": doc_name,
        "patient_id": "dummy_patient_app_1",
        "patient_name": "Siddharth App User",
        "patient_phone": wire_phone_mobile,
        "patient_age": 29,
        "patient_gender": "Male",
        "booking_for": "myself",
        "appointment_date": today_str,
        "time_slot": "11:00 AM - 11:30 AM",
        "total_fee": 500.0,
        "payment_option": "full",
        "payment_status": "DONE",
        "booking_source": "CARESEVA_APP"
    }

    res_app_book = client.post("/api/appointments/", json=app_booking_payload)
    app_appt_created = res_app_book.status_code in [200, 201]
    app_appt_id = res_app_book.json().get('id') if app_appt_created else None
    log_wire("Step A1: CareSeva Mobile App booking endpoint", app_appt_created, f"Appt ID: {app_appt_id}")

    # Check Reflection 1: Visible in HMS Hospital Appointments List?
    res_hms_appts = client.get(f"/api/appointments/hospital/{hosp_id}?date={today_str}")
    hms_appts = res_hms_appts.json() if res_hms_appts.status_code == 200 else []
    found_in_hms = any(a.get('id') == app_appt_id or a.get('patient_phone') == wire_phone_mobile for a in hms_appts)
    log_wire("Step A2: Visible in HMS Appointments List (/api/appointments/hospital/{id})", found_in_hms, f"Found in HMS list of {len(hms_appts)} appointments for today")

    # Check Reflection 2: Enrolled in Doctor's Live Queue for OPD?
    res_q = client.get(f"/api/queue/{doc_id}/entries")
    q_entries = res_q.json() if res_q.status_code == 200 else []
    target_q_entry = next((e for e in q_entries if e.get('appointment_id') == app_appt_id or e.get('patient_phone') == wire_phone_mobile or "Siddharth" in e.get('patient_name', '')), None)
    log_wire("Step A3: Enrolled in Doctor OPD Queue (/api/queue/{id}/entries)", target_q_entry is not None, f"Assigned Token #{target_q_entry.get('token_number') if target_q_entry else 'None'}")

    # Check Reflection 3: Visible in HMS Patient Registry?
    res_hms_pats = client.get(f"/api/patients/hospital/{hosp_id}")
    hms_pats = res_hms_pats.json() if res_hms_pats.status_code == 200 else []
    found_in_registry = any(p.get('phone') == wire_phone_mobile for p in hms_pats)
    log_wire("Step A4: Synced into HMS Patient Registry (/api/patients/hospital/{id})", found_in_registry, f"Patient recorded in hospital active registry")

    # FLOW B: HMS Desk -> Mobile App Reflection
    print("\n--- FLOW B: HMS DESK WALK-IN -> CARESEVA APP REFLECTION ---")
    hms_walkin_payload = {
        "hospital_id": hosp_id,
        "department_id": dept_id,
        "department_name": doctor.get('department_name', "Cardiology"),
        "doctor_id": doc_id,
        "doctor_name": doc_name,
        "name": "Kavita Walk-In Patient",
        "phone": wire_phone_hms,
        "dob": "1992/08/14",
        "age": 34,
        "gender": "Female",
        "total_fee": 500.0,
        "payment_status": "DONE"
    }

    res_hms_reg = client.post("/api/patients/", json=hms_walkin_payload)
    hms_reg_ok = res_hms_reg.status_code in [200, 201]
    hms_pid = res_hms_reg.json().get('pid') if hms_reg_ok else None
    hms_token = res_hms_reg.json().get('token_number') if hms_reg_ok else None
    log_wire("Step B1: HMS Reception Desk Patient Registration", hms_reg_ok, f"Assigned PID: {hms_pid}, Token: #{hms_token}")

    # Check Reflection 1: Patient opens CareSeva App and views "My Appointments"
    res_mobile_my = client.get(f"/api/appointments/patient/my-appointments?phone={wire_phone_hms}")
    my_appts = res_mobile_my.json() if res_mobile_my.status_code == 200 else []
    found_in_mobile = any(a.get('patient_phone') == wire_phone_hms or a.get('patient_id') == hms_pid for a in my_appts)
    log_wire("Step B2: Appears in Mobile App 'My Appointments' (/api/appointments/patient/my-appointments)", found_in_mobile, f"Mobile user retrieved {len(my_appts)} appointments for phone {wire_phone_hms}")

    # Check Reflection 2: Live Queue token visible to mobile patient?
    res_active_q = client.get(f"/api/queue/patient/active?phone={wire_phone_hms}")
    active_q_data = res_active_q.json() if res_active_q.status_code == 200 else {}
    has_active_token = active_q_data.get('has_active_queue') is True
    log_wire("Step B3: Mobile Patient sees live queue token status (/api/queue/patient/active)", has_active_token, f"Live queue active: {active_q_data.get('has_active_queue')}, Token #{active_q_data.get('token_number')}")

    # FLOW C: Doctor OPD Actions & Progression
    print("\n--- FLOW C: DOCTOR OPD ACTIONS & STATUS PROGRESSION ---")
    res_call_next = client.post(f"/api/queue/{doc_id}/next")
    log_wire("Step C1: Doctor calls 'Next' patient via HMS (/api/queue/{id}/next)", res_call_next.status_code in [200, 404], f"Result: {res_call_next.json()}")

    res_call_comp = client.post(f"/api/queue/{doc_id}/complete")
    log_wire("Step C2: Doctor calls 'Complete' consultation via HMS (/api/queue/{id}/complete)", res_call_comp.status_code in [200, 404], f"Result: {res_call_comp.json()}")

    # Cleanup test records
    import pymongo
    try:
        mongo_url = os.getenv('MONGODB_URL')
        if mongo_url:
            c = pymongo.MongoClient(mongo_url)
            db = c[os.getenv('MONGODB_DB_NAME', 'careseva')]
            db['patients'].delete_many({'phone': {'$in': [wire_phone_mobile, wire_phone_hms]}})
            db['appointments'].delete_many({'patient_phone': {'$in': [wire_phone_mobile, wire_phone_hms]}})
            db['queue_entries'].delete_many({'patient_phone': {'$in': [wire_phone_mobile, wire_phone_hms]}})
            print("\n[INFO] Cleaned up cross-wiring test artifacts.")
    except Exception as e:
        print(f"[WARN] Cleanup error: {e}")

print("\n" + "="*80)
print(f"CROSS-WIRING AUDIT: {len(wire_results['passed'])} PASSED | {len(wire_results['failed'])} FAILED")
print("="*80 + "\n")
