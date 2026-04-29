from __future__ import annotations

import json
import time
import hashlib
from pathlib import Path

from backend.config import CACHE_TTL, CACHE_DIR

CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _key(domain: str) -> Path:
    h = hashlib.sha256(domain.encode()).hexdigest()
    return CACHE_DIR / f"{h}.json"


def get(domain: str) -> dict | None:
    path = _key(domain)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        path.unlink(missing_ok=True)
        return None
    if time.time() - data.get("_ts", 0) > CACHE_TTL:
        path.unlink(missing_ok=True)
        return None
    return data.get("result")


def set(domain: str, result: dict) -> None:
    path = _key(domain)
    path.write_text(
        json.dumps({"_ts": time.time(), "result": result}, default=str),
        encoding="utf-8",
    )
