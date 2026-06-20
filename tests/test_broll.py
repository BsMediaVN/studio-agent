"""Phase 05 tests — B-roll module (keyless Openverse + optional Pexels + cache).

NO real network: the provider HTTP seam (`broll_providers._get_json` /
`broll.download_bytes`) and the LLM keyword call are patched. Asserts cache
behaviour + graceful None fallbacks + consecutive-keyword dedupe + SSRF guard.
Never asserts on downloaded image bytes (results drift — R5).
"""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from PIL import Image

import apps.video.frames.broll as broll
import apps.video.frames.broll_providers as prov
from apps.video.frames.composition import DialogueSegment


def _jpeg_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), (120, 80, 40)).save(buf, "JPEG")
    return buf.getvalue()


def _llm(keyword: str | list[str]) -> AsyncMock:
    m = AsyncMock()
    m.complete_text = AsyncMock(
        side_effect=keyword if isinstance(keyword, list) else None,
        return_value=None if isinstance(keyword, list) else keyword,
    )
    return m


def _cfg(tmp_path: Path, **kw) -> broll.BrollConfig:
    kw.setdefault("enable", True)
    return broll.BrollConfig(cache_dir=tmp_path, **kw)


# --- _slug ----------------------------------------------------------------

def test_slug_is_filesystem_safe() -> None:
    assert broll._slug("  Hà Nội Street/Food!! ") == "h-n-i-street-food"
    assert broll._slug("../etc/passwd") == "etc-passwd"  # no traversal


# --- extract_keyword(s) ---------------------------------------------------

@pytest.mark.asyncio
async def test_extract_keyword_strips_and_trims() -> None:
    assert await broll.extract_keyword("Phở", _llm('  "hanoi food".  ')) == "hanoi food"


@pytest.mark.asyncio
async def test_extract_keyword_llm_error_returns_empty() -> None:
    llm = AsyncMock()
    llm.complete_text = AsyncMock(side_effect=RuntimeError("down"))
    assert await broll.extract_keyword("text", llm) == ""


@pytest.mark.asyncio
async def test_extract_keywords_batch_parses_numbered() -> None:
    llm = _llm("1. city skyline\n2. forest river\n")  # line 3 missing → ''
    out = await broll.extract_keywords(["a", "b", "c"], llm)
    assert out == ["city skyline", "forest river", ""]
    assert llm.complete_text.call_count == 1  # ONE call for all lines (M2)


@pytest.mark.asyncio
async def test_extract_keywords_batch_error_returns_blanks() -> None:
    llm = AsyncMock()
    llm.complete_text = AsyncMock(side_effect=RuntimeError("down"))
    assert await broll.extract_keywords(["a", "b"], llm) == ["", ""]


# --- providers: search parsing + dispatch ---------------------------------

def test_search_openverse_parses_url() -> None:
    payload = {"results": [{"url": "https://live.staticflickr.com/x.jpg"}]}
    with patch.object(prov, "_get_json", return_value=payload):
        assert prov.search_openverse("food", "landscape", 10.0) == "https://live.staticflickr.com/x.jpg"


def test_search_pexels_parses_url() -> None:
    payload = {"photos": [{"src": {"large2x": "https://images.pexels.com/a.jpg"}}]}
    with patch.object(prov, "_get_json", return_value=payload):
        assert prov.search_pexels("food", "landscape", "key", 10.0) == "https://images.pexels.com/a.jpg"


def test_search_image_dispatch_and_safety() -> None:
    with patch.object(prov, "search_openverse", return_value="u1") as ov:
        assert prov.search_image("k", provider="openverse", orientation="landscape", api_key=None) == "u1"
        ov.assert_called_once()
    # unknown provider → None, no raise
    assert prov.search_image("k", provider="bogus", orientation="landscape", api_key=None) is None
    # underlying error → None (never raises out)
    with patch.object(prov, "search_openverse", side_effect=RuntimeError("boom")):
        assert prov.search_image("k", provider="openverse", orientation="landscape", api_key=None) is None


def test_provider_needs_key() -> None:
    assert prov.provider_needs_key("openverse") is None     # keyless
    assert prov.provider_needs_key("pexels") == "PEXELS_API_KEY"


# --- SSRF guard -----------------------------------------------------------

def test_assert_public_url_blocks_internal() -> None:
    prov._assert_public_url("https://8.8.8.8/a.jpg")  # public IP literal → ok
    for bad in ("http://127.0.0.1/x", "http://169.254.169.254/meta",
                "http://10.0.0.5/x", "ftp://8.8.8.8/x"):
        with pytest.raises(ValueError):
            prov._assert_public_url(bad)


# --- fetch: cache hit/miss + fallbacks (default keyless provider) ----------

@pytest.mark.asyncio
async def test_keyless_cache_miss_then_hit(tmp_path: Path) -> None:
    with patch.object(broll, "search_image", return_value="https://h/a.jpg") as si, \
         patch.object(broll, "download_bytes", return_value=_jpeg_bytes()) as db:
        r1 = await broll.fetch_broll_image("Phở", llm=_llm("food"), cfg=_cfg(tmp_path))
        assert r1 is not None and r1.exists()
        assert si.call_count == 1 and db.call_count == 1
        r2 = await broll.fetch_broll_image("Phở", llm=_llm("food"), cfg=_cfg(tmp_path))
        assert r2 == r1 and si.call_count == 1 and db.call_count == 1  # cache hit, no net


@pytest.mark.asyncio
async def test_pexels_without_key_returns_none(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("PEXELS_API_KEY", raising=False)
    with patch.object(broll, "search_image") as si:
        r = await broll.fetch_broll_image("Phở", llm=_llm("food"),
                                          cfg=_cfg(tmp_path, provider="pexels"))
        assert r is None
        si.assert_not_called()  # short-circuits before searching


@pytest.mark.asyncio
async def test_empty_search_result_returns_none(tmp_path: Path) -> None:
    with patch.object(broll, "search_image", return_value=None):
        assert await broll.fetch_broll_image("x", llm=_llm("kw"), cfg=_cfg(tmp_path)) is None


@pytest.mark.asyncio
async def test_bad_image_bytes_rejected(tmp_path: Path) -> None:
    with patch.object(broll, "search_image", return_value="https://h/b.jpg"), \
         patch.object(broll, "download_bytes", return_value=b"not-an-image"):
        assert await broll.fetch_broll_image("g", llm=_llm("kw"), cfg=_cfg(tmp_path)) is None


@pytest.mark.asyncio
async def test_empty_keyword_skips_fetch(tmp_path: Path) -> None:
    with patch.object(broll, "search_image") as si:
        assert await broll.fetch_broll_image("x", llm=_llm(""), cfg=_cfg(tmp_path)) is None
        si.assert_not_called()


def test_validate_image_rejects_oversized(monkeypatch) -> None:
    monkeypatch.setattr(broll, "_MAX_PIXELS", 16)  # 4x4 ceiling
    with pytest.raises(ValueError):
        broll._validate_image(_jpeg_bytes())        # 8x8 = 64px > 16
    monkeypatch.setattr(broll, "_MAX_PIXELS", 40_000_000)
    broll._validate_image(_jpeg_bytes())            # within ceiling → ok


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

    llm = _llm("1. city skyline\n2. city skyline\n3. forest river")  # ONE batched call
    with patch.object(broll, "_fetch_by_keyword", side_effect=fake_fetch):
        await broll.attach_broll(segs, llm=llm, cfg=_cfg(tmp_path))
    assert llm.complete_text.call_count == 1               # batched, not 3 calls
    assert segs[0].image_path == segs[1].image_path        # same kw reused
    assert segs[2].image_path != segs[0].image_path
    assert calls["n"] == 2                                  # only 2 fetches for 3 segs


@pytest.mark.asyncio
async def test_attach_broll_disabled_is_noop(tmp_path: Path) -> None:
    segs = [_seg("l1")]
    await broll.attach_broll(segs, llm=_llm("x"), cfg=broll.BrollConfig(enable=False))
    assert segs[0].image_path is None
