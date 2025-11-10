from __future__ import annotations
import asyncio
from dataclasses import dataclass, field
from typing import Dict, Optional, Callable, Awaitable

@dataclass
class TaskInfo:
    task_id: str
    progress: float = 0.0         # 0..100
    status: str = "pending"       # pending|running|done|error|cancelled
    result: Optional[dict] = None
    error: Optional[str] = None
    _task: Optional[asyncio.Task] = field(default=None, repr=False)

class TaskManager:
    """
    Simple in-memory task manager keyed by task_id.
    Thread-safety: guarded by an asyncio.Lock (works for single-process uvicorn workers).
    """
    def __init__(self) -> None:
        self._tasks: Dict[str, TaskInfo] = {}
        self._lock = asyncio.Lock()

    def get(self, task_id: str) -> Optional[TaskInfo]:
        return self._tasks.get(task_id)

    async def get_or_create(
        self,
        task_id: str,
        job_factory: Callable[[TaskInfo], Awaitable[dict]],
    ) -> TaskInfo:
        async with self._lock:
            info = self._tasks.get(task_id)
            if info and info.status in {"pending", "running"}:
                # existing ongoing job -> just return it; caller can read progress
                return info

            # create a new TaskInfo and schedule the job
            info = TaskInfo(task_id=task_id, status="running", progress=0.0)
            self._tasks[task_id] = info

            async def runner():
                try:
                    info.status = "running"
                    result = await job_factory(info)
                    info.result = result
                    info.progress = 100.0
                    info.status = "done"
                except asyncio.CancelledError:
                    info.status = "cancelled"
                    raise
                except Exception as e:
                    info.status = "error"
                    info.error = str(e)

            info._task = asyncio.create_task(runner())
            return info

    async def cancel(self, task_id: str) -> bool:
        async with self._lock:
            info = self._tasks.get(task_id)
            if not info or not info._task or info._task.done():
                return False
            info._task.cancel()
            return True

    async def cleanup_finished(self) -> None:
        """Optionally clean finished tasks to free memory."""
        async with self._lock:
            to_delete = [tid for tid, t in self._tasks.items() if t.status in {"done", "error", "cancelled"}]
            for tid in to_delete:
                del self._tasks[tid]
