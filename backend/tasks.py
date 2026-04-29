import asyncio
import uuid
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import AsyncGenerator

from backend.models import AnalysisRequest, AnalysisResult
from backend import cache as cache_store
from backend.config import PDF_OUTPUT_DIR

_jobs: dict[str, dict] = {}
_executor = ThreadPoolExecutor(max_workers=8)


def _run_sync(fn, *args):
    return fn(*args)


async def _run_in_executor(fn, *args):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, fn, *args)


def _emit(job_id: str, module: str, percent: int, message: str):
    _jobs[job_id]["events"].append({
        "module": module, "percent": percent, "message": message
    })


async def run_analysis(req: AnalysisRequest) -> str:
    job_id = str(uuid.uuid4())[:8]
    _jobs[job_id] = {"status": "running", "result": None, "events": [], "created": datetime.utcnow().isoformat()}

    asyncio.create_task(_analyze(job_id, req))
    return job_id


async def _analyze(job_id: str, req: AnalysisRequest):
    from urllib.parse import urlparse
    from backend.modules import cms, security, performance, hosting, contacts, seo, compliance
    from backend.modules.scorer import calculate
    from backend.exporters.pdf_report import generate

    url = req.url
    domain = urlparse(url).netloc or url

    cached = cache_store.get(domain)
    if cached:
        _jobs[job_id]["result"] = cached
        _jobs[job_id]["status"] = "done"
        _emit(job_id, "cache", 100, "Resultado obtenido del caché")
        return

    result = AnalysisResult(job_id=job_id, domain=domain, url=url, name=req.name, email=req.email)

    try:
        _emit(job_id, "cms", 5, "Detectando CMS y tecnologías...")
        result.cms = await _run_in_executor(cms.analyze, url)
        _emit(job_id, "cms", 20, f"CMS detectado: {result.cms.cms or 'Desconocido'}")

        wp_version = result.cms.version if result.cms and result.cms.cms == "WordPress" else None

        _emit(job_id, "security", 22, "Auditando seguridad...")
        result.security = await _run_in_executor(security.analyze, url, wp_version)
        _emit(job_id, "security", 38, "Auditoría de seguridad completada")

        _emit(job_id, "performance", 40, "Midiendo performance con PageSpeed...")
        result.performance = await _run_in_executor(performance.analyze, url)
        _emit(job_id, "performance", 55, f"Score mobile: {result.performance.mobile_score}/100" if result.performance.mobile_score else "Performance analizada")

        _emit(job_id, "hosting", 57, "Analizando hosting e infraestructura...")
        result.hosting = await _run_in_executor(hosting.analyze, url)
        _emit(job_id, "hosting", 68, f"Hosting: {result.hosting.provider or 'Desconocido'}")

        _emit(job_id, "contacts", 70, "Extrayendo información de contacto...")
        result.contacts = await _run_in_executor(contacts.analyze, url)
        _emit(job_id, "contacts", 78, f"{len(result.contacts.emails)} email(s) encontrado(s)")

        _emit(job_id, "seo", 80, "Analizando SEO...")
        result.seo = await _run_in_executor(seo.analyze, url)
        _emit(job_id, "seo", 88, "SEO analizado")

        _emit(job_id, "compliance", 89, "Verificando compliance y analytics...")
        result.compliance = await _run_in_executor(compliance.analyze, url)
        _emit(job_id, "compliance", 93, "Compliance verificado")

        _emit(job_id, "score", 94, "Calculando score comercial...")
        result.score = calculate(result.cms, result.security, result.performance, result.hosting, result.seo, result.compliance)
        _emit(job_id, "score", 96, f"Score: {result.score.total}/100 — {result.score.label}")

        _emit(job_id, "pdf", 97, "Generando reporte PDF...")
        pdf_path = await _run_in_executor(generate, result, PDF_OUTPUT_DIR)
        result.pdf_path = pdf_path
        _emit(job_id, "pdf", 100, "Reporte listo")

        result_dict = result.model_dump()
        cache_store.set(domain, result_dict)
        _jobs[job_id]["result"] = result_dict

    except Exception as e:
        result.error = str(e)
        _jobs[job_id]["result"] = result.model_dump()
        _emit(job_id, "error", 100, f"Error: {str(e)}")

    _jobs[job_id]["status"] = "done"


def get_job(job_id: str) -> dict | None:
    return _jobs.get(job_id)


async def stream_events(job_id: str) -> AsyncGenerator[str, None]:
    sent = 0
    while True:
        job = _jobs.get(job_id)
        if not job:
            yield f"data: {json.dumps({'error': 'job not found'})}\n\n"
            break

        events = job.get("events", [])
        while sent < len(events):
            yield f"data: {json.dumps(events[sent])}\n\n"
            sent += 1

        if job.get("status") == "done" and sent >= len(events):
            yield f"data: {json.dumps({'done': True})}\n\n"
            break

        await asyncio.sleep(0.3)
