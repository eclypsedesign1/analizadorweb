import re
import requests
from bs4 import BeautifulSoup
from backend.config import HEADERS, REQUEST_TIMEOUT
from backend.models import ComplianceResult, Issue, Severity

COOKIE_SIGNATURES = [
    "cookieconsent", "cookie-consent", "cookie_consent", "cookiebanner",
    "cookie-banner", "tarteaucitron", "gdpr", "cookiebot", "onetrust",
    "cookiehub", "axeptio", "complianz",
]

PRIVACY_PATHS = ["/privacidad", "/privacy", "/privacy-policy", "/politica-de-privacidad", "/terminos", "/legal"]


def _fetch(url: str) -> str:
    try:
        r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        return r.text
    except Exception:
        return ""


def _has_cookie_banner(html: str) -> bool:
    html_lower = html.lower()
    return any(sig in html_lower for sig in COOKIE_SIGNATURES)


def _has_privacy_policy(base_url: str, html: str) -> bool:
    privacy_keywords = ["privacidad", "privacy", "política", "aviso legal", "cookies"]
    soup = BeautifulSoup(html, "lxml")
    for a in soup.find_all("a", href=True):
        text = a.get_text().lower()
        href = a["href"].lower()
        if any(kw in text or kw in href for kw in privacy_keywords):
            return True
    for path in PRIVACY_PATHS:
        try:
            r = requests.head(base_url.rstrip("/") + path, headers=HEADERS, timeout=5, allow_redirects=True)
            if r.status_code == 200:
                return True
        except Exception:
            pass
    return False


def _detect_analytics(html: str) -> dict:
    return {
        "ga4": bool(re.search(r"gtag\('config',\s*'G-", html) or "googletagmanager.com/gtag" in html),
        "gtm": bool("googletagmanager.com/gtm.js" in html or re.search(r"GTM-[A-Z0-9]+", html)),
        "meta_pixel": bool(re.search(r"fbq\('init'", html) or "connect.facebook.net/en_US/fbevents" in html),
        "hotjar": bool("static.hotjar.com" in html or re.search(r"hj\(.*?'hjid'", html)),
        "clarity": bool("clarity.ms/tag" in html or re.search(r"clarity\('set'", html)),
    }


def analyze(url: str) -> ComplianceResult:
    from urllib.parse import urlparse
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"

    issues: list[Issue] = []
    html = _fetch(url)

    has_cookie = _has_cookie_banner(html)
    has_privacy = _has_privacy_policy(base, html)
    analytics = _detect_analytics(html)
    has_any_analytics = any(analytics.values())

    if not has_cookie:
        issues.append(Issue(severity=Severity.warning, message="Sin banner de cookies detectado", detail="Requerido por GDPR/LGPD para sitios que usan cookies de seguimiento"))
    if not has_privacy:
        issues.append(Issue(severity=Severity.warning, message="Sin política de privacidad visible", detail="Obligatorio en la mayoría de países de LATAM y Europa"))
    if not has_any_analytics:
        issues.append(Issue(severity=Severity.info, message="Sin sistema de analytics instalado", detail="Sin datos de visitas, no es posible medir el rendimiento del sitio"))

    return ComplianceResult(
        has_cookie_banner=has_cookie,
        has_privacy_policy=has_privacy,
        has_ga4=analytics["ga4"],
        has_gtm=analytics["gtm"],
        has_meta_pixel=analytics["meta_pixel"],
        has_hotjar=analytics["hotjar"],
        has_clarity=analytics["clarity"],
        issues=issues
    )
