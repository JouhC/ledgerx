

def has_inflight_task() -> Tuple[bool, str | None]:
    for tid, info in task_results.items():
        if info.get("status") == "Processing":
            return True, tid
    return False, None