from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from core.config import settings
from database import connect_to_mongo, close_mongo_connection, get_db

app = FastAPI(title=settings.PROJECT_NAME)

# Configure CORS for Flutter frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
