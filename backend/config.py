from __future__ import annotations

from dotenv import load_dotenv
import os
from pathlib import Path

load_dotenv()

# ── API keys ──────────────────────────────────────────────────────────────────
PAGESPEED_API_KEY = os.getenv("PAGESPEED_API_KEY", "")
IPINFO_TOKEN = os.getenv("IPINFO_TOKEN", "")
WPSCAN_API_KEY = os.getenv("WPSCAN_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")

# ── App settings ──────────────────────────────────────────────────────────────
APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
APP_PORT = int(os.getenv("APP_PORT", "8000"))
DEBUG = os.getenv("DEBUG", "false").lower() == "true"

# ── Rate limiting ─────────────────────────────────────────────────────────────
RATE_LIMIT_PER_DAY = int(os.getenv("RATE_LIMIT_PER_DAY", "5"))

# ── CORS: comma-separated list of allowed origins ────────────────────────────
_origins_env = os.getenv("ALLOWED_ORIGINS", "")
ALLOWED_ORIGINS: list[str] = [o.strip() for o in _origins_env.split(",") if o.strip()] or ["*"]

# ── Cache & storage — absolute paths anchored to project root ─────────────────
_PROJECT_ROOT = Path(__file__).parent.parent
CACHE_TTL = int(os.getenv("CACHE_TTL", "86400"))
CACHE_DIR = Path(os.getenv("CACHE_DIR", str(_PROJECT_ROOT / ".cache")))
PDF_OUTPUT_DIR = str(Path(os.getenv("PDF_OUTPUT_DIR", str(_PROJECT_ROOT / "pdfs"))))

# ── HTTP defaults ─────────────────────────────────────────────────────────────
REQUEST_TIMEOUT = 15
MODULE_TIMEOUT = 30

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; EclypseWebAnalyzer/2.0; +https://eclypsedesign.com)"
}
