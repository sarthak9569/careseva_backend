from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from typing import List, Dict, Optional
from models.queue import QueueCreate, QueueResponse, QueueInDB, QueueEntryCreate, QueueEntryResponse, QueueEntryInDB
from database import get_db
from bson import ObjectId
from datetime import datetime, timezone, timedelta
import json

IST = timezone(timedelta(hours=5, minutes=30))

def get_ist_now() -> datetime:
    return datetime.now(IST)

router = APIRouter()

# WebSocket Connection Manager
class ConnectionManager:
    def __init__(self):
        # Maps doctor_id to a list of active websocket connections
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, doctor_id: str):
        await websocket.accept()
        if doctor_id not in self.active_connections:
            self.active_connections[doctor_id] = []
        self.active_connections[doctor_id].append(websocket)

    def disconnect(self, websocket: WebSocket, doctor_id: str):
        if doctor_id in self.active_connections:
            if websocket in self.active_connections[doctor_id]:
                self.active_connections[doctor_id].remove(websocket)
            if not self.active_connections[doctor_id]:
                del self.active_connections[doctor_id]

    async def broadcast_queue_update(self, doctor_id: str, message: dict):
        if doctor_id in self.active_connections:
            for connection in self.active_connections[doctor_id]:
                try:
                    await connection.send_text(json.dumps(message))
                except Exception:
                    pass

manager = ConnectionManager()

@router.websocket("/ws/{doctor_id}")
async def websocket_endpoint(websocket: WebSocket, doctor_id: str):
    await manager.connect(websocket, doctor_id)
    try:
        while True:
            data = await websocket.receive_text()
            if data:
                try:
                    msg = json.loads(data)
                    if msg.get("action") == "ping" or msg.get("event") == "ping":
                        await websocket.send_text(json.dumps({"event": "pong"}))
                except Exception:
                    # If raw string ping
                    if data.strip().lower() == "ping":
                        await websocket.send_text(json.dumps({"event": "pong"}))
    except (WebSocketDisconnect, Exception):
        manager.disconnect(websocket, doctor_id)

@router.post("/join", response_model=QueueEntryResponse)
async def join_queue(entry: QueueEntryCreate, db = Depends(get_db)):
    # Get or create the queue for this doctor today
    queue = await db["queues"].find_one({
        "hospital_id": entry.hospital_id,
        "doctor_id": entry.doctor_id,
        "status": "ACTIVE"
    })
    
    if not queue:
        # Create new queue
        new_queue = QueueInDB(
            id="",
            hospital_id=entry.hospital_id,
            department_id=entry.department_id,
            doctor_id=entry.doctor_id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            total_tokens=0,
            current_token=0
        )
        db_queue = new_queue.dict(exclude={"id"})
        res = await db["queues"].insert_one(db_queue)
        queue_id = str(res.inserted_id)
        token_num = 1
    else:
        queue_id = str(queue["_id"])
        token_num = queue["total_tokens"] + 1
        
    # Increment total_tokens
    await db["queues"].update_one({"_id": ObjectId(queue_id)}, {"$inc": {"total_tokens": 1}})
    
    # Create entry
    db_entry = QueueEntryInDB(
        id="",
        queue_id=queue_id,
        patient_id=entry.patient_id,
        patient_name=entry.patient_name,
        token_number=token_num,
        hospital_id=entry.hospital_id,
        department_id=entry.department_id,
        doctor_id=entry.doctor_id,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    
    entry_dict = db_entry.dict(exclude={"id"})
    res2 = await db["queue_entries"].insert_one(entry_dict)
    entry_dict["id"] = str(res2.inserted_id)
    
    # Broadcast to websocket
    await manager.broadcast_queue_update(entry.doctor_id, {
        "event": "new_patient",
        "total_tokens": token_num
    })
    
    return QueueEntryResponse(**entry_dict)

@router.get("/patient/active")
async def get_patient_active_queue(
    patient_id: Optional[str] = None,
    phone: Optional[str] = None,
    db = Depends(get_db)
):
    """Retrieve all active queue tokens and doctor room statuses for this patient across all departments."""
    conditions = []
    if patient_id and patient_id != "dummy_patient_123":
        conditions.append({"patient_id": patient_id})
    if phone:
        clean_p = phone.strip().replace(" ", "").replace("-", "")
        if clean_p.startswith("+91"):
            clean_p = clean_p[3:]
        conditions.append({"phone": clean_p})
        try:
            pt = await db["patients"].find_one({"phone": clean_p})
            if pt:
                if pt.get("pid"):
                    conditions.append({"patient_id": pt["pid"]})
                conditions.append({"patient_id": str(pt["_id"])})
        except Exception:
            pass

    query = {"status": {"$in": ["WAITING", "CALLED", "IN_PROGRESS"]}}
    if conditions:
        query["$or"] = conditions

    cursor = db["queue_entries"].find(query).sort("created_at", -1)
    entries = await cursor.to_list(length=20)
    
    # Fallback to most recent active entries if none matched specific filter
    if not entries:
        fallback_cursor = db["queue_entries"].find(
            {"status": {"$in": ["WAITING", "CALLED", "IN_PROGRESS"]}}
        ).sort("created_at", -1).limit(5)
        entries = await fallback_cursor.to_list(length=5)

    if not entries:
        return {"has_active_queue": False, "active_queues": []}

    # Build queue list with doctor and room details
    active_list = []
    for entry in entries:
        doctor_id = entry.get("doctor_id")
        queue = None
        if entry.get("queue_id"):
            try:
                queue = await db["queues"].find_one({"_id": ObjectId(entry["queue_id"])})
            except Exception:
                pass
        if not queue and doctor_id:
            queue = await db["queues"].find_one({"doctor_id": doctor_id, "status": "ACTIVE"})

        current_token = queue.get("current_token", 0) if queue else 0
        total_tokens = queue.get("total_tokens", 0) if queue else 0

        doctor = None
        if doctor_id:
            try:
                doctor = await db["doctors"].find_one({"_id": ObjectId(doctor_id)})
            except Exception:
                doctor = await db["doctors"].find_one({"_id": doctor_id})

        dept = None
        dept_id = entry.get("department_id")
        if dept_id:
            try:
                dept = await db["departments"].find_one({"_id": ObjectId(dept_id)})
            except Exception:
                pass

        doctor_name = doctor.get("name") if doctor else "Duty Doctor"
        dept_name = entry.get("department_name") or (dept.get("name") if dept else "General")

        active_list.append({
            "entry_id": str(entry["_id"]),
            "doctor_id": doctor_id,
            "doctor_name": doctor_name,
            "department_name": dept_name,
            "token_number": entry.get("token_number", 0),
            "current_token": current_token,
            "total_tokens": total_tokens,
            "status": entry.get("status", "WAITING"),
            "patient_name": entry.get("patient_name", ""),
            "appointment_id": entry.get("appointment_id")
        })

    first = active_list[0] if active_list else {}
    return {
        "has_active_queue": len(active_list) > 0,
        "active_queues": active_list,
        "entry_id": first.get("entry_id"),
        "doctor_id": first.get("doctor_id"),
        "doctor_name": first.get("doctor_name"),
        "department_name": first.get("department_name"),
        "token_number": first.get("token_number", 0),
        "current_token": first.get("current_token", 0),
        "total_tokens": first.get("total_tokens", 0),
        "status": first.get("status", "WAITING"),
        "patient_name": first.get("patient_name", "")
    }

@router.get("/{doctor_id}/entries", response_model=List[QueueEntryResponse])
async def get_queue_entries(doctor_id: str, db = Depends(get_db)):
    queue = await db["queues"].find_one({
        "doctor_id": doctor_id,
        "status": "ACTIVE"
    })
    if not queue:
        return []
        
    cursor = db["queue_entries"].find({"queue_id": str(queue["_id"])})
    entries = await cursor.to_list(length=100)
    
    result = []
    for e in entries:
        e["id"] = str(e["_id"])
        result.append(QueueEntryResponse(**e))
    return result

@router.get("/{doctor_id}/history", response_model=List[QueueEntryResponse])
async def get_patient_history(doctor_id: str, date: str = None, db = Depends(get_db)):
    from typing import Optional
    
    query = {
        "doctor_id": doctor_id,
        "status": {"$in": ["COMPLETED", "CANCELLED", "NO_SHOW"]}
    }
    
    if date:
        try:
            target_date = datetime.strptime(date, "%Y-%m-%d").date()
            start = datetime.combine(target_date, datetime.min.time())
            end = datetime.combine(target_date, datetime.max.time())
            query["updated_at"] = {"$gte": start, "$lte": end}
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
            
    # Sort by updated_at descending so most recent is first
    cursor = db["queue_entries"].find(query).sort("updated_at", -1)
    entries = await cursor.to_list(length=200)
    
    result = []
    for e in entries:
        e["id"] = str(e["_id"])
        result.append(QueueEntryResponse(**e))
    return result

@router.post("/{doctor_id}/complete")
async def complete_current_patient(doctor_id: str, db = Depends(get_db)):
    queue = await db["queues"].find_one({
        "doctor_id": doctor_id,
        "status": "ACTIVE"
    })
    if not queue:
        raise HTTPException(status_code=404, detail="Active queue not found")
        
    current_token = queue["current_token"]
    if current_token > 0:
        # Mark current token as COMPLETED
        entry = await db["queue_entries"].find_one_and_update(
            {"queue_id": str(queue["_id"]), "token_number": current_token},
            {"$set": {"status": "COMPLETED", "updated_at": get_ist_now()}}
        )
        if entry:
            if entry.get("appointment_id"):
                try:
                    await db["appointments"].update_one(
                        {"_id": ObjectId(entry["appointment_id"])},
                        {"$set": {"status": "COMPLETED", "updated_at": get_ist_now()}}
                    )
                except Exception:
                    pass
            elif entry.get("patient_id"):
                await db["appointments"].update_one(
                    {
                        "doctor_id": doctor_id,
                        "patient_id": entry["patient_id"],
                        "status": {"$in": ["BOOKED", "WAITING", "CALLED", "IN_PROGRESS"]}
                    },
                    {"$set": {"status": "COMPLETED", "updated_at": get_ist_now()}}
                )
        
    # Auto-advance to next token (as requested by user)
    new_token = current_token + 1
    
    # Only advance if we haven't exceeded total tokens
    if new_token <= queue["total_tokens"]:
        await db["queues"].update_one(
            {"_id": queue["_id"]},
            {"$set": {"current_token": new_token, "updated_at": get_ist_now()}}
        )
        
        called_entry = await db["queue_entries"].find_one_and_update(
            {"queue_id": str(queue["_id"]), "token_number": new_token},
            {"$set": {"status": "CALLED", "updated_at": get_ist_now()}}
        )
        if called_entry:
            if called_entry.get("appointment_id"):
                try:
                    await db["appointments"].update_one(
                        {"_id": ObjectId(called_entry["appointment_id"])},
                        {"$set": {"status": "IN_PROGRESS", "updated_at": get_ist_now()}}
                    )
                except Exception:
                    pass
            elif called_entry.get("patient_id"):
                await db["appointments"].update_one(
                    {
                        "doctor_id": doctor_id,
                        "patient_id": called_entry["patient_id"],
                        "status": {"$in": ["BOOKED", "WAITING"]}
                    },
                    {"$set": {"status": "IN_PROGRESS", "updated_at": get_ist_now()}}
                )
    else:
        # If no more tokens, just leave current_token as is (or reset if desired, but usually we just keep it at max)
        new_token = current_token

    # Broadcast update
    await manager.broadcast_queue_update(doctor_id, {
        "event": "queue_advanced",
        "current_token": new_token
    })
    
    return {"status": "success", "current_token": new_token}

@router.post("/{doctor_id}/next")
async def call_next_patient(doctor_id: str, db = Depends(get_db)):
    queue = await db["queues"].find_one({
        "doctor_id": doctor_id,
        "status": "ACTIVE"
    })
    if not queue:
        raise HTTPException(status_code=404, detail="Active queue not found")
        
    new_token = queue["current_token"] + 1
    
    # Update current token
    await db["queues"].update_one(
        {"_id": queue["_id"]},
        {"$set": {"current_token": new_token, "updated_at": get_ist_now()}}
    )
    
    # Update entry status
    called_entry = await db["queue_entries"].find_one_and_update(
        {"queue_id": str(queue["_id"]), "token_number": new_token},
        {"$set": {"status": "CALLED", "updated_at": get_ist_now()}}
    )
    if called_entry:
        if called_entry.get("appointment_id"):
            try:
                await db["appointments"].update_one(
                    {"_id": ObjectId(called_entry["appointment_id"])},
                    {"$set": {"status": "IN_PROGRESS", "updated_at": get_ist_now()}}
                )
            except Exception:
                pass
        elif called_entry.get("patient_id"):
            await db["appointments"].update_one(
                {
                    "doctor_id": doctor_id,
                    "patient_id": called_entry["patient_id"],
                    "status": {"$in": ["BOOKED", "WAITING"]}
                },
                {"$set": {"status": "IN_PROGRESS", "updated_at": get_ist_now()}}
            )
    
    # Broadcast update
    await manager.broadcast_queue_update(doctor_id, {
        "event": "queue_advanced",
        "current_token": new_token
    })
    
    return {"status": "success", "current_token": new_token}

@router.get("/{doctor_id}/status")
async def get_queue_status(doctor_id: str, db = Depends(get_db)):
    queue = await db["queues"].find_one({
        "doctor_id": doctor_id,
        "status": "ACTIVE"
    })
    if not queue:
        return {"status": "CLOSED", "current_token": 0, "total_tokens": 0}
        
    return {
        "status": "ACTIVE",
        "current_token": queue["current_token"],
        "total_tokens": queue["total_tokens"]
    }
