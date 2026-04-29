from __future__ import annotations

import time

import requests

from backend.config import PAGESPEED_API_KEY, REQUEST_TIMEOUT
from backend.safe_fetch import safe_get, safe_head
from backend.models import PerformanceResult, Issue, Severity

CDN_SIGNATURES = {
    "Cloudflare": ["cf-ray", "cf-cache-status"],
    "Fastly": ["x-served-by", "x-fastly"],
    "Akamai": ["x-check-cacheable", "x-akamai-transformed"],
    "AWS CloudFront": ["x-amz-cf-id"],
    "BunnyCDN": ["x-pull-zone"],
}


def _pagespeed(url: str, strategy: str) -> dict:
    if not PAGESPEED_API_KEY:
        return {}
    try:
        r = requests.get(
            "https://www.googleapis.com/pagespeedonline/v5/runPagespeed",
            params={"url": url, "strategy": strategy, "key": PAGESPEED_API_KEY},
            timeout=45,
        )
        if not r.ok:
            return {}
        data = r.json()
        cats = data.get("lighthouseResult", {}).get("categories", {})
        audits = data.get("lighthouseResult", {}).get("audits", {})
        score = int(cats.get("performance", {}).get("score", 0) * 100)

        def ms(key: str) -> float | None:
            v = audits.get(key, {}).get("numericValue")
            return round(v / 1000, 2) if v else None

        screenshot = None
        if strategy == "mobile":
            ss_data = audits.get("final-screenshot", {}).get("details", {}).get("data", "")
            if ss_data:
                screenshot = ss_data

        return {
            "score": score,
            "lcp": ms("largest-contentful-paint"),
            "fcp": ms("first-contentful-paint"),
            "cls": audits.get("cumulative-layout-shift", {}).get("numericValue"),
            "ttfb": ms("server-response-time"),
            "screenshot": screenshot,
        }
    except Exception:
        return {}


def _measure_ttfb(url: str) -> float | None:
    try:
        start = time.time()
        r = safe_get(url, stream=True)
        ttfb = time.time() - start
        r.close()
        return round(ttfb, 3)
    except Exception:
        return None


def _detect_cdn(url: str) -> tuple[bool, str | None]:
    try:
        r = safe_head(url, allow_redirects=True)
        resp_lower = {k.lower(): v.lower() for k, v in r.headers.items()}
        for provider, sigs in CDN_SIGNATURES.items():
            if any(sig in resp_lower for sig in sigs):
                return True, provider
    except Exception:
        pass
    return False, None


def analyze(url: str) -> PerformanceResult:
    issues: list[Issue] = []

    mobile = _pagespeed(url, "mobile")
    desktop = _pagespeed(url, "desktop")
    uses_cdn, cdn_provider = _detect_cdn(url)
    ttfb = mobile.get("ttfb") or _measure_ttfb(url)

    mobile_score = mobile.get("score")
    desktop_score = desktop.get("score")
    lcp = mobile.get("lcp")
    fcp = mobile.get("fcp")
    cls = mobile.get("cls")

    if mobile_score is not None and mobile_score < 50:
        issues.append(Issue(severity=Severity.critical, message=f"Rendimiento mobile muy bajo: {mobile_score}/100", detail="Usuarios en celular experimentan carga muy lenta"))
    elif mobile_score is not None and mobile_score < 70:
        issues.append(Issue(severity=Severity.warning, message=f"Rendimiento mobile a mejorar: {mobile_score}/100"))

    if lcp and lcp > 4.0:
        issues.append(Issue(severity=Severity.critical, message=f"LCP lento: {lcp}s", detail="Google recomienda menos de 2.5s para buena experiencia"))
    elif lcp and lcp > 2.5:
        issues.append(Issue(severity=Severity.warning, message=f"LCP a mejorar: {lcp}s"))

    if cls and cls > 0.25:
        issues.append(Issue(severity=Severity.warning, message=f"CLS alto: {cls}", detail="El contenido se mueve durante la carga"))

    if not uses_cdn:
        issues.append(Issue(severity=Severity.info, message="No usa CDN", detail="Un CDN mejora la velocidad de carga globalmente"))

    return PerformanceResult(
        mobile_score=mobile_score,
        desktop_score=desktop_score,
        lcp=lcp,
        fcp=fcp,
        cls=cls,
        ttfb=ttfb,
        uses_cdn=uses_cdn,
        cdn_provider=cdn_provider,
        screenshot_mobile=mobile.get("screenshot"),
        issues=issues,
    )
