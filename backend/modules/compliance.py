from __future__ import annotations

import re

from bs4 import BeautifulSoup

from backend.safe_fetch import safe_get, safe_head
from backend.models import ComplianceResult, Issue, Severity

COOKIE_SIGNATURES = [
    "cookieconsent", "cookie-consent", "cookie_consent", "cookiebanner",
    "cookie-banner", "tarteaucitron", "gdpr", "cookiebot", "onetrust",
    "cookiehub", "axeptio", "complianz",
]

PRIVACY_PATHS = [
    "/privacidad", "/privacy", "/privacy-policy",
    "/politica-de-privacidad", "/terminos", "/legal",
]

PRIVACY_KEYWORDS = ["privacidad", "privacy", "política", "aviso legal", "cookies"]


def _fetch(url: str) -> str:
    try:
        return safe_get(url, allow_redirects=True).text
    except Exception:
        return ""


def _has_privacy_policy(base_url: str, html: str) -> bool:
    soup = BeautifulSoup(html, "lxml")
    for a in soup.find_all("a", href=True):
        text = a.get_text().lower()
        href = a["href"].lower()
        if any(kw in text or kw in href for kw in PRIVACY_KEYWORDS):
            return True
    for path in PRIVACY_PATHS:
        try:
            r = safe_head(base_url.rstrip("/") + path, allow_redirects=True, timeout=5)
            if r.status_code == 200:
                return True
        except Exception:
            pass
    return False


def _detect_analytics(html: str) -> dict:
    return {
        "ga4":        bool(re.search(r"gtag\('config',\s*'G-", html) or "googletagmanager.com/gtag" in html),
        "gtm":        bool("googletagmanager.com/gtm.js" in html or re.search(r"GTM-[A-Z0-9]+", html)),
        "meta_pixel": bool(re.search(r"fbq\('init'", html) or "connect.facebook.net/en_US/fbevents" in html),
        "hotjar":     bool("static.hotjar.com" in html),
        "clarity":    bool("clarity.ms/tag" in html),
    }


def analyze(url: str) -> ComplianceResult:
    from urllib.parse import urlparse
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"

    issues: list[Issue] = []
    html = _fetch(url)
    html_lower = html.lower()

    has_cookie = any(sig in html_lower for sig in COOKIE_SIGNATURES)
    has_privacy = _has_privacy_policy(base, html)
    analytics = _detect_analytics(html)
    has_any_analytics = any(analytics.values())

    if not has_cookie:
        issues.append(Issue(severity=Severity.warning, message="Sin banner de cookies detectado", detail="Requerido por GDPR/LGPD para sitios que usan cookies de seguimiento"))
    if not has_privacy:
        issues.append(Issue(severity=Severity.warning, message="Sin política de privacidad visible", detail="Obligatorio en la mayoría de países de LATAM y Europa"))
    if not has_any_analytics:
        issues.append(Issue(severity=Severity.info, message="Sin sistema de analytics instalado", detail="Sin datos de visitas no es posible medir el rendimiento del sitio"))

    return ComplianceResult(
        has_cookie_banner=has_cookie,
        has_privacy_policy=has_privacy,
        has_ga4=analytics["ga4"],
        has_gtm=analytics["gtm"],
        has_meta_pixel=analytics["meta_pixel"],
        has_hotjar=analytics["hotjar"],
        has_clarity=analytics["clarity"],
        issues=issues,
    )
