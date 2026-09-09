from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "CareSeva Backend API"
    MONGODB_URL: str = "mongodb://localhost:27017"
    MONGODB_DB_NAME: str = "careseva"

    # Cashfree Payment Gateway Settings
    CASHFREE_APP_ID: str = ""
    CASHFREE_SECRET_KEY: str = ""
    CASHFREE_ENV: str = "production"
    CASHFREE_API_VERSION: str = "2023-08-01"

    # Cashfree Payouts Settings
    CASHFREE_PAYOUT_CLIENT_ID: str = ""
    CASHFREE_PAYOUT_CLIENT_SECRET: str = ""
    CASHFREE_PAYOUT_ENV: str = "production"
    
    # Platform Commission Fee (0% for now - 100% goes to hospital)
    PLATFORM_FEE_PERCENTAGE: float = 0.0
    PLATFORM_FEE_FLAT: float = 0.0

    class Config:
        import os
        env_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
        extra = "allow"

settings = Settings()

