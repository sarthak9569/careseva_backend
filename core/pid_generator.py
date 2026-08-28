async def generate_unique_pid(db) -> str:
    """
    Atomically generates a sequential unique Patient ID (PID)
    Formatted as CS-P-10001, CS-P-10002, etc.
    """
    counter = await db["counters"].find_one_and_update(
        {"_id": "patient_pid"},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=True
    )
    # Start sequence from 10001 if new counter
    seq = counter.get("seq", 1)
    if seq < 10001:
        # Initialize counter to 10001
        await db["counters"].update_one(
            {"_id": "patient_pid"},
            {"$set": {"seq": 10001}}
        )
        seq = 10001
        
    return f"CS-P-{seq}"
