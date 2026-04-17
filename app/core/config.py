from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import List
import secrets


class Settings(BaseSettings):
    APP_NAME: str = "URL Shortener"
    APP_ENV: str = "development"
    BASE_URL: str = "http://localhost:8001"
    FRONTEND_URL: str = "http://localhost:5173"

    DATABASE_URL: str = "postgresql+asyncpg://postgres:password@localhost:5434/urlshortener"
    REDIS_URL: str = "redis://localhost:6379/0"

    # AUDIT FIX: SECRET_KEY must never be auto-generated silently in production.
    # Production environments MUST set this via environment variables or .env
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    RESET_TOKEN_EXPIRE_MINUTES: int = 30

    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str
    SMTP_PASSWORD: str
    EMAILS_FROM_EMAIL: str
    EMAILS_FROM_NAME: str = "URL Shortener"

    SHORT_CODE_LENGTH: int = 6

    RATE_LIMIT_AUTH: str = "10/minute"
    RATE_LIMIT_CREATE_URL: str = "30/minute"
    RATE_LIMIT_REDIRECT: str = "120/minute"
    RATE_LIMIT_PLATFORM_READ: str = "60/minute"
    RATE_LIMIT_PLATFORM_WRITE: str = "10/minute"

    MAX_REQUEST_BODY_SIZE: int = 1_048_576  # 1MB
    DB_QUERY_TIMEOUT: int = 10

    # Per-user totals (across all projects)
    MAX_LINKS_PER_USER: int = 1000
    MAX_PROJECTS_PER_USER: int = 50
    # Per-project cap
    MAX_LINKS_PER_PROJECT: int = 500
    # Audit log retention
    AUDIT_LOG_RETENTION_DAYS: int = 365
    
    # AI Feature
    GROQ_API_KEY: str

    # Langsmith Tracing (requires LANGCHAIN_ prefix)
    LANGCHAIN_TRACING_V2: bool = True
    LANGCHAIN_ENDPOINT: str = "https://api.smith.langchain.com"
    LANGCHAIN_API_KEY: str
    LANGCHAIN_PROJECT: str = "LinkVault_AI_Agent"



    @field_validator("SECRET_KEY")
    @classmethod
    def warn_weak_secret(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters")
        return v

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def allowed_origins(self) -> List[str]:
        origins = [self.FRONTEND_URL, self.BASE_URL]
        if not self.is_production:
            origins.extend([
                "http://localhost:5173", "http://127.0.0.1:5173",
                "http://localhost:5174", "http://localhost:3000"
            ])
        return origins

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"
        


settings = Settings()
