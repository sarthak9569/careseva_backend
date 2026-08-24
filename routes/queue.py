from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from typing import List, Dict
from models.queue import QueueCreate, QueueResponse, QueueInDB, QueueEntryCreate, QueueEntryResponse, QueueEntryInDB
from database import get_db
from bson import ObjectId
from datetime import datetime
import json

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
            # We mostly just push data from server, but client could send pings
    except WebSocketDisconnect:
        manager.disconnect(websocket, doctor_id)

@router.post("/join", response_model=QueueEntryResponse)
async def join_queue(entry: QueueEntryCreate, db = Depends(get_db)):
    # Get or create the queue for this doctor today
    # For simplicity, we just use one active queue per doctor
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
        {"$set": {"current_token": new_token, "updated_at": datetime.utcnow()}}
    )
    
    # Update entry status
    await db["queue_entries"].update_one(
        {"queue_id": str(queue["_id"]), "token_number": new_token},
        {"$set": {"status": "CALLED", "updated_at": datetime.utcnow()}}
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
