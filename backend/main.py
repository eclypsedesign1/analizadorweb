from __future__ import annotations

import logging
import re
import time
from collections import defaultdict
from pathlib import Path

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

from backend.models import AnalysisRequest
from backend import tasks
from backend.config import RATE_LIMIT_PER_DAY, PDF_OUTPUT_DIR, ALLOWED_ORIGINS
from backend.safe_fetch import assert_safe_url

logger = logging.getLogger(__name__)

app = FastAPI(title="Eclypse Web Intelligence Analyzer", version="2.0")

# CORS: only allow configured origins (not wildcard)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

# Security headers on every response
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response: Response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
    # Only add CSP on HTML pages, not on SSE/binary endpoints
    if "text/html" in response.headers.get("content-type", ""):
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' https://fonts.googleapis.com; "
            "font-src https://fonts.gstatic.com; "
            "img-src 'self' data:; "
            "connect-src 'self';"
        )
    return response


# Rate limiter — per real client IP, bounded cleanup
_ip_hits: dict[str, list[float]] = defaultdict(list)
_SAFE_DOMAIN = re.compile(r"[^a-zA-Z0-9\-]")


def _get_client_ip(request: Request) -> str:
    # When behind a trusted reverse proxy (Nginx), trust X-Real-IP.
    # Never trust X-Forwarded-For directly as it can be spoofed by the client.
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else "unknown"


def _check_rate_limit(ip: str):
    now = time.time()
    day_ago = now - 86400
    # Prune old entries for this IP
    _ip_hits[ip] = [t for t in _ip_hits[ip] if t > day_ago]
    if len(_ip_hits[ip]) >= RATE_LIMIT_PER_DAY:
        raise HTTPException(
            status_code=429,
            detail=f"Límite de {RATE_LIMIT_PER_DAY} análisis por día alcanzado. Volvé mañana."
        )
    _ip_hits[ip].append(now)

    # Evict stale IPs to prevent unbounded memory growth
    if len(_ip_hits) > 10_000:
        stale = [k for k, hits in _ip_hits.items() if not hits or hits[-1] < day_ago]
        for k in stale:
            del _ip_hits[k]


@app.post("/analyze")
async def analyze(req: AnalysisRequest, request: Request):
    ip = _get_client_ip(request)
    _check_rate_limit(ip)

    # Validate URL against SSRF targets before queuing (fast fail)
    try:
        assert_safe_url(req.url)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    job_id = await tasks.run_analysis(req)
    return {"job_id": job_id, "redirect": f"/results/{job_id}"}


@app.get("/stream/{job_id}")
async def stream(job_id: str):
    return StreamingResponse(
        tasks.stream_events(job_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/result/{job_id}")
async def get_result(job_id: str):
    job = tasks.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job no encontrado")
    result = dict(job.get("result") or {})
    # Strip PII — name and email must not be exposed on an unauthenticated endpoint
    result.pop("email", None)
    result.pop("name", None)
    return result


@app.get("/report/{job_id}")
async def download_report(job_id: str):
    job = tasks.get_job(job_id)
    if not job or not job.get("result"):
        raise HTTPException(status_code=404, detail="Reporte no disponible aún")
    pdf_path = job["result"].get("pdf_path")
    if not pdf_path or not Path(pdf_path).exists():
        raise HTTPException(status_code=404, detail="PDF no generado aún")

    domain = job["result"].get("domain", "reporte")
    # Sanitize domain for use in Content-Disposition header — alphanumeric and hyphens only
    safe_domain = _SAFE_DOMAIN.sub("_", domain)[:60]
    filename = f"analisis_{safe_domain}.pdf"

    return FileResponse(pdf_path, media_type="application/pdf", filename=filename)


@app.get("/health")
async def health():
    return {"status": "ok"}


# Serve frontend static files
frontend_path = Path(__file__).parent.parent / "frontend"
if frontend_path.exists():
    app.mount("/assets", StaticFiles(directory=str(frontend_path / "assets")), name="assets")

    @app.get("/", response_class=HTMLResponse)
    async def index():
        return (frontend_path / "index.html").read_text(encoding="utf-8")

    @app.get("/results/{job_id}", response_class=HTMLResponse)
    async def results_page(job_id: str):
        return (frontend_path / "results.html").read_text(encoding="utf-8")


if __name__ == "__main__":
    import uvicorn
    from backend.config import APP_HOST, APP_PORT, DEBUG
    uvicorn.run("backend.main:app", host=APP_HOST, port=APP_PORT, reload=DEBUG)
