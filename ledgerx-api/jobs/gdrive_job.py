from integrations.gdrive_service import build_drive_service
from googleapiclient.http import MediaFileUpload
import asyncio

def get_or_create_folder_sync(svc, name: str, parent_id: str | None = None) -> str:
    query = f"name='{name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"

    if parent_id:
        query += f" and '{parent_id}' in parents"

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


async def get_or_create_folder(svc, name: str, parent_id: str | None = None) -> str:
    return await asyncio.to_thread(get_or_create_folder_sync, svc, name, parent_id)


async def create_folder_structure(folder_names: list[str]):
    svc = await asyncio.to_thread(build_drive_service)

    # create/get main folder first
    main_folder_id = await get_or_create_folder(svc, "LedgerX")

    # create/get subfolders concurrently
    tasks = [
        get_or_create_folder(svc, name, parent_id=main_folder_id)
        for name in folder_names
    ]
    subfolder_ids = await asyncio.gather(*tasks)

    return {
        "main_folder_id": main_folder_id,
        "subfolders": dict(zip(folder_names, subfolder_ids))
    }


async def upload_pdf(local_path: str, folder_id: str, filename: str) -> str:
    svc = await asyncio.to_thread(build_drive_service)
    file_metadata = {"name": filename, "parents": [folder_id]}
    media = MediaFileUpload(local_path, mimetype="application/pdf", resumable=True)
    f = await asyncio.to_thread(svc.files().create, body=file_metadata, media_body=media, fields="id")
    return f["id"]