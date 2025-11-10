import uuid, asyncio
from typing import Dict, Any, Tuple
from core.config import settings
from jobs import fetch_bills_job

task_results: Dict[str, Dict[str, Any]] = {}

def has_inflight_task() -> Tuple[bool, str | None]:
    for tid, info in task_results.items():
        if info.get("status") == "Processing":
            return True, tid
    return False, None

def start_job(*, n: int | None = None, default_player: str | None = None) -> str:
    task_id = str(uuid.uuid4())
    task_results[task_id] = {"status": "Processing", "progress": 0}
    asyncio.create_task(
        fetch_bills_job.main(
            task_results,
            task_id,
            salt=settings.SALT,
            default_player=default_player or settings.DEFAULT_PLAYER,
            n=n
        )
    )
    return task_id