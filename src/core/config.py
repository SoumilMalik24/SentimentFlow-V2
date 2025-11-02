import json
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Any
from pydantic import field_validator, Field
import os

class Settings(BaseSettings):
    # Load from .env file
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    DB_URL: str = Field(..., description="Database connection URL")
    NEWS_API_KEYS: List[str] = Field(..., description="List of News API keys")
    HF_TOKEN: str | None = Field(None, description="Hugging Face API token (optional)")
    LOG_DIR: str = Field(default="logs", description="Directory for logs")
    
    # This will now load "Soumil24/zero-shot-startup-sentiment-v2" from your .env
    MODEL_PATH: str = Field(..., description="Hugging Face Model ID")
    
    @field_validator("NEWS_API_KEYS", mode='before')
    @classmethod
    def parse_json_string(cls, v: Any) -> Any:
        if isinstance(v, str):
            try:
                # This will parse the string "[...]" into a Python list
                return json.loads(v)
            except json.JSONDecodeError:
                # Fallback for comma-separated, just in case
                return [key.strip() for key in v.split(',') if key.strip()]
        return v

settings = Settings()

# Ensure log directory exists
os.makedirs(settings.LOG_DIR, exist_ok=True)