import json
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Paste the full Google JSON into .env like: GOOGLE_AUTH={...}
    GOOGLE_AUTH: str

    # Where to send the user AFTER callback (your Streamlit app)
    FRONTEND_URL: str = "http://localhost:8501"

    class Config:
        env_file = ".env"
        case_sensitive = True

    @property
    def google_client_config(self) -> dict:
        return json.loads(self.GOOGLE_AUTH)

settings = Settings()
