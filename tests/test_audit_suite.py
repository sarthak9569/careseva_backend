import os
import sys
import io
import time
from datetime import datetime
from dotenv import load_dotenv

# Ensure sys.stdout handles UTF-8 (prevents UnicodeEncodeError on Windows terminals with ₹ symbol)
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

results = {
    'passed': [],
    'failed': [],
    'warnings': []
}

def record_test(name, passed, details="", duration_ms=0):
    status = "PASS" if passed else "FAIL"
    print(f"[{status}] {name} ({duration_ms:.1f}ms) - {details}")
    if passed:
        results['passed'].append({'name': name, 'details': details, 'duration': duration_ms})
    else:
        results['failed'].append({'name': name, 'details': details, 'duration': duration_ms})

print("\n" + "="*80)
print("   CARESEVA END-TO-END AUTOMATED AUDIT & PRODUCTION READINESS TEST SUITE")
print("="*80 + "\n")

with TestClient(app) as client:
    # 1. System Health & DB Connectivity
    t0 = time.time()
    res = client.get("/health")
    d = (time.time() - t0)*1000
    record_test("System Health Endpoint (/health)", res.status_code == 200 and res.json().get('status') == 'ok', res.text, d)

    t0 = time.time()
    res = client.get("/test-db")
    d = (time.time() - t0)*1000
    collections = res.json().get('collections', []) if res.status_code == 200 else []
    record_test("Database Connectivity & Collections (/test-db)", res.status_code == 200 and len(collections) > 0, f"Found {len(collections)} collections: {collections}", d)

    # 2. Hospitals Directory & Search
    t0 = time.time()
    res = client.get("/api/hospitals/")
    d = (time.time() - t0)*1000
    hospitals = res.json() if res.status_code == 200 else []
    
    hosp = next((h for h in hospitals if "srivastava" in h.get("name", "").lower()), hospitals[0] if hospitals else None)
    hosp_id = str(hosp['id']) if hosp else None
    hosp_name = hosp.get('name') if hosp else "None"
    record_test("Hospital Directory Listing (/api/hospitals/)", res.status_code == 200 and len(hospitals) > 0, f"Retrieved {len(hospitals)} registered hospitals. Active: '{hosp_name}' (ID: {hosp_id})", d)

    if hosp_id:
        t0 = time.time()
        res = client.get(f"/api/hospitals/{hosp_id}")
        d = (time.time() - t0)*1000
        record_test("Hospital Details by ID (/api/hospitals/{{id}})", res.status_code == 200 and res.json().get('id') == hosp_id, f"Hospital Name: {res.json().get('name')}", d)

    # 3. Hospital Departments & Doctors Management
    departments = []
    doctors = []
    if hosp_id:
        t0 = time.time()
        res = client.get(f"/api/management/{hosp_id}/departments")
        d = (time.time() - t0)*1000
        departments = res.json() if res.status_code == 200 else []
        record_test("Hospital Departments Listing (/api/management/{{id}}/departments)", res.status_code == 200, f"Found {len(departments)} departments.", d)

        t0 = time.time()
        res = client.get(f"/api/management/{hosp_id}/doctors")
        d = (time.time() - t0)*1000
        doctors = res.json() if res.status_code == 200 else []
        doc_id = str(doctors[0]['id']) if doctors else None
        doc_name = doctors[0].get('name') if doctors else "None"
        record_test("Hospital Doctors Listing (/api/management/{{id}}/doctors)", res.status_code == 200 and len(doctors) > 0, f"Found {len(doctors)} active doctors. Sample: {doc_name} (ID: {doc_id})", d)

        t0 = time.time()
        res = client.get(f"/api/management/{hosp_id}/dashboard-stats")
        d = (time.time() - t0)*1000
        record_test("Hospital Dashboard Stats (/api/management/{{id}}/dashboard-stats)", res.status_code == 200, f"Stats: {res.json()}", d)

    # 4. Patient Directory & Medico-Legal Master Records (Performance Benchmark)
    if hosp_id:
        t0 = time.time()
        res = client.get(f"/api/patients/hospital/{hosp_id}")
        d = (time.time() - t0)*1000
        pats = res.json() if res.status_code == 200 else []
        record_test("HMS Patients Registry Table (/api/patients/hospital/{{id}})", res.status_code == 200 and d < 1500, f"{len(pats)} patients retrieved in {d:.1f}ms (< 1.5s threshold)", d)

        t0 = time.time()
        res = client.get(f"/api/patients/hospital/{hosp_id}/directory")
        d = (time.time() - t0)*1000
        dir_pats = res.json() if res.status_code == 200 else []
        record_test("Master Medico-Legal Patient Directory (/api/patients/hospital/{{id}}/directory)", res.status_code == 200 and d < 2000, f"{len(dir_pats)} patient records assembled in {d:.1f}ms (< 2s threshold)", d)

    # 5. Anti-Duplicacy Patient Walk-in Registration (Strict Verification)
    test_phone = "9888877771"
    test_name = "Audit Test Patient"
    test_dob = "1995/05/15"
    initial_pid = None

    if hosp_id and doctors:
        target_doc = doctors[0]
        target_doc_id = str(target_doc['id'])
        target_doc_name = target_doc.get('name')
        target_dept_id = str(target_doc.get('department_id') or (departments[0]['id'] if departments else ""))
        target_dept_name = target_doc.get('department_name') or "Cardiology"

        # Step A: Register initial appointment
        reg_payload = {
            "hospital_id": hosp_id,
            "department_id": target_dept_id,
            "department_name": target_dept_name,
            "doctor_id": target_doc_id,
            "name": test_name,
            "phone": test_phone,
            "dob": test_dob,
            "age": 31,
            "gender": "Male",
            "total_fee": 500.0,
            "payment_status": "DONE"
        }
        t0 = time.time()
        res_reg1 = client.post("/api/patients/", json=reg_payload)
        d = (time.time() - t0)*1000
        initial_pid = res_reg1.json().get('pid') if res_reg1.status_code in [200, 201] else None
        record_test("New Walk-in Patient Registration (/api/patients/)", res_reg1.status_code in [200, 201], f"Generated PID: {initial_pid}, Token: #{res_reg1.json().get('token_number')}", d)

        # Step B: Duplicate registration attempt (Same Doctor, Same Day, Same Person)
        t0 = time.time()
        res_dup = client.post("/api/patients/", json=reg_payload)
        d = (time.time() - t0)*1000
        dup_blocked = res_dup.status_code == 409 and res_dup.json().get('detail', {}).get('code') == 'DUPLICATE_APPOINTMENT'
        record_test("Duplicate Booking Blocked - Same Doctor/Day (/api/patients/)", dup_blocked, f"Response HTTP {res_dup.status_code}, Reason: {res_dup.json().get('detail', {}).get('message')}", d)

        # Step C: Pre-check duplicate endpoint
        t0 = time.time()
        res_check = client.get("/api/patients/check-duplicate", params={
            "hospital_id": hosp_id,
            "phone": test_phone,
            "name": test_name,
            "dob": test_dob,
            "doctor_id": target_doc_id
        })
        d = (time.time() - t0)*1000
        check_ok = res_check.status_code == 200 and res_check.json().get('has_duplicate') is True
        record_test("Pre-check Duplicate API (/api/patients/check-duplicate)", check_ok, f"has_duplicate: {res_check.json().get('has_duplicate')}", d)

        # Step D: Different Doctor on Same Day (Should be ALLOWED and reuse PID)
        if len(doctors) > 1:
            diff_doc = doctors[1]
            diff_doc_id = str(diff_doc['id'])
            diff_doc_name = diff_doc.get('name')
            diff_payload = {
                **reg_payload,
                "doctor_id": diff_doc_id,
                "doctor_name": diff_doc_name,
                "department_id": str(diff_doc.get('department_id') or target_dept_id),
                "department_name": diff_doc.get('department_name') or "Pediatrics"
            }
            t0 = time.time()
            res_diff = client.post("/api/patients/", json=diff_payload)
            d = (time.time() - t0)*1000
            diff_allowed = res_diff.status_code in [200, 201] and res_diff.json().get('pid') == initial_pid
            record_test("Multi-Doctor Booking Allowed - Reuses Same PID", diff_allowed, f"Reused PID: {res_diff.json().get('pid')} for doctor '{diff_doc_name}'", d)

    # 6. Appointments Booking via Mobile API & Conflict Checking
    if hosp_id and doctors:
        fresh_mobile_phone = "9112223334"
        appt_payload = {
            "hospital_id": hosp_id,
            "department_id": str(doctors[0].get('department_id') or (departments[0]['id'] if departments else "dept_gen")),
            "department_name": doctors[0].get('department_name') or "General",
            "doctor_id": str(doctors[0]['id']),
            "doctor_name": doctors[0].get('name'),
            "patient_id": "CS-P-10099",
            "patient_name": "Fresh Mobile Patient",
            "patient_phone": fresh_mobile_phone,
            "booking_for": "myself",
            "appointment_date": datetime.now().strftime("%Y-%m-%d"),
            "total_fee": 500.0,
            "payment_option": "full",
            "payment_status": "DONE",
            "booking_source": "CARESEVA_APP"
        }
        t0 = time.time()
        res_appt = client.post("/api/appointments/", json=appt_payload)
        d = (time.time() - t0)*1000
        appt_id = res_appt.json().get('id') if res_appt.status_code in [200, 201] else None
        record_test("Mobile App Appointment Creation (/api/appointments/)", res_appt.status_code in [200, 201], f"Created Appt ID: {appt_id}", d)

        # Re-booking same doctor via mobile app with same phone/PID -> Should be blocked 400
        t0 = time.time()
        res_mobile_dup = client.post("/api/appointments/", json=appt_payload)
        d = (time.time() - t0)*1000
        mobile_dup_blocked = res_mobile_dup.status_code == 400
        record_test("Mobile Duplicate Rejection (/api/appointments/)", mobile_dup_blocked, f"Response: {res_mobile_dup.json().get('detail', {}).get('message') if isinstance(res_mobile_dup.json().get('detail'), dict) else res_mobile_dup.json().get('detail')}", d)

    # 7. Queue Progression & Token Management
    if hosp_id and doctors:
        q_doc_id = str(doctors[0]['id'])
        t0 = time.time()
        res_q = client.get(f"/api/queue/{q_doc_id}/entries")
        d = (time.time() - t0)*1000
        record_test("Doctor Active Queue Entries Fetch (/api/queue/{{id}}/entries)", res_q.status_code == 200, f"Found {len(res_q.json())} entries in doctor queue", d)

        t0 = time.time()
        res_next = client.post(f"/api/queue/{q_doc_id}/next")
        d = (time.time() - t0)*1000
        record_test("Queue Call Next Patient (/api/queue/{{id}}/next)", res_next.status_code in [200, 404], f"Result: {res_next.json()}", d)

        t0 = time.time()
        res_comp = client.post(f"/api/queue/{q_doc_id}/complete")
        d = (time.time() - t0)*1000
        record_test("Queue Complete Current Patient (/api/queue/{{id}}/complete)", res_comp.status_code in [200, 404], f"Result: {res_comp.json()}", d)

    # 8. IPD Admissions Lifecycle
    if hosp_id:
        adm_payload = {
            "hospital_id": hosp_id,
            "patient_name": "Audit Admission Patient",
            "patient_phone": "9991112223",
            "patient_dob": "1988/03/20",
            "patient_age": 38,
            "patient_gender": "Female",
            "department_id": str(departments[0]['id']) if departments else "dept_1",
            "department_name": departments[0].get('name') if departments else "Emergency",
            "doctor_id": str(doctors[0]['id']) if doctors else "doc_1",
            "doctor_name": doctors[0].get('name') if doctors else "Dr. Attending",
            "ward_type": "General Ward",
            "bed_number": "ICU-Bed-04",
            "provisional_diagnosis": "Acute Observation",
            "chief_complaints": "Chest discomfort"
        }
        t0 = time.time()
        res_adm = client.post("/api/admissions/", json=adm_payload)
        d = (time.time() - t0)*1000
        adm_id = res_adm.json().get('id') if res_adm.status_code in [200, 201] else None
        record_test("IPD Patient Admission (/api/admissions/)", res_adm.status_code in [200, 201], f"Admitted PID: {res_adm.json().get('patient_id')}, IPD Number: {res_adm.json().get('ipd_number')}", d)

        t0 = time.time()
        res_adms = client.get(f"/api/admissions/hospital/{hosp_id}")
        d = (time.time() - t0)*1000
        record_test("IPD Admissions List (/api/admissions/hospital/{{id}})", res_adms.status_code == 200, f"Found {len(res_adms.json())} active admissions", d)

        if adm_id:
            t0 = time.time()
            res_dis = client.patch(f"/api/admissions/{adm_id}/status", json={
                "status": "DISCHARGED",
                "discharge_summary": "Recovered smoothly during audit test",
                "discharge_date": datetime.now().strftime("%Y-%m-%d %H:%M")
            })
            d = (time.time() - t0)*1000
            record_test("IPD Patient Discharge (/api/admissions/{{id}}/status)", res_dis.status_code == 200, f"Discharge status: {res_dis.json().get('status')}", d)

# Clean up audit test records from MongoDB
import pymongo
try:
    mongo_url = os.getenv('MONGODB_URL')
    if mongo_url:
        c = pymongo.MongoClient(mongo_url)
        db = c[os.getenv('MONGODB_DB_NAME', 'careseva')]
        db['patients'].delete_many({'phone': {'$in': [test_phone, "9112223334", "9991112223"]}})
        db['appointments'].delete_many({'patient_phone': {'$in': [test_phone, "9112223334", "9991112223"]}})
        db['admissions'].delete_many({'patient_phone': {'$in': [test_phone, "9112223334", "9991112223"]}})
        print("\n[INFO] Cleaned up audit artifacts from database.")
except Exception as e:
    print(f"\n[WARN] Cleanup exception: {e}")

print("\n" + "="*80)
print(f"AUDIT SUMMARY: {len(results['passed'])} PASSED | {len(results['failed'])} FAILED")
print("="*80 + "\n")
