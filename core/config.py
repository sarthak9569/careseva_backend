from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "CareSeva Backend API"
    MONGODB_URL: str = "mongodb://localhost:27017"
    MONGODB_DB_NAME: str = "careseva"

    # Cashfree Payment Gateway Settings
    CASHFREE_APP_ID: str = "TEST_CASHFREE_APP_ID"
    CASHFREE_SECRET_KEY: str = "TEST_CASHFREE_SECRET_KEY"
    CASHFREE_ENV: str = "SANDBOX"  # "SANDBOX" or "PRODUCTION"
    CASHFREE_API_VERSION: str = "2023-08-01"

    class Config:
        import os
        env_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
        extra = "allow"

settings = Settings()
