
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

def upload_pdf(local_path: str, folder_id: str, filename: str) -> str:
    svc = build_drive_service()
    file_metadata = {"name": filename, "parents": [folder_id]}
    media = MediaFileUpload(local_path, mimetype="application/pdf", resumable=True)
    f = svc.files().create(body=file_metadata, media_body=media, fields="id").execute()
    return f["id"]