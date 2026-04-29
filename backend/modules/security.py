import ssl
import socket
import datetime
import requests
from backend.config import HEADERS, REQUEST_TIMEOUT, WPSCAN_API_KEY
from backend.models import SecurityResult, Issue, Severity

SECURITY_HEADERS = ["x-frame-options", "content-security-policy", "strict-transport-security", "x-content-type-options", "referrer-policy", "permissions-policy"]
SENSITIVE_PATHS = ["/wp-config.php.bak", "/.env", "/phpinfo.php", "/.git/config", "/wp-config.php", "/debug.log"]


def _check_ssl(hostname: str) -> dict:
    result = {"valid": False, "issuer": None, "days_left": None, "grade": None}
    try:
        ctx = ssl.create_default_context()
        with ctx.wrap_socket(socket.socket(), server_hostname=hostname) as s:
            s.settimeout(10)
            s.connect((hostname, 443))
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
        r = requests.head(url, headers=HEADERS, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        resp_headers = {k.lower(): v for k, v in r.headers.items()}
        return {h: resp_headers.get(h) for h in SECURITY_HEADERS}
    except Exception:
        return {h: None for h in SECURITY_HEADERS}


def _check_exposed_files(base_url: str) -> list[str]:
    exposed = []
    for path in SENSITIVE_PATHS:
        try:
            r = requests.get(base_url.rstrip("/") + path, headers=HEADERS, timeout=8, allow_redirects=False)
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
            timeout=10
        )
        if r.ok:
            data = r.json()
            vuln_key = version.replace(".", "")
            vulns = data.get(vuln_key, {}).get("vulnerabilities", [])
            return [{"title": v.get("title"), "cve": v.get("references", {}).get("cve", [None])[0]} for v in vulns[:5]]
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
    cves = _check_wp_cves(wp_version or "") if wp_version else []

    if not ssl_data["valid"]:
        issues.append(Issue(severity=Severity.critical, message="SSL inválido o ausente", detail="Los visitantes verán 'Sitio no seguro' en el navegador"))
    elif ssl_data["days_left"] is not None and ssl_data["days_left"] < 30:
        issues.append(Issue(severity=Severity.critical, message=f"SSL vence en {ssl_data['days_left']} días", detail="Renovar antes de que expire para evitar alertas a visitantes"))
    elif ssl_data["days_left"] is not None and ssl_data["days_left"] < 60:
        issues.append(Issue(severity=Severity.warning, message=f"SSL vence en {ssl_data['days_left']} días"))

    missing_headers = [h for h, v in sec_headers.items() if v is None]
    if "content-security-policy" in missing_headers:
        issues.append(Issue(severity=Severity.warning, message="Sin Content Security Policy (CSP)", detail="Aumenta el riesgo de ataques XSS"))
    if "strict-transport-security" in missing_headers:
        issues.append(Issue(severity=Severity.warning, message="Sin HSTS", detail="El sitio puede ser accedido por HTTP sin redirección forzada"))
    if "x-frame-options" in missing_headers:
        issues.append(Issue(severity=Severity.info, message="Sin X-Frame-Options"))

    for path in exposed:
        issues.append(Issue(severity=Severity.critical, message=f"Archivo sensible expuesto: {path}", detail="Este archivo puede exponer credenciales o configuración del servidor"))

    for cve in cves:
        issues.append(Issue(severity=Severity.critical, message=f"Vulnerabilidad WordPress: {cve['title']}", detail=f"CVE: {cve['cve']}"))

    return SecurityResult(
        ssl_valid=ssl_data["valid"],
        ssl_issuer=ssl_data["issuer"],
        ssl_days_left=ssl_data["days_left"],
        ssl_grade=ssl_data["grade"],
        headers=sec_headers,
        exposed_files=exposed,
        cves=cves,
        issues=issues
    )
