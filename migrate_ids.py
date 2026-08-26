import asyncio
import os
import random
import string
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
from dotenv import load_dotenv

load_dotenv()

# For running locally in backend folder
MONGO_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
client = AsyncIOMotorClient(MONGO_URL)
db = client["careseva"]

def generate_hop_id():
    return f"CARE-{''.join(random.choices(string.digits, k=4))}"

async def generate_doc_id(department_id: str, hospital_id: str):
    # Fetch department to get initials
    dept = await db["departments"].find_one({"_id": ObjectId(department_id)})
    dept_name = dept["name"] if dept else "GEN"
    
    # Simple initials: first 3-6 letters capitalized
    initials = "".join([c for c in dept_name if c.isalpha()]).upper()[:6]
    if not initials:
        initials = "DOC"
        
    # Count how many doctors already have doc_ids starting with these initials in this hospital
    regex = f"^{initials}[0-9]+$"
    count = await db["doctors"].count_documents({"hospital_id": hospital_id, "doc_id": {"$regex": regex}})
    
    return f"{initials}{count + 1:02d}"

async def run_migration():
    print("Starting ID Migration...")
    
    # 1. Migrate Hospitals
    hospitals = await db["hospitals"].find({"hop_id": {"$exists": False}}).to_list(length=1000)
    for h in hospitals:
        hop_id = generate_hop_id()
        # Ensure hop_id is unique
        while await db["hospitals"].find_one({"hop_id": hop_id}):
            hop_id = generate_hop_id()
            
        await db["hospitals"].update_one({"_id": h["_id"]}, {"$set": {"hop_id": hop_id}})
        print(f"Migrated Hospital {h['name']} -> {hop_id}")
        
    # 2. Migrate Doctors
    doctors = await db["doctors"].find({"doc_id": {"$exists": False}}).to_list(length=10000)
    for d in doctors:
        doc_id = await generate_doc_id(d.get("department_id"), d.get("hospital_id"))
        await db["doctors"].update_one({"_id": d["_id"]}, {"$set": {"doc_id": doc_id}})
        print(f"Migrated Doctor {d['name']} -> {doc_id}")
        
    print("Migration complete!")

if __name__ == "__main__":
    asyncio.run(run_migration())
