from pydantic import BaseSettings, Field
from typing import List
import os

class Settings(BaseSettings):
    DB_URL: str = Field(..., description="Database connection URL")
    NEWS_API_KEYS: List[str] = Field(..., description="List of News API keys")
    HF_TOKEN: str = Field(..., description="Hugging Face API token")
    LOG_DIR: str = Field(default="logs", description="Directory for logs")
    MODEL_PATH: str = Field(default="src/sentiments/finbert_model", description="Path to model directory")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
    
settings = Settings()

os.makedirs(settings.LOG_DIR, exist_ok=True)