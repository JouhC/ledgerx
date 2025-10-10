from core.config import settings
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import base64
import os
import re
from typing import Any

def build_gmail_service() -> Any:
    """Gmail API service using stored token."""
    creds = None
    if settings.credentials_desktop_token:
        creds = Credentials.from_authorized_user_info(settings.credentials_desktop_token)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            raise Exception("No valid credentials available. Please set CREDENTIALS_DESKTOP_TOKEN in your .env file.")
    return build("gmail", "v3", credentials=creds)

def list_messages(service, query, max_results=100):
    resp = service.users().messages().list(userId="me", q=query, maxResults=max_results).execute()
    return resp.get("messages", [])

def get_message(service, msg_id):
    return service.users().messages().get(userId="me", id=msg_id, format="full").execute()

def iter_pdf_attachments(msg):
    """Yield (filename, attachmentId) for PDF attachments found in message parts."""
    payload = msg.get("payload", {}) or {}
    stack = [payload]
    while stack:
        part = stack.pop()
        # push nested parts
        for sub in part.get("parts", []) or []:
            stack.append(sub)
        # check current part for attachment
        filename = part.get("filename") or ""
        body = part.get("body") or {}
        if filename and "attachmentId" in body and filename.lower().endswith(".pdf"):
            yield filename, body["attachmentId"]

def download_attachment(service, msg_id, attachment_id, filename):
    att = service.users().messages().attachments().get(
        userId="me", messageId=msg_id, id=attachment_id
    ).execute()
    data = att.get("data")
    if not data:
        return None
    file_bytes = base64.urlsafe_b64decode(data.encode("utf-8"))
    safe = re.sub(r'[\\/:*?"<>|]+', "_", filename) or f"{msg_id}.pdf"
    path = os.path.join(settings.TEMP_ATTACHED_DIR, safe)
    with open(path, "wb") as f:
        f.write(file_bytes)
    return path

def extract_bills(query):
    service = build_gmail_service()
    msgs = list_messages(service, query, max_results=100)

    saved = []
    for m in msgs:
        full = get_message(service, m["id"])
        for fname, att_id in iter_pdf_attachments(full):
            out = download_attachment(service, m["id"], att_id, fname)
            if out:
                saved.append(out)

    return saved
