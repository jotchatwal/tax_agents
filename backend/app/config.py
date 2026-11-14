import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

# Base project path
BASE_DIR = Path(__file__).resolve().parent.parent.parent

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # MongoDB Atlas Settings
    MONGODB_URI: str = "mongodb+srv://cluster0.ofim2w.mongodb.net/taxpilot_db?authSource=%24external&authMechanism=MONGODB-X509"
    MONGODB_DATABASE: str = "taxpilot_db"
    MONGODB_CERT_PATH: str = str(BASE_DIR / "X509-cert-1105780303199716876.pem")

    # LLM Settings
    LLM_PROVIDER: str = "gemini"  # gemini, openai, anthropic, mock
    LLM_API_KEY: str = ""
    LLM_MODEL: str = "gemini-1.5-flash"

    # Embedding Settings
    EMBEDDING_PROVIDER: str = "local"  # local (sentence-transformers), gemini, voyage, openai
    EMBEDDING_API_KEY: str = ""
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
    EMBEDDING_DIMENSIONS: int = 384

    # Security & App Settings
    APP_SECRET_KEY: str = "taxpilot-hackathon-2026-secret-governed-memory-key"
    FRONTEND_ORIGIN: str = "http://localhost:8000"
    ENVIRONMENT: str = "development"

settings = Settings()
