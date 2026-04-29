import os
import time
import json
from collections import defaultdict
from pathlib import Path

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse, FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from backend.models import AnalysisRequest
from backend import tasks
from backend.config import RATE_LIMIT_PER_DAY, PDF_OUTPUT_DIR

app = FastAPI(title="Eclypse Web Intelligence Analyzer", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Simple in-memory rate limiter
_ip_hits: dict[str, list[float]] = defaultdict(list)


def _check_rate_limit(ip: str):
    now = time.time()
    day_ago = now - 86400
    _ip_hits[ip] = [t for t in _ip_hits[ip] if t > day_ago]
    if len(_ip_hits[ip]) >= RATE_LIMIT_PER_DAY:
        raise HTTPException(status_code=429, detail=f"Límite de {RATE_LIMIT_PER_DAY} análisis por día alcanzado. Volvé mañana.")
    _ip_hits[ip].append(now)


@app.post("/analyze")
async def analyze(req: AnalysisRequest, request: Request):
    ip = request.client.host if request.client else "unknown"
    _check_rate_limit(ip)
    job_id = await tasks.run_analysis(req)
    return {"job_id": job_id, "redirect": f"/results/{job_id}"}


@app.get("/stream/{job_id}")
async def stream(job_id: str):
    return StreamingResponse(
        tasks.stream_events(job_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


@app.get("/result/{job_id}")
async def get_result(job_id: str):
    job = tasks.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job no encontrado")
    return job.get("result", {})


@app.get("/report/{job_id}")
async def download_report(job_id: str):
    job = tasks.get_job(job_id)
    if not job or not job.get("result"):
        raise HTTPException(status_code=404, detail="Reporte no disponible aún")
    pdf_path = job["result"].get("pdf_path")
    if not pdf_path or not Path(pdf_path).exists():
        raise HTTPException(status_code=404, detail="PDF no generado aún")
    domain = job["result"].get("domain", "reporte")
    filename = f"analisis_{domain.replace('.', '_')}.pdf"
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
