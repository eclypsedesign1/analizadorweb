from __future__ import annotations

import ssl
import socket
import datetime

import requests

from backend.config import REQUEST_TIMEOUT, WPSCAN_API_KEY
from backend.safe_fetch import safe_get, safe_head
from backend.models import SecurityResult, Issue, Severity

SECURITY_HEADERS = [
    "x-frame-options", "content-security-policy", "strict-transport-security",
    "x-content-type-options", "referrer-policy", "permissions-policy",
]
SENSITIVE_PATHS = [
    "/wp-config.php.bak", "/.env", "/phpinfo.php", "/.git/config",
    "/wp-config.php", "/debug.log",
]


def _check_ssl(hostname: str) -> dict:
    result: dict = {"valid": False, "issuer": None, "days_left": None}
    try:
        ctx = ssl.create_default_context()
        raw_sock = socket.create_connection((hostname, 443), timeout=10)
        with ctx.wrap_socket(raw_sock, server_hostname=hostname) as s:
            cert = s.getpeercert()

        not_after = datetime.datetime.strptime(cert["notAfter"], "%b %d %H:%M:%S %Y %Z")
        days_left = (not_after - datetime.datetime.utcnow()).days
        issuer = dict(x[0] for x in cert.get("issuer", []))
        result["valid"] = days_left > 0
        result["days_left"] = days_left
        result["issuer"] = issuer.get("organizationName", issuer.get("commonName", "Desconocido"))
    except ssl.SSLCertVerificationError:
        result["valid"] = False
        result["issuer"] = "Certificado inválido"
    except Exception:
        result["valid"] = False
    return result


def _check_headers(url: str) -> dict:
    try:
        r = safe_head(url, allow_redirects=True)
        resp = {k.lower(): v for k, v in r.headers.items()}
        return {h: resp.get(h) for h in SECURITY_HEADERS}
    except Exception:
        return {h: None for h in SECURITY_HEADERS}


def _check_exposed_files(base_url: str) -> list[str]:
    exposed = []
    for path in SENSITIVE_PATHS:
        try:
            r = safe_get(base_url.rstrip("/") + path, allow_redirects=False, timeout=8)
            if r.status_code == 200 and len(r.content) > 10:
                exposed.append(path)
        except Exception:
            pass
    return exposed


def _check_wp_cves(version: str) -> list[dict]:
    if not WPSCAN_API_KEY or not version:
        return []
    try:
        r = requests.get(
            f"https://wpscan.com/api/v3/wordpresses/{version.replace('.', '')}",
            headers={"Authorization": f"Token token={WPSCAN_API_KEY}"},
            timeout=10,
        )
        if r.ok:
            data = r.json()
            key = version.replace(".", "")
            vulns = data.get(key, {}).get("vulnerabilities", [])
            return [
                {"title": v.get("title"), "cve": (v.get("references", {}).get("cve") or [None])[0]}
                for v in vulns[:5]
            ]
    except Exception:
        pass
    return []


def analyze(url: str, wp_version: str | None = None) -> SecurityResult:
    from urllib.parse import urlparse
    parsed = urlparse(url)
    hostname = parsed.hostname or ""
    base = f"{parsed.scheme}://{parsed.netloc}"

    issues: list[Issue] = []

    ssl_data = _check_ssl(hostname)
    sec_headers = _check_headers(url)
    exposed = _check_exposed_files(base)
    cves = _check_wp_cves(wp_version) if wp_version else []

    if not ssl_data["valid"]:
        issues.append(Issue(severity=Severity.critical, message="SSL inválido o ausente", detail="Los visitantes verán 'Sitio no seguro' en el navegador"))
    elif ssl_data["days_left"] is not None and ssl_data["days_left"] < 30:
        issues.append(Issue(severity=Severity.critical, message=f"SSL vence en {ssl_data['days_left']} días", detail="Renovar antes de que expire para evitar alertas a visitantes"))
    elif ssl_data["days_left"] is not None and ssl_data["days_left"] < 60:
        issues.append(Issue(severity=Severity.warning, message=f"SSL vence en {ssl_data['days_left']} días"))

    missing = [h for h, v in sec_headers.items() if v is None]
    if "content-security-policy" in missing:
        issues.append(Issue(severity=Severity.warning, message="Sin Content Security Policy (CSP)", detail="Aumenta el riesgo de ataques XSS"))
    if "strict-transport-security" in missing:
        issues.append(Issue(severity=Severity.warning, message="Sin HSTS", detail="El sitio puede ser accedido por HTTP sin redirección forzada"))
    if "x-frame-options" in missing:
        issues.append(Issue(severity=Severity.info, message="Sin X-Frame-Options"))

    for path in exposed:
        issues.append(Issue(severity=Severity.critical, message=f"Archivo sensible expuesto: {path}", detail="Puede exponer credenciales o configuración del servidor"))

    for cve in cves:
        issues.append(Issue(severity=Severity.critical, message=f"Vulnerabilidad WordPress: {cve['title']}", detail=f"CVE: {cve['cve']}"))

    return SecurityResult(
        ssl_valid=ssl_data["valid"],
        ssl_issuer=ssl_data["issuer"],
        ssl_days_left=ssl_data["days_left"],
        headers=sec_headers,
        exposed_files=exposed,
        cves=cves,
        issues=issues,
    )
