from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List, Literal, Dict
from core.config import settings
from jobs.fetch_bills_job import run_fetch_all
from datetime import datetime, timezone
from db.database import db_all
from services.progress import PROGRESS

router = APIRouter(prefix=settings.API_PREFIX, tags=["bills"])

class BillIn(BaseModel):
    vendor: str
    due_date: datetime
    amount: float
    currency: str = "PHP"
    pdf_path: str
    source_email_id: Optional[str] = None

class FetchResponse(BaseModel):
    added: int

@router.get("/fetch_bills")
def get_bills():
    run_fetch_all()

    response = {
        "status": "Completed",
        "bills": db_all()
    }

    return response
    
