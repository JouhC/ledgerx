from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List, Literal, Dict
from core.config import settings
from jobs.fetch_bills_job import run_fetch_all
from datetime import datetime, timezone
from db.database import db_all
from services.progress import PROGRESS

router = APIRouter(prefix=settings.API_PREFIX, tags=["tasks"])

class FetchResponse(BaseModel):
    added: int

@router.get("/{task_id}")
async def get_task_status(task_id: str):
    return PROGRESS.get(task_id, {"status": "Not Found", "progress": 0})
    
