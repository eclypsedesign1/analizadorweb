import re
import requests
from bs4 import BeautifulSoup
from backend.config import HEADERS, REQUEST_TIMEOUT
from backend.models import CMSResult, Issue, Severity


CMS_SIGNATURES = {
    "WordPress": [
        r"/wp-content/", r"/wp-includes/", r'name="generator" content="WordPress',
        r"wp-embed.min.js",
    ],
    "Joomla": [
        r"/media/jui/", r'content="Joomla!', r"/components/com_",
    ],
    "Drupal": [
        r'content="Drupal', r"/sites/default/files/", r"Drupal.settings",
    ],
    "Shopify": [
        r"cdn.shopify.com", r"Shopify.theme", r"/collections/",
    ],
    "Wix": [
        r"static.wixstatic.com", r"wix-warmup-data",
    ],
    "Squarespace": [
        r"static.squarespace.com", r"squarespace-cdn",
    ],
    "Webflow": [
        r"assets.website-files.com", r"webflow.com/",
    ],
    "Next.js": [
        r"/_next/static/", r'id="__NEXT_DATA__"',
    ],
    "Prestashop": [
        r"/themes/classic/", r"prestashop",
    ],
}

LATEST_WP = "6.7"


def _fetch(url: str) -> tuple[str | None, dict]:
    try:
        r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        return r.text, r.headers
    except Exception:
        return None, {}


def _detect_wp_version(html: str, base_url: str) -> str | None:
    patterns = [
        r'<meta name="generator" content="WordPress ([0-9.]+)"',
        r"wp-includes/js/wp-embed\.min\.js\?ver=([0-9.]+)",
        r"wp-includes/css/dist/block-library/style\.min\.css\?ver=([0-9.]+)",
    ]
    for p in patterns:
        m = re.search(p, html, re.IGNORECASE)
        if m:
            return m.group(1)

    for path in ["/feed/", "/wp-login.php"]:
        text, _ = _fetch(base_url.rstrip("/") + path)
        if text:
            m = re.search(r"WordPress ([0-9.]+)", text)
            if m:
                return m.group(1)
    return None


def _detect_wp_theme(html: str) -> str | None:
    m = re.search(r"/wp-content/themes/([^/\"']+)", html)
    return m.group(1) if m else None


def _detect_wp_plugins(html: str, base_url: str) -> list[dict]:
    plugins = {}
    for m in re.finditer(r"/wp-content/plugins/([^/\"']+)/", html):
        slug = m.group(1)
        plugins[slug] = {"slug": slug, "version": None, "update_available": False}

    for slug in list(plugins.keys())[:10]:
        try:
            api_url = f"https://api.wordpress.org/plugins/info/1.0/{slug}.json"
            r = requests.get(api_url, timeout=8)
            if r.ok:
                data = r.json()
                plugins[slug]["latest_version"] = data.get("version")
        except Exception:
            pass

    return list(plugins.values())


def analyze(url: str) -> CMSResult:
    base = url.rstrip("/")
    html, headers = _fetch(base)
    issues: list[Issue] = []

    if html is None:
        return CMSResult(issues=[Issue(severity=Severity.critical, message="No se pudo acceder al sitio")])

    detected_cms = None
    for cms_name, sigs in CMS_SIGNATURES.items():
        if any(re.search(sig, html, re.IGNORECASE) for sig in sigs):
            detected_cms = cms_name
            break

    if detected_cms is None:
        detected_cms = "HTML estático / Desconocido"

    result = CMSResult(cms=detected_cms)

    if detected_cms == "WordPress":
        version = _detect_wp_version(html, base)
        result.version = version
        result.theme = _detect_wp_theme(html)
        result.plugins = _detect_wp_plugins(html, base)

        if version:
            try:
                v_parts = [int(x) for x in version.split(".")]
                l_parts = [int(x) for x in LATEST_WP.split(".")]
                if v_parts < l_parts:
                    issues.append(Issue(
                        severity=Severity.critical,
                        message=f"WordPress {version} está desactualizado",
                        detail=f"La última versión es {LATEST_WP}. Las versiones antiguas tienen vulnerabilidades conocidas."
                    ))
            except ValueError:
                pass

        outdated_plugins = [p for p in result.plugins if p.get("latest_version") and p.get("version") and p["version"] != p["latest_version"]]
        if outdated_plugins:
            issues.append(Issue(
                severity=Severity.critical,
                message=f"{len(outdated_plugins)} plugins sin actualizar",
                detail=", ".join(p["slug"] for p in outdated_plugins[:5])
            ))
        elif result.plugins:
            issues.append(Issue(
                severity=Severity.info,
                message=f"{len(result.plugins)} plugins detectados"
            ))

    result.issues = issues
    return result
