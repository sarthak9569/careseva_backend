from motor.motor_asyncio import AsyncIOMotorClient
from core.config import settings

class Database:
    client: AsyncIOMotorClient = None
    db = None

db_manager = Database()

async def connect_to_mongo():
    db_manager.client = AsyncIOMotorClient(settings.MONGODB_URL)
    db_manager.db = db_manager.client[settings.MONGODB_DB_NAME]
    print(f"Connected to MongoDB at {settings.MONGODB_URL}")

async def close_mongo_connection():
    if db_manager.client:
        db_manager.client.close()
        print("Closed MongoDB connection")

def get_db():
    return db_manager.db
