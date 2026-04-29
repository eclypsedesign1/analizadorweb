import re
import requests
from bs4 import BeautifulSoup
from backend.config import HEADERS, REQUEST_TIMEOUT
from backend.models import ContactResult, Issue, Severity

SOCIAL_PATTERNS = {
    "linkedin": r"linkedin\.com/(?:company|in)/([^\"'/?\s]+)",
    "instagram": r"instagram\.com/([^\"'/?\s]+)",
    "facebook": r"facebook\.com/([^\"'/?\s]+)",
    "twitter": r"(?:twitter|x)\.com/([^\"'/?\s]+)",
    "youtube": r"youtube\.com/(?:channel|@|c)/([^\"'/?\s]+)",
    "tiktok": r"tiktok\.com/@([^\"'/?\s]+)",
}

PHONE_PATTERN = r"(?:\+?[\d\s\-().]{7,20})"
EMAIL_PATTERN = r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"

CONTACT_PATHS = ["/", "/contacto", "/contact", "/nosotros", "/about", "/acerca"]


def _fetch_page(url: str) -> str:
    try:
        r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        return r.text
    except Exception:
        return ""


def _extract_emails(html: str, domain: str) -> list[str]:
    found = set()
    for m in re.finditer(r'href="mailto:([^"]+)"', html, re.IGNORECASE):
        found.add(m.group(1).strip().lower())
    for m in re.finditer(EMAIL_PATTERN, html):
        email = m.group(0).lower()
        if not email.endswith((".png", ".jpg", ".gif", ".svg", ".css", ".js")):
            found.add(email)
    return sorted(found)[:5]


def _extract_phones(html: str) -> list[str]:
    found = set()
    for m in re.finditer(r'href="tel:([^"]+)"', html, re.IGNORECASE):
        found.add(m.group(1).strip())
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(" ")
    for m in re.finditer(r'\+?[\d][\d\s\-().]{6,18}[\d]', text):
        candidate = m.group(0).strip()
        digits = re.sub(r'\D', '', candidate)
        if 7 <= len(digits) <= 15:
            found.add(candidate)
    return sorted(found)[:3]


def _extract_social(html: str) -> dict:
    social = {}
    for platform, pattern in SOCIAL_PATTERNS.items():
        m = re.search(pattern, html, re.IGNORECASE)
        if m:
            social[platform] = m.group(0)
    return social


def _extract_contact_name(html: str) -> str | None:
    soup = BeautifulSoup(html, "lxml")
    for selector in ["#about", "#nosotros", ".team-member", ".about-section"]:
        section = soup.select_one(selector)
        if section:
            m = re.search(r'\b([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+ [A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)\b', section.get_text())
            if m:
                return m.group(1)
    return None


def analyze(url: str) -> ContactResult:
    from urllib.parse import urlparse
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    domain = parsed.netloc

    all_html = ""
    for path in CONTACT_PATHS:
        all_html += _fetch_page(base.rstrip("/") + path)

    emails = _extract_emails(all_html, domain)
    phones = _extract_phones(all_html)
    social = _extract_social(all_html)
    contact_name = _extract_contact_name(all_html)

    issues: list[Issue] = []
    if not emails:
        issues.append(Issue(severity=Severity.info, message="No se encontraron emails en el sitio"))
    if not phones:
        issues.append(Issue(severity=Severity.info, message="No se encontró número de teléfono visible"))

    return ContactResult(
        emails=emails,
        phones=phones,
        social=social,
        contact_name=contact_name,
        issues=issues
    )
