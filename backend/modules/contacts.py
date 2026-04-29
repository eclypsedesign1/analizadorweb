from __future__ import annotations

import re

from bs4 import BeautifulSoup

from backend.safe_fetch import safe_get
from backend.models import ContactResult, Issue, Severity

SOCIAL_PATTERNS = {
    "linkedin":  r"linkedin\.com/(?:company|in)/([^\"'/?\s]+)",
    "instagram": r"instagram\.com/([^\"'/?\s]+)",
    "facebook":  r"facebook\.com/([^\"'/?\s]+)",
    "twitter":   r"(?:twitter|x)\.com/([^\"'/?\s]+)",
    "youtube":   r"youtube\.com/(?:channel|@|c)/([^\"'/?\s]+)",
    "tiktok":    r"tiktok\.com/@([^\"'/?\s]+)",
}

EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
CONTACT_PATHS = ["/", "/contacto", "/contact", "/nosotros", "/about", "/acerca"]


def _fetch_page(url: str) -> str:
    try:
        r = safe_get(url, allow_redirects=True)
        return r.text
    except Exception:
        return ""


def _extract_emails(html: str) -> list[str]:
    found: set[str] = set()
    for m in re.finditer(r'href="mailto:([^"]+)"', html, re.IGNORECASE):
        found.add(m.group(1).strip().lower())
    for m in EMAIL_PATTERN.finditer(html):
        email = m.group(0).lower()
        if not email.endswith((".png", ".jpg", ".gif", ".svg", ".css", ".js")):
            found.add(email)
    return sorted(found)[:5]


def _extract_phones(html: str) -> list[str]:
    found: set[str] = set()
    for m in re.finditer(r'href="tel:([^"]+)"', html, re.IGNORECASE):
        found.add(m.group(1).strip())
    soup = BeautifulSoup(html, "lxml")
    for m in re.finditer(r'\+?[\d][\d\s\-().]{6,18}[\d]', soup.get_text(" ")):
        candidate = m.group(0).strip()
        if 7 <= len(re.sub(r'\D', '', candidate)) <= 15:
            found.add(candidate)
    return sorted(found)[:3]


def _extract_social(html: str) -> dict:
    return {
        platform: m.group(0)
        for platform, pattern in SOCIAL_PATTERNS.items()
        if (m := re.search(pattern, html, re.IGNORECASE))
    }


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

    # Fetch pages and join — use list to avoid O(n²) string concatenation
    pages: list[str] = []
    for path in CONTACT_PATHS:
        pages.append(_fetch_page(base.rstrip("/") + path))
    all_html = "".join(pages)

    emails = _extract_emails(all_html)
    phones = _extract_phones(all_html)
    social = _extract_social(all_html)
    contact_name = _extract_contact_name(all_html)

    issues: list[Issue] = []
    if not emails:
        issues.append(Issue(severity=Severity.info, message="No se encontraron emails en el sitio"))
    if not phones:
        issues.append(Issue(severity=Severity.info, message="No se encontró número de teléfono visible"))

    return ContactResult(emails=emails, phones=phones, social=social, contact_name=contact_name, issues=issues)
