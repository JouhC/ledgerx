from typing import Any, Dict
from db.database import update_bill_source_folder_id
from integrations.gdrive_service import build_drive_service
from googleapiclient.http import MediaFileUpload
import asyncio
import time

from googleapiclient.errors import HttpError

import logging

logger = logging.getLogger(__name__)

# ---------- CONFIG ----------
DRIVE_MAX_RETRIES = 3
DRIVE_CONCURRENCY = 1


# ---------- HELPERS ----------
def _escape_drive_query_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _is_retryable_error(exc: Exception) -> bool:
    if isinstance(exc, HttpError):
        try:
            status = exc.resp.status
            return status in {429, 500, 502, 503, 504}
        except Exception:
            return False

    msg = str(exc).lower()
    retry_signals = [
        "timed out",
        "timeout",
        "temporarily unavailable",
        "connection reset",
        "connection aborted",
        "broken pipe",
        "503",
        "502",
        "504",
        "429",
    ]
    return any(signal in msg for signal in retry_signals)


# ---------- CORE SYNC DRIVE OP ----------
def get_or_create_folder_sync(svc, name: str, parent_id: str | None = None) -> str:
    safe_name = _escape_drive_query_value(name)

    query = (
        f"name='{safe_name}' "
        "and mimeType='application/vnd.google-apps.folder' "
        "and trashed=false"
    )

    if parent_id:
        query += f" and '{parent_id}' in parents"

    last_err = None

    for attempt in range(1, DRIVE_MAX_RETRIES + 1):
        try:
            #logging.info(f"Attempt {attempt}: Searching for folder with query: {query}")
            results = svc.files().list(
                q=query,
                spaces="drive",
                fields="files(id, name)",
                pageSize=1
            ).execute()

            folders = results.get("files", [])
            if folders:
                return folders[0]["id"]

            file_metadata = {
                "name": name,
                "mimeType": "application/vnd.google-apps.folder",
            }

            if parent_id:
                file_metadata["parents"] = [parent_id]

            folder = svc.files().create(
                body=file_metadata,
                fields="id"
            ).execute()

            return folder["id"]

        except Exception as e:
            last_err = e

            if attempt == DRIVE_MAX_RETRIES or not _is_retryable_error(e):
                raise

            sleep_seconds = 2 ** (attempt - 1)
            time.sleep(sleep_seconds)

    raise last_err


# ---------- ASYNC WRAPPERS ----------
async def get_or_create_folder(
    svc,
    name: str,
    parent_id: str | None = None
) -> str:
    return await asyncio.to_thread(get_or_create_folder_sync, svc, name, parent_id)


async def get_or_create_folder_limited(
    sem: asyncio.Semaphore,
    svc,
    name: str,
    parent_id: str | None = None
) -> str:
    async with sem:
        return await get_or_create_folder(svc, name, parent_id)


async def update_bill_source_folder_id_async(source_id: Any, folder_id: str) -> None:
    await asyncio.to_thread(update_bill_source_folder_id, source_id, folder_id)


# ---------- MAIN ----------
async def create_folder_structure(sources: list[dict[str, Any]]) -> dict:
    if not sources:
        svc = await asyncio.to_thread(build_drive_service)
        main_folder_id = await get_or_create_folder(svc, "LedgerX")
        return {
            "main_folder_id": main_folder_id,
            "subfolders": {}
        }

    svc = await asyncio.to_thread(build_drive_service)

    # Step 1: get/create main folder
    main_folder_id = await get_or_create_folder(svc, "LedgerX")

    # Step 2: collect source ids + names
    folder_names = [
        (source["id"], source["name"])
        for source in sources
    ]

    # Step 3: create/get subfolders with limited concurrency
    sem = asyncio.Semaphore(DRIVE_CONCURRENCY)

    subfolder_ids = await asyncio.gather(*[
        get_or_create_folder_limited(sem, svc, name, parent_id=main_folder_id)
        for _, name in folder_names
    ])

    # Step 4: update DB concurrently
    await asyncio.gather(*[
        update_bill_source_folder_id_async(source_id, folder_id)
        for (source_id, _), folder_id in zip(folder_names, subfolder_ids)
    ])

    # Step 5: return desired output
    return {
        "main_folder_id": main_folder_id,
        "subfolders": dict(zip(
            [name for _, name in folder_names],
            subfolder_ids
        ))
    }


async def upload_pdf(local_path: str, folder_id: str, filename: str) -> str:
    svc = await asyncio.to_thread(build_drive_service)

    file_metadata = {
        "name": filename,
        "parents": [folder_id],
    }

    media = MediaFileUpload(
        local_path,
        mimetype="application/pdf",
        resumable=True,
    )

    def _upload():
        logger.info("Uploading PDF '%s' to folder %s", filename, folder_id)

        request = svc.files().create(
            body=file_metadata,
            media_body=media,
            fields="id",
        )
        logger.info("Create request type: %s", type(request))

        response = request.execute()
        logger.info("Upload response type: %s", type(response))
        logger.info("Uploaded file id: %s", response["id"])

        return response["id"]

    return await asyncio.to_thread(_upload)