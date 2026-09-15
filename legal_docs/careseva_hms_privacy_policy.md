# CareSeva HMS Privacy & Data Processing Notice

**Effective Date:** September 15, 2026  
**Version:** 1.0  
**Compliance Framework:** Digital Personal Data Protection (DPDP) Act, 2023 (India)  
**Provider:** Softkrest Infotech (Sole Proprietorship owned by Mr. Sarthak Srivastava)  
**MSME Udyam Registration No:** UDYAM-UP-75-0200308  
**Trademark:** CARESEVA™ (Class 42, App No: 14991641)  

---

## 1. Regulatory Roles: Data Processor vs. Data Fiduciary
Under the Indian Digital Personal Data Protection (DPDP) Act 2023:
* **Healthcare Partner (Hospital):** Acts as the **Data Fiduciary** for patient records created directly during walk-in clinical consultations and hospital OPD registrations.
* **Softkrest Infotech:** Acts as the **Data Processor** providing cloud infrastructure, database hosting, OPD queue automation, and software services on behalf of the hospital.

For patients registered directly via the CareSeva Mobile Application, Softkrest Infotech acts as the Data Fiduciary for user authentication and platform account management.

---

## 2. Categories of Data Processed in HMS
CareSeva HMS processes the following categories of operational and health data:
1. **Hospital Organizational Data:** Hospital name, accreditation, address, contact details, department lists, and consultation fee structures.
2. **Staff Credentials:** Doctor and staff names, medical registration numbers, phone numbers, role permissions, and access credentials.
3. **Clinical & Queue Records:** Patient walk-in records, assigned token numbers, OPD queue status, doctor consultation logs, and IPD admission/discharge records.
4. **Audit Logs:** System activity records including login timestamps, record creation, token call events, and updates.

---

## 3. Multi-Tenant Database Security & Data Isolation
* **Hospital Data Isolation:** CareSeva HMS is built on a multi-tenant cloud architecture. All database queries and API endpoints strictly filter data by `hospital_id`.
* **Zero Cross-Hospital Leakage:** Staff at Hospital A have no technical or database visibility into patient records, doctor queues, or analytics of Hospital B.

---

## 4. Audit Logging & Security Standards
* **Action Tracking:** CareSeva HMS records server-side audit logs for sensitive operations (e.g., token calls, doctor queue completion, patient registration, IPD status changes).
* **Encryption Standards:** Data in transit is protected using **TLS 1.3 / HTTPS** encryption. Data at rest is encrypted in secure MongoDB Atlas cloud instances.

---

## 5. Data Retention, Backup & Contract Termination
* **Retention During Active Subscription:** Hospital operational data is retained throughout the active license period.
* **Data Export Upon Termination:** Upon contract termination or written request, Softkrest Infotech provides the hospital with a structured data export (JSON/CSV) of its patient records and clinical logs.
* **Post-Termination Deletion:** Following contract completion and grace period export, hospital operational records are purged from active production servers, subject to legal record-keeping requirements.

---

## 6. Security Contact & Incident Response
To report security concerns or data processing inquiries regarding CareSeva HMS:

* **Security & Data Lead:** Mr. Sarthak Srivastava
* **Entity:** Softkrest Infotech
* **Email:** softkrestinfotech@gmail.com
* **Phone:** +91 9369309644
* **Address:** Varanasi, Uttar Pradesh, India
