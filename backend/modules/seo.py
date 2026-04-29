from __future__ import annotations

import json
import re
from urllib.robotparser import RobotFileParser
from urllib.error import URLError

from bs4 import BeautifulSoup

from backend.safe_fetch import safe_get
from backend.models import SEOResult, Issue, Severity


def _fetch(url: str) -> tuple[str, int]:
    try:
        r = safe_get(url, allow_redirects=True)
        return r.text, r.status_code
    except Exception:
        return "", 0


def _robots_blocks_google(robots_url: str) -> bool:
    """Use stdlib RobotFileParser — handles multi-agent blocks correctly."""
    try:
        rp = RobotFileParser()
        rp.set_url(robots_url)
        rp.read()
        # If Googlebot cannot fetch the root, the site is effectively blocked
        return not rp.can_fetch("Googlebot", "/")
    except (URLError, Exception):
        return False


def analyze(url: str) -> SEOResult:
    from urllib.parse import urlparse
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"

    issues: list[Issue] = []
    html, status = _fetch(url)
    if not html:
        return SEOResult(issues=[Issue(severity=Severity.critical, message="No se pudo analizar el SEO del sitio")])

    soup = BeautifulSoup(html, "lxml")

    # Meta title
    title_tag = soup.find("title")
    meta_title = title_tag.get_text().strip() if title_tag else None
    title_len = len(meta_title) if meta_title else 0

    # Meta description
    meta_desc_tag = soup.find("meta", attrs={"name": re.compile(r"description", re.I)})
    meta_desc = meta_desc_tag.get("content", "").strip() if meta_desc_tag else None
    desc_len = len(meta_desc) if meta_desc else 0

    # Robots.txt
    robots_url = base + "/robots.txt"
    _, robots_code = _fetch(robots_url)
    has_robots = robots_code == 200
    blocks_google = _robots_blocks_google(robots_url) if has_robots else False

    # Sitemap
    _, sitemap_code = _fetch(base + "/sitemap.xml")
    has_sitemap = sitemap_code == 200

    # H1
    h1_count = len(soup.find_all("h1"))

    # Images alt text
    images = soup.find_all("img")
    images_total = len(images)
    images_with_alt = sum(1 for img in images if img.get("alt", "").strip())

    # Canonical
    has_canonical = soup.find("link", rel="canonical") is not None

    # Schema markup
    schema_types: list[str] = []
    for s in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(s.string or "{}")
            t = data.get("@type")
            if t:
                schema_types.append(t if isinstance(t, str) else str(t))
        except Exception:
            pass

    # OG / Twitter
    og_title = (soup.find("meta", property="og:title") or {}).get("content")
    og_image = (soup.find("meta", property="og:image") or {}).get("content")
    og_desc = (soup.find("meta", property="og:description") or {}).get("content")
    has_twitter = soup.find("meta", attrs={"name": "twitter:card"}) is not None

    # Issues
    if not meta_title:
        issues.append(Issue(severity=Severity.critical, message="Sin meta title", detail="El title es el factor SEO más importante"))
    elif title_len < 30 or title_len > 65:
        issues.append(Issue(severity=Severity.warning, message=f"Meta title fuera del rango ideal ({title_len} chars)", detail="Recomendado: 50-60 caracteres"))

    if not meta_desc:
        issues.append(Issue(severity=Severity.warning, message="Sin meta description", detail="Afecta el CTR en resultados de Google"))
    elif desc_len < 100 or desc_len > 165:
        issues.append(Issue(severity=Severity.info, message=f"Meta description fuera del rango ideal ({desc_len} chars)"))

    if not has_robots:
        issues.append(Issue(severity=Severity.info, message="Sin robots.txt"))
    elif blocks_google:
        issues.append(Issue(severity=Severity.critical, message="robots.txt bloquea a Googlebot", detail="El sitio puede no aparecer en Google"))

    if not has_sitemap:
        issues.append(Issue(severity=Severity.warning, message="Sin sitemap.xml", detail="El sitemap ayuda a Google a indexar todas las páginas"))

    if h1_count == 0:
        issues.append(Issue(severity=Severity.warning, message="Sin etiqueta H1"))
    elif h1_count > 1:
        issues.append(Issue(severity=Severity.info, message=f"Múltiples H1 ({h1_count})", detail="Se recomienda un solo H1 por página"))

    if images_total > 0 and (images_with_alt / images_total) < 0.5:
        pct = int((images_with_alt / images_total) * 100)
        issues.append(Issue(severity=Severity.warning, message=f"Solo {pct}% de imágenes tienen alt text"))

    if not schema_types:
        issues.append(Issue(severity=Severity.info, message="Sin schema markup (datos estructurados)"))

    if not og_title or not og_image:
        issues.append(Issue(severity=Severity.info, message="OG tags incompletos", detail="Cuando se comparte en redes sociales no se ve correctamente"))

    return SEOResult(
        has_meta_title=bool(meta_title),
        meta_title=meta_title,
        meta_title_length=title_len,
        has_meta_description=bool(meta_desc),
        meta_description=meta_desc,
        meta_description_length=desc_len,
        has_robots_txt=has_robots,
        robots_blocks_google=blocks_google,
        has_sitemap=has_sitemap,
        h1_count=h1_count,
        images_total=images_total,
        images_with_alt=images_with_alt,
        has_canonical=has_canonical,
        has_schema=bool(schema_types),
        schema_types=schema_types,
        og_title=og_title,
        og_image=og_image,
        og_description=og_desc,
        has_twitter_card=has_twitter,
        issues=issues,
    )
