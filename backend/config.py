from dotenv import load_dotenv
import os

load_dotenv()

PAGESPEED_API_KEY = os.getenv("PAGESPEED_API_KEY", "")
IPINFO_TOKEN = os.getenv("IPINFO_TOKEN", "")
WPSCAN_API_KEY = os.getenv("WPSCAN_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
APP_PORT = int(os.getenv("APP_PORT", "8000"))
DEBUG = os.getenv("DEBUG", "false").lower() == "true"

RATE_LIMIT_PER_DAY = int(os.getenv("RATE_LIMIT_PER_DAY", "5"))
CACHE_TTL = int(os.getenv("CACHE_TTL", "86400"))
PDF_OUTPUT_DIR = os.getenv("PDF_OUTPUT_DIR", "./pdfs")

REQUEST_TIMEOUT = 15
MODULE_TIMEOUT = 30

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; EclypseWebAnalyzer/2.0; +https://eclypsedesign.com)"
}
