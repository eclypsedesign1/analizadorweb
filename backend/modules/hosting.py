from __future__ import annotations

import socket
from datetime import datetime, timezone

import requests
import dns.resolver
import whois as whois_lib

from backend.config import IPINFO_TOKEN
from backend.models import HostingResult, Issue, Severity

MX_PROVIDERS = {
    "google": "Google Workspace", "googlemail": "Google Workspace",
    "outlook": "Microsoft 365", "hotmail": "Microsoft / Hotmail",
    "zoho": "Zoho Mail", "mailchimp": "Mailchimp",
    "sendgrid": "SendGrid", "cpanel": "cPanel / Hosting propio",
    "amazonses": "Amazon SES", "mailgun": "Mailgun", "titan": "Titan Mail",
}

ASN_PROVIDERS = {
    "AS13335": "Cloudflare", "AS16509": "Amazon AWS", "AS14618": "Amazon AWS",
    "AS15169": "Google Cloud", "AS8075": "Microsoft Azure", "AS396982": "Google Cloud",
    "AS46606": "GoDaddy", "AS26496": "GoDaddy", "AS36183": "SiteGround",
    "AS35540": "SiteGround", "AS14061": "DigitalOcean", "AS60068": "CDN77",
    "AS19551": "Incapsula / Imperva", "AS20940": "Akamai", "AS54113": "Fastly",
}


def _resolve_ip(hostname: str) -> str | None:
    try:
        return socket.gethostbyname(hostname)
    except Exception:
        return None


def _ipinfo(ip: str) -> dict:
    try:
        headers = {"Authorization": f"Bearer {IPINFO_TOKEN}"} if IPINFO_TOKEN else {}
        r = requests.get(f"https://ipinfo.io/{ip}/json", headers=headers, timeout=10)
        return r.json() if r.ok else {}
    except Exception:
        return {}


def _mx_provider(domain: str) -> str | None:
    try:
        answers = dns.resolver.resolve(domain, "MX")
        mx = str(answers[0].exchange).lower()
        for key, name in MX_PROVIDERS.items():
            if key in mx:
                return name
        return mx.split(".")[-2] if "." in mx else mx
    except Exception:
        return None


def _whois_dates(domain: str) -> tuple[str | None, str | None]:
    try:
        w = whois_lib.whois(domain)
        def fmt(d):
            if isinstance(d, list):
                d = d[0]
            return d.strftime("%Y-%m-%d") if isinstance(d, datetime) else str(d)[:10]
        return fmt(w.creation_date), fmt(w.expiration_date)
    except Exception:
        return None, None


def analyze(url: str) -> HostingResult:
    from urllib.parse import urlparse
    parsed = urlparse(url)
    hostname = parsed.hostname or ""
    domain = ".".join(hostname.split(".")[-2:]) if hostname.count(".") >= 2 else hostname

    issues: list[Issue] = []

    ip = _resolve_ip(hostname)
    info = _ipinfo(ip) if ip else {}
    asn = info.get("org", "")
    asn_code = asn.split(" ")[0] if asn else None
    provider = ASN_PROVIDERS.get(asn_code, " ".join(asn.split(" ")[1:]) if asn else None)

    mx_provider = _mx_provider(domain)
    registered, expires = _whois_dates(domain)

    if expires:
        try:
            days = (datetime.strptime(expires, "%Y-%m-%d") - datetime.now(timezone.utc).replace(tzinfo=None)).days
            if days < 30:
                issues.append(Issue(severity=Severity.critical, message=f"Dominio vence en {days} días", detail="Renovar urgente para no perder el dominio"))
            elif days < 90:
                issues.append(Issue(severity=Severity.warning, message=f"Dominio vence en {days} días"))
        except Exception:
            pass

    return HostingResult(
        ip=ip,
        asn=asn,
        provider=provider,
        country=info.get("country"),
        city=info.get("city"),
        mx_provider=mx_provider,
        domain_registered=registered,
        domain_expires=expires,
        issues=issues,
    )
