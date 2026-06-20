"""Phase 05 tests — B-roll module (Pexels + cache + fallback).

NO real network: the HTTP seam (`_http_get_json`/`_http_get_bytes`) and the LLM
keyword call are patched. Asserts cache behaviour + graceful None fallbacks +
consecutive-keyword dedupe. Never asserts on downloaded image bytes (Pexels
results drift — R5); only on cache/structure.
"""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from PIL import Image

import apps.video.frames.broll as broll
from apps.video.frames.composition import DialogueSegment


def _jpeg_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), (120, 80, 40)).save(buf, "JPEG")
    return buf.getvalue()


def _llm(keyword: str | list[str]) -> AsyncMock:
    m = AsyncMock()
    if isinstance(keyword, list):
        m.complete_text = AsyncMock(side_effect=keyword)
    else:
        m.complete_text = AsyncMock(return_value=keyword)
    return m


def _cfg(tmp_path: Path, **kw) -> broll.BrollConfig:
    return broll.BrollConfig(enable=True, cache_dir=tmp_path, **kw)


# --- _slug ----------------------------------------------------------------

def test_slug_is_filesystem_safe() -> None:
    assert broll._slug("  Hà Nội Street/Food!! ") == "h-n-i-street-food"
    assert broll._slug("../etc/passwd") == "etc-passwd"  # no traversal


# --- extract_keyword ------------------------------------------------------

@pytest.mark.asyncio
async def test_extract_keyword_strips_and_trims() -> None:
    kw = await broll.extract_keyword("Phở Hà Nội", _llm('  "hanoi street food".  '))
    assert kw == "hanoi street food"


@pytest.mark.asyncio
async def test_extract_keyword_llm_error_returns_empty() -> None:
    llm = AsyncMock()
    llm.complete_text = AsyncMock(side_effect=RuntimeError("llm down"))
    assert await broll.extract_keyword("text", llm) == ""  # no raise


@pytest.mark.asyncio
async def test_extract_keyword_blank_input() -> None:
    assert await broll.extract_keyword("   ", _llm("x")) == ""


# --- search_pexels --------------------------------------------------------

def test_search_pexels_parses_url() -> None:
    payload = {"photos": [{"src": {"large2x": "http://x/a.jpg", "large": "http://x/b.jpg"}}]}
    with patch.object(broll, "_http_get_json", return_value=payload):
        assert broll.search_pexels("food", "landscape", "key") == "http://x/a.jpg"


def test_search_pexels_empty_results_none() -> None:
    with patch.object(broll, "_http_get_json", return_value={"photos": []}):
        assert broll.search_pexels("food", "landscape", "key") is None


def test_search_pexels_missing_key_or_keyword_none() -> None:
    assert broll.search_pexels("food", "landscape", "") is None
    assert broll.search_pexels("", "landscape", "key") is None


def test_search_pexels_http_error_none() -> None:
    with patch.object(broll, "_http_get_json", side_effect=RuntimeError("429")):
        assert broll.search_pexels("food", "landscape", "key") is None


# --- security guards (H1 SSRF, H2 decompression bomb) ----------------------

def test_check_host_rejects_non_pexels() -> None:
    broll._check_host("https://images.pexels.com/photos/1/a.jpg")  # allowed
    for bad in ("http://169.254.169.254/latest/meta-data/",
                "https://evil.com/x.jpg",
                "https://images.pexels.com.evil.com/x.jpg"):
        with pytest.raises(ValueError):
            broll._check_host(bad)


def test_validate_image_rejects_oversized(monkeypatch) -> None:
    monkeypatch.setattr(broll, "_MAX_PIXELS", 16)  # 4x4 ceiling for the test
    with pytest.raises(ValueError):
        broll._validate_image(_jpeg_bytes())        # 8x8 = 64px > 16
    monkeypatch.setattr(broll, "_MAX_PIXELS", 40_000_000)
    broll._validate_image(_jpeg_bytes())            # within ceiling → ok


# --- fetch_broll_image: cache hit/miss + fallbacks ------------------------

@pytest.mark.asyncio
async def test_no_api_key_returns_none(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("PEXELS_API_KEY", raising=False)
    assert await broll.fetch_broll_image("Phở", llm=_llm("food"), cfg=_cfg(tmp_path)) is None


@pytest.mark.asyncio
async def test_cache_miss_then_hit_no_second_http(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("PEXELS_API_KEY", "testkey")
    payload = {"photos": [{"src": {"large2x": "http://x/a.jpg"}}]}
    with patch.object(broll, "_http_get_json", return_value=payload) as gj, \
         patch.object(broll, "_http_get_bytes", return_value=_jpeg_bytes()) as gb:
        r1 = await broll.fetch_broll_image("Phở", llm=_llm("food"), cfg=_cfg(tmp_path))
        assert r1 is not None and r1.exists()
        assert gj.call_count == 1 and gb.call_count == 1
        r2 = await broll.fetch_broll_image("Phở", llm=_llm("food"), cfg=_cfg(tmp_path))
        assert r2 == r1 and gj.call_count == 1 and gb.call_count == 1  # cache hit


@pytest.mark.asyncio
async def test_empty_results_returns_none(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("PEXELS_API_KEY", "testkey")
    with patch.object(broll, "_http_get_json", return_value={"photos": []}):
        assert await broll.fetch_broll_image("x", llm=_llm("nope"), cfg=_cfg(tmp_path)) is None


@pytest.mark.asyncio
async def test_bad_image_bytes_rejected(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("PEXELS_API_KEY", "testkey")
    payload = {"photos": [{"src": {"large": "http://x/b.jpg"}}]}
    with patch.object(broll, "_http_get_json", return_value=payload), \
         patch.object(broll, "_http_get_bytes", return_value=b"not-an-image"):
        assert await broll.fetch_broll_image("g", llm=_llm("garbage"), cfg=_cfg(tmp_path)) is None


@pytest.mark.asyncio
async def test_empty_keyword_skips_fetch(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("PEXELS_API_KEY", "testkey")
    with patch.object(broll, "_http_get_json") as gj:
        assert await broll.fetch_broll_image("x", llm=_llm(""), cfg=_cfg(tmp_path)) is None
        gj.assert_not_called()


# --- attach_broll: dedupe + gating ----------------------------------------

def _seg(text: str) -> DialogueSegment:
    return DialogueSegment(speaker="A", text=text, audio_path=Path("a.wav"), duration_s=1.0)


@pytest.mark.asyncio
async def test_attach_broll_consecutive_dedupe(tmp_path: Path) -> None:
    segs = [_seg("l1"), _seg("l2"), _seg("l3")]
    calls = {"n": 0}

    def fake_fetch(kw: str, cfg) -> Path:
        calls["n"] += 1
        return tmp_path / f"{broll._slug(kw)}.jpg"

    llm = _llm(["city skyline", "city skyline", "forest river"])
    with patch.object(broll, "_fetch_by_keyword", side_effect=fake_fetch):
        await broll.attach_broll(segs, llm=llm, cfg=_cfg(tmp_path))
    assert segs[0].image_path == segs[1].image_path        # same kw reused
    assert segs[2].image_path != segs[0].image_path
    assert calls["n"] == 2                                  # only 2 fetches for 3 segs


@pytest.mark.asyncio
async def test_attach_broll_disabled_is_noop(tmp_path: Path) -> None:
    segs = [_seg("l1")]
    await broll.attach_broll(segs, llm=_llm("x"), cfg=broll.BrollConfig(enable=False))
    assert segs[0].image_path is None
