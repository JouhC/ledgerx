from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    API_PREFIX: str = "/api/v1"

    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()

print(settings)