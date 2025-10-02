from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    SALT: str
    DEFAULT_PLAYER: str | None = None
    DB_FILE: str
    RENDER: bool = False
    ERROR_CODES_FILE: str = "app/error_codes.json"

    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()

print(settings)