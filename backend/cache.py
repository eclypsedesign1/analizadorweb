import json
import time
import hashlib
from pathlib import Path
from backend.config import CACHE_TTL

_CACHE_DIR = Path(".cache")
_CACHE_DIR.mkdir(exist_ok=True)


def _key(domain: str) -> Path:
    h = hashlib.md5(domain.encode()).hexdigest()
    return _CACHE_DIR / f"{h}.json"


def get(domain: str) -> dict | None:
    path = _key(domain)
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    if time.time() - data["_ts"] > CACHE_TTL:
        path.unlink(missing_ok=True)
        return None
    return data["result"]


def set(domain: str, result: dict) -> None:
    path = _key(domain)
    path.write_text(json.dumps({"_ts": time.time(), "result": result}))
