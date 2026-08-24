from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from core.config import settings
from database import connect_to_mongo, close_mongo_connection, get_db
from routes import auth, hospitals, admin, hospital_management, queue, appointments

app = FastAPI(title=settings.PROJECT_NAME)

# Configure CORS for Flutter frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(hospitals.router, prefix="/api/hospitals", tags=["hospitals"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
app.include_router(hospital_management.router, prefix="/api/management", tags=["hospital_management"])
app.include_router(queue.router, prefix="/api/queue", tags=["queue"])
app.include_router(appointments.router, prefix="/api/appointments", tags=["appointments"])

@app.on_event("startup")
async def startup_db_client():
    await connect_to_mongo()

@app.on_event("shutdown")
async def shutdown_db_client():
    await close_mongo_connection()

@app.get("/")
async def root():
    return {"message": "Welcome to CareSeva Backend API!"}

@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.get("/test-db")
async def test_db(db = Depends(get_db)):
    try:
        # A simple query to check the DB connection
        collections = await db.list_collection_names()
        return {"status": "success", "collections": collections}
    except Exception as e:
        return {"status": "error", "message": str(e)}
