"""Image-search providers for B-roll + the network/SSRF layer.

Keyless-first: ``openverse`` (Creative Commons, no API key) is the default so the
feature works for everyone out of the box; ``pexels`` is optional (needs a key).
Split from ``broll.py`` so the networking/provider code stays self-contained.

Security: download URLs come from external APIs and (for Openverse) point at
arbitrary third-party hosts, so every fetched URL is checked to resolve to a
PUBLIC IP (blocks SSRF to localhost / cloud-metadata / private ranges), redirects
are disabled, and content-type is enforced.
"""

from __future__ import annotations

import ipaddress
import logging
import socket
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

_PEXELS_SEARCH = "https://api.pexels.com/v1/search"
_OPENVERSE_SEARCH = "https://api.openverse.org/v1/images/"
# Provider → env var holding its key (absent → keyless provider).
PROVIDER_KEY_ENV = {"pexels": "PEXELS_API_KEY"}
# Openverse aspect_ratio values keyed by our orientation names.
_OV_ASPECT = {"landscape": "wide", "portrait": "tall", "square": "square"}


def provider_needs_key(provider: str) -> str | None:
    """Env-var name the provider requires, or None if it's keyless."""
    return PROVIDER_KEY_ENV.get(provider)


def _assert_public_url(url: str) -> None:
    """Raise unless ``url`` is http(s) and resolves only to public IPs (SSRF guard)."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError(f"unsupported URL: {url!r}")
    infos = socket.getaddrinfo(parsed.hostname, parsed.port or 443, proto=socket.IPPROTO_TCP)
    for *_, sockaddr in infos:
        ip = ipaddress.ip_address(sockaddr[0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            raise ValueError(f"non-public address for host {parsed.hostname!r}: {ip}")


def _get_json(url: str, *, headers: dict | None, params: dict, timeout: float) -> dict:
    r = httpx.get(url, headers=headers or {}, params=params, timeout=timeout)
    r.raise_for_status()
    return r.json()


def search_pexels(keyword: str, orientation: str, api_key: str, timeout: float) -> str | None:
    if not (keyword and api_key):
        return None
    data = _get_json(
        _PEXELS_SEARCH, headers={"Authorization": api_key},
        params={"query": keyword, "per_page": 1, "orientation": orientation},
        timeout=timeout,
    )
    photos = data.get("photos") or []
    if not photos:
        return None
    src = photos[0].get("src") or {}
    return src.get("large2x") or src.get("large") or src.get("original")


def search_openverse(keyword: str, orientation: str, timeout: float) -> str | None:
    """Creative-Commons image URL via Openverse — no API key required."""
    if not keyword:
        return None
    data = _get_json(
        _OPENVERSE_SEARCH, headers={"User-Agent": "VietVoiceStudio/1.0 (B-roll)"},
        params={"q": keyword, "page_size": 1,
                "aspect_ratio": _OV_ASPECT.get(orientation, "wide")},
        timeout=timeout,
    )
    results = data.get("results") or []
    if not results:
        return None
    return results[0].get("url") or results[0].get("thumbnail")


def search_image(keyword: str, *, provider: str, orientation: str,
                 api_key: str | None, timeout: float = 10.0) -> str | None:
    """Dispatch to the configured provider. Returns an image URL or None (never raises)."""
    try:
        if provider == "pexels":
            return search_pexels(keyword, orientation, api_key or "", timeout)
        if provider == "openverse":
            return search_openverse(keyword, orientation, timeout)
        logger.warning("unknown B-roll provider %r", provider)
        return None
    except Exception as e:  # noqa: BLE001 — degrade to no-image
        logger.warning("%s search failed for %r: %s", provider, keyword, e)
        return None


def download_bytes(url: str, timeout: float, max_bytes: int) -> bytes:
    """Download an image URL → bytes. SSRF-checked, no redirects, size-capped."""
    _assert_public_url(url)
    with httpx.stream("GET", url, timeout=timeout, follow_redirects=False) as r:
        r.raise_for_status()
        ctype = r.headers.get("content-type", "")
        if not ctype.startswith("image/"):
            raise ValueError(f"not an image: content-type={ctype!r}")
        buf = bytearray()
        for chunk in r.iter_bytes():
            buf += chunk
            if len(buf) > max_bytes:
                raise ValueError("image exceeds max_bytes")
        return bytes(buf)
