import os
from pydantic import BaseModel

class Settings(BaseModel):
    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-secret")
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/app.db")
    ADMIN_USER: str = os.getenv("ADMIN_USER", "admin")
    ADMIN_PASS: str = os.getenv("ADMIN_PASS", "Trocar@123")
    ALLOWED_ORIGINS: str = os.getenv("ALLOWED_ORIGINS", "*")

settings = Settings()
