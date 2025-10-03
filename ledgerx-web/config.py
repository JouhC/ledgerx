# config.py
from typing import Any, Dict, Tuple
from pydantic_settings import BaseSettings
import streamlit as st


def st_secrets_source(_: type[BaseSettings]) -> Dict[str, Any]:
    """
    Custom source for Pydantic that loads values from st.secrets.
    Falls back to {} if no secrets are defined.
    """
    try:
        return dict(st.secrets)
    except Exception:
        return {}


class Settings(BaseSettings):
    API_PREFIX: str = "/api/v1"
    API_URL: str = "http://localhost:8000"
    GOOGLE_OAUTH: Dict[str, Any] = {}
    DB_USER: str | None = None
    DB_PASSWORD: str | None = None
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432

    class Config:
        # priority: init args > st.secrets > env vars
        @classmethod
        def customise_sources(
            cls,
            init_settings,
            env_settings,
            file_secret_settings,
        ) -> Tuple[Any, ...]:
            return (
                init_settings,
                st_secrets_source,   # <-- our Streamlit secrets source
                env_settings,        # fallback to real env vars
                file_secret_settings,
            )


settings = Settings()