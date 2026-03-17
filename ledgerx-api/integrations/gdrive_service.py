
from core.config import settings
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from typing import Any

def build_drive_service() -> Any:
    """Drive API service using stored token."""
    creds = None
    if settings.credentials_desktop_token:
        creds = Credentials.from_authorized_user_info(settings.credentials_desktop_token)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            raise Exception("No valid credentials available. Please set CREDENTIALS_DESKTOP_TOKEN in your .env file.")
    return build("drive", "v3", credentials=creds)


def list_files_in_folder(folder_id: str) -> list[dict]:
    svc = build_drive_service()
    query = f"'{folder_id}' in parents and trashed=false"
    results = svc.files().list(q=query, fields="files(id, name)").execute()
    return results.get("files", [])