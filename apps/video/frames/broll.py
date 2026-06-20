"""B-roll background images for frames mode (Pexels + local cache).

Vietnamese dialogue text → English visual keyword (via the existing
``LLMScriptGenerator``) → Pexels photo search → download → cache by slug.

Every failure path returns ``None`` so the caller falls back to the flat
background — a B-roll problem NEVER breaks a video job (R3). The disk cache
makes results deterministic + offline after the first fetch (R5).
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

import httpx

from apps.video.frames.composition import DialogueSegment

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_CACHE = _PROJECT_ROOT / "output" / "studio" / "video" / "broll-cache"
_PEXELS_SEARCH = "https://api.pexels.com/v1/search"
# Only ever download from Pexels image hosts (SSRF guard — the URL comes from an
# external API response, so never let it point the server at arbitrary hosts).
_ALLOWED_IMG_HOSTS = ("images.pexels.com",)
_MAX_PIXELS = 40_000_000  # ~40MP decoded-size ceiling (decompression-bomb guard)
_KEYWORD_SYSTEM = (
    "You turn a line of Vietnamese narration into ONE short English search "
    "phrase (1-4 words) naming a concrete, filmable visual scene for stock "
    "footage. Output ONLY the phrase — no quotes, punctuation, or explanation."
)


@dataclass
class BrollConfig:
    """Tunables for B-roll fetching (defaults are safe + offline-friendly)."""

    enable: bool = False
    orientation: str = "landscape"
    cache_dir: Path = field(default_factory=lambda: _DEFAULT_CACHE)
    max_bytes: int = 12 * 1024 * 1024
    timeout_s: float = 15.0


def _slug(keyword: str) -> str:
    """Filesystem-safe cache key (also blocks path traversal)."""
    return re.sub(r"[^a-z0-9]+", "-", (keyword or "").strip().lower()).strip("-")[:60]


def cache_path(keyword: str, cache_dir: Path, orientation: str) -> Path:
    return Path(cache_dir) / f"{_slug(keyword)}-{orientation}.jpg"


# --- HTTP seam (patched in tests; no real network is hit there) ------------
def _http_get_json(url: str, headers: dict, params: dict, timeout: float) -> dict:
    r = httpx.get(url, headers=headers, params=params, timeout=timeout)
    r.raise_for_status()
    return r.json()


def _check_host(url: str) -> None:
    """Reject any URL whose host isn't a Pexels image host (SSRF guard)."""
    host = urlparse(url).netloc.lower()
    if not any(host == h or host.endswith("." + h) for h in _ALLOWED_IMG_HOSTS):
        raise ValueError(f"disallowed image host: {host!r}")


def _http_get_bytes(url: str, timeout: float, max_bytes: int) -> bytes:
    _check_host(url)
    # follow_redirects=False: Pexels image URLs are direct, and a redirect could
    # bounce the fetch to an internal/disallowed host (SSRF).
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


def _validate_image(data: bytes) -> None:
    """Raise if bytes aren't a decodable image OR exceed the pixel ceiling.

    ``max_bytes`` caps the *compressed* size; this guards the *decoded* size so a
    small file can't decode to gigapixels (decompression bomb).
    """
    from io import BytesIO

    from PIL import Image

    Image.open(BytesIO(data)).verify()  # structural check (consumes the stream)
    w, h = Image.open(BytesIO(data)).size  # re-open: verify() invalidates the object
    if w * h > _MAX_PIXELS:
        raise ValueError(f"image too large: {w}x{h} px")


async def extract_keyword(text: str, llm) -> str:
    """VN text → one English visual keyword. Returns '' on any failure."""
    if not (text and text.strip()):
        return ""
    try:
        raw = await llm.complete_text(text.strip()[:500], system=_KEYWORD_SYSTEM)
        return " ".join((raw or "").split()).strip().strip('".')[:60]
    except Exception as e:  # noqa: BLE001 — degrade, never break the job
        logger.warning("broll keyword extraction failed: %s", e)
        return ""


def search_pexels(keyword: str, orientation: str, api_key: str) -> str | None:
    """Best Pexels photo URL for ``keyword``, or None on any failure/empty."""
    if not keyword or not api_key:
        return None
    try:
        data = _http_get_json(
            _PEXELS_SEARCH,
            headers={"Authorization": api_key},
            params={"query": keyword, "per_page": 1, "orientation": orientation},
            timeout=10.0,
        )
        photos = data.get("photos") or []
        if not photos:
            return None
        src = photos[0].get("src") or {}
        return src.get("large2x") or src.get("large") or src.get("original")
    except Exception as e:  # noqa: BLE001
        logger.warning("pexels search failed for %r: %s", keyword, e)
        return None


def _fetch_by_keyword(keyword: str, cfg: BrollConfig) -> Path | None:
    """Blocking cache→search→download→validate→cache. Returns Path|None, never raises."""
    try:
        if not keyword:
            return None
        dest = cache_path(keyword, cfg.cache_dir, cfg.orientation)
        if dest.exists() and dest.stat().st_size > 0:
            return dest  # cache hit — no network
        api_key = os.environ.get("PEXELS_API_KEY", "")
        if not api_key:
            logger.warning("PEXELS_API_KEY not set — B-roll disabled (flat bg)")
            return None
        url = search_pexels(keyword, cfg.orientation, api_key)
        if not url:
            return None
        data = _http_get_bytes(url, cfg.timeout_s, cfg.max_bytes)
        _validate_image(data)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        logger.info("broll cached: %r → %s", keyword, dest.name)
        return dest
    except Exception as e:  # noqa: BLE001
        logger.warning("broll fetch failed for %r: %s", keyword, e)
        return None


async def fetch_broll_image(text: str, *, llm, cfg: BrollConfig) -> Path | None:
    """Orchestrator: VN text → keyword → cached/downloaded image Path, or None."""
    keyword = await extract_keyword(text, llm)
    if not keyword:
        return None
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _fetch_by_keyword, keyword, cfg)


async def attach_broll(segments: list[DialogueSegment], *, llm, cfg: BrollConfig) -> None:
    """Set ``seg.image_path`` per segment. Consecutive identical keywords reuse
    one image (R6 — avoids jarring swaps). Failures leave image_path=None."""
    if not cfg.enable or not segments:
        return
    loop = asyncio.get_running_loop()
    last_kw: str | None = None
    last_path: Path | None = None
    for seg in segments:
        keyword = await extract_keyword(seg.text, llm)
        if keyword and keyword == last_kw:
            seg.image_path = last_path
            continue
        path = (
            await loop.run_in_executor(None, _fetch_by_keyword, keyword, cfg)
            if keyword else None
        )
        seg.image_path = path
        last_kw, last_path = keyword, path
