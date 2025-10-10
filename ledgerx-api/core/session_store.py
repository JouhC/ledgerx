# utils/session_store.py
from cachetools import TTLCache
from typing import Any

# keep sessions 15 minutes; adjust as you like
store = TTLCache(maxsize=1000, ttl=15 * 60)

def put(key: str, value: dict[str, Any]) -> None:
    store[key] = value

def get(key: str) -> dict | None:
    return store.get(key)
