"""B-roll background images for frames mode (keyless-first + local cache).

Vietnamese dialogue text → English visual keyword (via the existing
``LLMScriptGenerator``) → image search (default: Openverse, no API key) →
download → cache by slug.

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

from apps.video.frames.broll_keywords import extract_keyword, extract_keywords
from apps.video.frames.broll_providers import (
    download_bytes,
    provider_needs_key,
    search_image,
)
from apps.video.frames.composition import DialogueSegment

__all__ = ["BrollConfig", "attach_broll", "fetch_broll_image",
           "extract_keyword", "extract_keywords"]

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_CACHE = _PROJECT_ROOT / "output" / "studio" / "video" / "broll-cache"
_MAX_PIXELS = 40_000_000  # ~40MP decoded-size ceiling (decompression-bomb guard)


@dataclass
class BrollConfig:
    """Tunables for B-roll fetching (defaults are safe, keyless + offline-friendly)."""

    enable: bool = False
    provider: str = "openverse"  # "openverse" (no key) | "pexels" (needs key)
    orientation: str = "landscape"
    cache_dir: Path = field(default_factory=lambda: _DEFAULT_CACHE)
    max_bytes: int = 12 * 1024 * 1024
    timeout_s: float = 15.0


def _slug(keyword: str) -> str:
    """Filesystem-safe cache key (also blocks path traversal)."""
    return re.sub(r"[^a-z0-9]+", "-", (keyword or "").strip().lower()).strip("-")[:60]


def cache_path(keyword: str, cache_dir: Path, provider: str, orientation: str) -> Path:
    return Path(cache_dir) / f"{provider}-{_slug(keyword)}-{orientation}.jpg"


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


def _fetch_by_keyword(keyword: str, cfg: BrollConfig) -> Path | None:
    """Blocking cache→search→download→validate→cache. Returns Path|None, never raises."""
    try:
        if not keyword:
            return None
        dest = cache_path(keyword, cfg.cache_dir, cfg.provider, cfg.orientation)
        if dest.exists() and dest.stat().st_size > 0:
            return dest  # cache hit — no network
        key_env = provider_needs_key(cfg.provider)
        api_key = os.environ.get(key_env, "") if key_env else None
        if key_env and not api_key:
            logger.warning("%s not set — B-roll disabled (flat bg)", key_env)
            return None
        url = search_image(
            keyword, provider=cfg.provider, orientation=cfg.orientation,
            api_key=api_key, timeout=min(cfg.timeout_s, 10.0),
        )
        if not url:
            return None
        data = download_bytes(url, cfg.timeout_s, cfg.max_bytes)
        _validate_image(data)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        logger.info("broll cached (%s): %r → %s", cfg.provider, keyword, dest.name)
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
    """Set ``seg.image_path`` per segment. Keywords are extracted in ONE batched
    LLM call (M2); consecutive identical keywords reuse one image (R6 — avoids
    jarring swaps). Failures leave image_path=None (flat bg)."""
    if not cfg.enable or not segments:
        return
    keywords = await extract_keywords([s.text for s in segments], llm)
    loop = asyncio.get_running_loop()
    last_kw: str | None = None
    last_path: Path | None = None
    for seg, keyword in zip(segments, keywords):
        if keyword and keyword == last_kw:
            seg.image_path = last_path
            continue
        path = (
            await loop.run_in_executor(None, _fetch_by_keyword, keyword, cfg)
            if keyword else None
        )
        seg.image_path = path
        last_kw, last_path = keyword, path
