from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List, Literal, Dict

class ReminderRules(BaseModel):
    offset_days: List[int] = [-7, -3, 0]
    send_hour_local: int = 9
    channel: Literal["email"] = "email"

class ReminderReq(BaseModel):
    scope: Literal["month","bill"]
    month: Optional[str] = None
    bill_id: Optional[str] = None
    rules: Optional[ReminderRules] = None
    schedule_at: Optional[str] = None

router = APIRouter(prefix="/reminders", tags=["reminders"])

@router.post("/api/v1/reminders")
def set_reminders(payload: ReminderReq, user = Depends(auth_user)):
    return {"scheduled": 0, "skipped": 0, "details": []}
