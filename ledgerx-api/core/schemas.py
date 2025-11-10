from pydantic import BaseModel, Field
from typing import Optional, Literal, Any

TaskStatus = Literal["pending", "running", "done", "error", "cancelled"]

class TaskProgress(BaseModel):
    task_id: str = Field(..., example="import:customer-123")
    status: TaskStatus
    progress: float = Field(0.0, ge=0.0, le=100.0)
    result: Optional[Any] = None
    error: Optional[str] = None
    message: Optional[str] = None
