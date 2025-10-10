from __future__ import annotations

import json
from pathlib import Path
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # --- config for pydantic-settings v2 ---
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",            # ignore env vars you didn't model
    )

    # --- fields ---
    CREDENTIALS_DESKTOP_OAUTH: str
    CREDENTIALS_DESKTOP_TOKEN: str

    DB_PATH: Path
    TEMP_ATTACHED_DIR: Path
    DEFAULT_SOURCES_PATH: Path

    API_PREFIX: str = "/api/v1"

    # --- computed helpers ---
    @property
    def credentials_desktop_oauth(self) -> dict:
        return json.loads(self.CREDENTIALS_DESKTOP_OAUTH)

    @property
    def credentials_desktop_token(self) -> dict:
        return json.loads(self.CREDENTIALS_DESKTOP_TOKEN)

    # normalize to absolute paths; accept str or Path
    @field_validator("DB_PATH", "TEMP_ATTACHED_DIR", "DEFAULT_SOURCES_PATH", mode="before")
    @classmethod
    def ensure_absolute(cls, v):
        return Path(v).resolve()

settings = Settings()