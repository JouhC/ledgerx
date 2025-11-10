from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List, Literal, Dict
from core.config import settings
from jobs.fetch_bills_job import run_fetch_all
from datetime import datetime, timezone
from db.database import db_all, db_mark_paid

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

class PayResult(BaseModel):
    bill_id: str
    status: str

@router.get("/fetch_bills")
def fetch_bills():
    try:
        run_fetch_all()
        response = {
            "status": "Success",
            "message": "Successfully fetched bills!"
        }
    except Exception as e:
        response = {
            "status": "Failed",
            "message": e
        }
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        return response

@router.get("/get_bills")
def get_bills():
    try:
        bills = db_all()
        response = {
            "status": "Success",
            "bills": bills
        }
    except Exception as e:
        response = {
            "status": "Failed",
            "message": "Failed to retrieve bills."
        }
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        return response
    
@router.post("/{bill_id}/pay")
def pay_bill(bill_id: str):
    try:
        mark_paid = db_mark_paid(bill_id)
        response = PayResult(bill_id=bill_id, status="paid")
    except Exception as e:
        response = PayResult(bill_id=bill_id, status="failed")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        return response
    
