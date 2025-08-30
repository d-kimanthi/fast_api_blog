import os

from dotenv import load_dotenv
from pydantic import BaseModel

# Load environment variables from .env file
load_dotenv()

class Settings(BaseModel):
    DATABASE_URL: str = os.getenv("DATABASE_URL", "please-provide-db-url")
    SECRET_KEY: str = os.getenv("SECRET_KEY", "please-provide-secret-key")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(
        os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60")
    )
    ALGORITHM: str = os.getenv("ALGORITHM", "HS256")


settings = Settings()
