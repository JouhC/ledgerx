from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field, EmailStr
from typing import Literal, Optional
from core.config import settings
from db.database import add_bill_source

class BillSourcePayload(BaseModel):
    name: str = Field(..., description="The name of the bill source, e.g. 'Meralco'.")
    provider: Literal["gmail", "drive", "api", "manual"] = Field(..., description="Source provider type.")
    gmail_query: Optional[str] = Field(None, description="Gmail search query string to locate the e-bills.")
    sender_email: Optional[EmailStr] = Field(None, description="Expected sender email address.")
    subject_like: Optional[str] = Field(None, description="Subject filter keyword for incoming emails.")
    include_kw: Optional[str] = Field(None, description="Comma-separated keywords to include in filtering.")
    exclude_kw: Optional[str] = Field(None, description="Comma-separated keywords to exclude from filtering.")
    drive_folder_id: Optional[str] = Field(None, description="Google Drive folder ID to store or fetch related files.")
    file_pattern: Optional[str] = Field(None, description="Filename pattern used when saving bills (supports placeholders like {month} and {year}).")
    currency: str = Field(..., description="Currency code, e.g., 'PHP'.")
    password_env: Optional[str] = Field(None, description="Environment variable name for password-protected PDFs, or 'None'.")
    category: Literal["utilities", "credit_card", "subscriptions", "loans", "others"] = Field(..., description="Bill category classification.")

class AddSourceResult(BaseModel):
    bill_id: str
    status: str

router = APIRouter(prefix=f"{settings.API_PREFIX}/bill_sources", tags=["bill_sources"])

@router.post("/add", response_model=AddSourceResult)
def add_bill_source_endpoint(payload: BillSourcePayload):
    try:
        add_bill_source(payload.model_dump())
        response = AddSourceResult(bill_id=payload.name, status="added")
    except Exception as e:
        response = AddSourceResult(bill_id=payload.name, status="failed")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        return response