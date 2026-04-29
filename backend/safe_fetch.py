from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

import requests

from backend.config import HEADERS, REQUEST_TIMEOUT

_BLOCKED_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),   # AWS metadata + link-local
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),     # shared address space
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]

_ALLOWED_SCHEMES = {"http", "https"}


def assert_safe_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise ValueError(f"Esquema no permitido: {parsed.scheme!r}. Solo se aceptan http y https.")

    hostname = parsed.hostname
    if not hostname:
        raise ValueError("La URL no contiene un hostname válido.")

    try:
        ip_str = socket.gethostbyname(hostname)
        ip = ipaddress.ip_address(ip_str)
    except socket.gaierror:
        raise ValueError(f"No se puede resolver el dominio: {hostname!r}")
    except ValueError:
        raise ValueError(f"IP inválida devuelta para {hostname!r}")

    for network in _BLOCKED_NETWORKS:
        if ip in network:
            raise ValueError(f"El dominio apunta a un rango de IP no permitido ({ip}).")


def safe_get(url: str, **kwargs) -> requests.Response:
    assert_safe_url(url)
    kwargs.setdefault("headers", HEADERS)
    kwargs.setdefault("timeout", REQUEST_TIMEOUT)
    kwargs.setdefault("allow_redirects", True)
    return requests.get(url, **kwargs)


def safe_head(url: str, **kwargs) -> requests.Response:
    assert_safe_url(url)
    kwargs.setdefault("headers", HEADERS)
    kwargs.setdefault("timeout", REQUEST_TIMEOUT)
    kwargs.setdefault("allow_redirects", True)
    return requests.head(url, **kwargs)
