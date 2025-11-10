# progress.py
from pydantic import BaseModel, Field
from enum import Enum
from typing import Any, Optional
from datetime import datetime, timezone
import asyncio


class TaskStatus(str, Enum):
    pending = "pending"
    running = "running"
    done = "done"
    error = "error"


class TaskProgress(BaseModel):
    task_id: str = Field(..., example="import:customer-123")
    status: TaskStatus
    progress: float = Field(0.0, ge=0.0, le=100.0)
    result: Optional[Any] = None
    error: Optional[str] = None
    message: Optional[str] = None
    started_at: Optional[str] = None
    updated_at: Optional[str] = None


class ProgressTracker:
    def __init__(self):
        self._lock = asyncio.Lock()
        self._tasks: dict[str, TaskProgress] = {}

    async def start(self, task_id: str, message: str = None):
        async with self._lock:
            self._tasks[task_id] = TaskProgress(
                task_id=task_id,
                status=TaskStatus.running,
                message=message or "Task started",
                started_at=datetime.now(timezone.utc).isoformat() + "Z",
                updated_at=datetime.now(timezone.utc).isoformat() + "Z",
            )

    async def update_progress(self, task_id: str, progress: float, message: str = None):
        async with self._lock:
            if task_id not in self._tasks:
                return
            task = self._tasks[task_id]
            task.progress = min(max(progress, 0.0), 100.0)
            task.updated_at = datetime.utcnow().isoformat() + "Z"
            if message:
                task.message = message

    async def finish(self, task_id: str, result: Any = None):
        async with self._lock:
            task = self._tasks.get(task_id)
            if task:
                task.status = TaskStatus.done
                task.progress = 100.0
                task.result = result
                task.updated_at = datetime.now(timezone.utc).isoformat() + "Z"

    async def fail(self, task_id: str, error: str):
        async with self._lock:
            task = self._tasks.get(task_id)
            if task:
                task.status = TaskStatus.error
                task.error = error
                task.updated_at = datetime.now(timezone.utc).isoformat() + "Z"

    async def get(self, task_id: str) -> Optional[TaskProgress]:
        async with self._lock:
            return self._tasks.get(task_id)


PROGRESS = ProgressTracker()
