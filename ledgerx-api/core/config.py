from pathlib import Path
from pydantic import field_validator
from pydantic_settings import BaseSettings
import json

class Settings(BaseSettings):
    CREDENTIALS_DESKTOP_OAUTH: str
    CREDENTIALS_DESKTOP_TOKEN: str
    DB_PATH: str
    TEMP_ATTACHED_DIR: str
    DEFAULT_SOURCES_PATH: str
    API_PREFIX: str = "/api/v1"

    class Config:
        env_file = ".env"
        case_sensitive = True
    
    @property
    def credentials_desktop_oauth(self) -> dict:
        return json.loads(self.CREDENTIALS_DESKTOP_OAUTH)  
    
    @property
    def credentials_desktop_token(self) -> dict:
        return json.loads(self.CREDENTIALS_DESKTOP_TOKEN)
    
    @field_validator("DB_PATH")
    def ensure_absolute(cls, v: Path) -> Path:
        return v.resolve()
    
    @field_validator("TEMP_ATTACHED_DIR")
    def ensure_absolute(cls, v: Path) -> Path:
        return v.resolve()
    
    @field_validator("DEFAULT_SOURCES_PATH")
    def ensure_absolute(cls, v: Path) -> Path:
        return v.resolve()

settings = Settings()
