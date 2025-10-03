from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List, Literal, Dict
from core.config import settings

router = APIRouter(prefix=settings.API_PREFIX, tags=["health"])

@router.get("/healthz")
def healthz():
    return {"ok": True}