from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List, Literal, Dict
from core.config import settings

router = APIRouter(prefix=settings.API_PREFIX, tags=["reminders"])

@router.get("bills")
def get_bills(
    month: str = Query(..., description="YYYY-MM"),
    span: int = 1,
    status: Optional[str] = None,
    vendor: Optional[str] = None,
    min_amount: Optional[float] = None,
    max_amount: Optional[float] = None,
    user = Depends(auth_user),
):
    return { "range": {"start_month": month, "end_month": month}, "items": [], "totals": {"count":0, "amount_due":0.0, "by_month": []} }
