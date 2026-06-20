"""Phase 02 tests — composition builder.

Pure: deterministic HTML, clip counts/attrs, HTML escaping.
Integration (needs HyperFrames): generated HTML lints clean, and a
multi-segment composition renders with audio present in EACH line's time
window (validates HyperFrames sequences multiple <audio> at offsets — R6).
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from apps.video.frames.composition import (
    CompositionConfig,
    DialogueSegment,
    assemble_job,
    build_composition,
)
from apps.video.frames.renderer import JOBS_DIR, FramesRenderer

_AVAILABLE = FramesRenderer.is_available()


def _seg(speaker: str, text: str, audio: Path, dur: float) -> DialogueSegment:
    return DialogueSegment(speaker=speaker, text=text, audio_path=audio, duration_s=dur)


def _tone(path: Path, freq: int, dur: float) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", f"sine=frequency={freq}:duration={dur}",
         "-ar", "48000", "-ac", "1", str(path)],
        check=True, capture_output=True,
    )
    return path


def _region_max_luma(mp4: Path, t: float, crop: str) -> int:
    """Max luma in a cropped region at time t (caption text is near-white)."""
    res = subprocess.run(
        ["ffmpeg", "-ss", str(t), "-i", str(mp4),
         "-vf", f"crop={crop},signalstats,metadata=print:file=-", "-frames:v", "1", "-f", "null", "-"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    ).stdout
    m = re.search(r"signalstats\.YMAX=(\d+)", res)
    return int(m.group(1)) if m else 0


def _mean_volume_db(mp4: Path, start: float, dur: float) -> float:
    out = subprocess.run(
        ["ffmpeg", "-ss", str(start), "-t", str(dur), "-i", str(mp4),
         "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True, text=True,
    ).stderr
    m = re.search(r"mean_volume:\s*(-?\d+\.?\d*)\s*dB", out)
    return float(m.group(1)) if m else -999.0


# --- pure tests (no HyperFrames needed) -----------------------------------

def test_deterministic(tmp_path: Path) -> None:
    segs = [_seg("Bình", "Xin chào", tmp_path / "a.wav", 1.2),
            _seg("Lan", "Chào bạn", tmp_path / "b.wav", 0.9)]
    assert build_composition(segs) == build_composition(segs)


def test_clip_counts_and_offsets() -> None:
    cfg = CompositionConfig(gap_s=0.2)
    segs = [_seg("A", "one", Path("a.wav"), 1.0), _seg("B", "two", Path("b.wav"), 1.5)]
    html = build_composition(segs, cfg)
    assert html.count('<audio ') == 2
    assert html.count('class="card clip"') == 2
    assert html.count('class="cap clip"') == 2
    # line 0 at 0.0; line 1 at 1.0 + gap 0.2 = 1.2
    assert 'id="audio-0" class="clip" data-start="0.0" data-duration="1.0"' in html
    assert 'id="audio-1" class="clip" data-start="1.2" data-duration="1.5"' in html
    # root duration = 1.0 + 0.2 + 1.5 = 2.7
    assert 'data-duration="2.7"' in html


def test_html_escaping() -> None:
    segs = [_seg("A&B", "<script>alert(1)</script> & co", Path("a.wav"), 1.0)]
    html = build_composition(segs)
    assert "<script>alert(1)" not in html
    assert "&lt;script&gt;" in html and "A&amp;B" in html


def test_empty_raises() -> None:
    with pytest.raises(ValueError):
        build_composition([])


# --- B-roll background track (Phase 05) -----------------------------------

def _img_seg(speaker: str, text: str, dur: float, img: str | None) -> DialogueSegment:
    return DialogueSegment(
        speaker=speaker, text=text, audio_path=Path("a.wav"),
        duration_s=dur, image_path=Path(img) if img else None,
    )


def test_no_image_path_is_unchanged() -> None:
    """image_path=None → no bg/scrim/tween artifacts (baseline preserved)."""
    html = build_composition([_seg("A", "hi", Path("a.wav"), 1.0)])
    assert 'class="bg' not in html
    assert ".scrim" not in html and "<div class=\"scrim\">" not in html
    assert ".fromTo(" not in html
    # the empty-timeline script line is intact, with nothing appended after it
    assert 'gsap.timeline({ paused: true });\n' in html


def test_image_path_emits_bg_track_and_scrim() -> None:
    html = build_composition([
        _img_seg("A", "one", 1.0, "i0.jpg"),
        _img_seg("B", "two", 1.0, "i1.jpg"),
    ])
    assert html.count('class="bg clip"') == 2
    assert html.count('data-track-index="3"') == 2
    assert 'src="assets/bg-0.jpg"' in html and 'src="assets/bg-1.jpg"' in html
    assert '<div class="scrim"></div>' in html
    assert ".bg {" in html and ".scrim {" in html
    # bg <img> painted behind brand/caption (DOM order)
    assert html.index('id="bg-0"') < html.index('class="brand"') < html.index('id="cap-0"')


def test_ken_burns_is_transform_only_no_opacity() -> None:
    html = build_composition([_img_seg("A", "one", 2.0, "i0.jpg")])
    tweens = re.findall(r"\.fromTo\([^;]*\);", html)
    assert len(tweens) == 1
    assert "opacity" not in tweens[0]           # opacity would hide the clip
    assert "scale" in tweens[0] and "xPercent" in tweens[0]
    assert "{{" not in html and "}}" not in html  # no double-brace leakage


def test_mixed_image_and_flat_segments() -> None:
    """Some segments imaged, some not → only imaged ones get a bg <img>."""
    html = build_composition([
        _img_seg("A", "withimg", 1.0, "i0.jpg"),
        _img_seg("B", "flat", 1.0, None),
    ])
    assert html.count('class="bg clip"') == 1
    assert 'id="bg-0"' in html and 'id="bg-1"' not in html


# --- integration tests (need HyperFrames) ---------------------------------

@pytest.mark.skipif(not _AVAILABLE, reason="HyperFrames not installed")
def test_generated_html_lints_clean(tmp_path: Path) -> None:
    segs = [_seg("Bình", "Câu một", _tone(tmp_path / "0.wav", 440, 1.0), 1.0),
            _seg("Lan", "Câu hai", _tone(tmp_path / "1.wav", 880, 1.0), 1.0)]
    job = assemble_job(
        JOBS_DIR / "pytest-comp-lint", segs,
        gsap_src=FramesRenderer.gsap_path(),
        hyperframes_json=FramesRenderer.project_dir() / "hyperframes.json",
    )
    try:
        res = subprocess.run(
            [str(FramesRenderer.binary_path()), "lint", str(job), "--json"],
            capture_output=True, text=True,
        )
        assert "media_missing_id" not in res.stdout
        # lint exits non-zero only on errors; warnings are fine
        assert res.returncode == 0, res.stdout[-500:]
    finally:
        __import__("shutil").rmtree(job, ignore_errors=True)


@pytest.mark.asyncio
@pytest.mark.skipif(not _AVAILABLE, reason="HyperFrames not installed")
async def test_multi_audio_sequencing(tmp_path: Path) -> None:
    """Two lines at distinct offsets → audio present in BOTH windows (R6)."""
    segs = [_seg("Bình", "Câu một", _tone(tmp_path / "0.wav", 440, 1.0), 1.0),
            _seg("Lan", "Câu hai", _tone(tmp_path / "1.wav", 880, 1.0), 1.0)]
    cfg = CompositionConfig(gap_s=0.15)
    job = assemble_job(
        JOBS_DIR / "pytest-comp-seq", segs, cfg,
        gsap_src=FramesRenderer.gsap_path(),
        hyperframes_json=FramesRenderer.project_dir() / "hyperframes.json",
    )
    try:
        mp4 = await FramesRenderer(fps=30, workers=4).render(job, tmp_path / "out")
        assert mp4.exists()
        # line 0 window [0,1.0] and line 1 window [1.15,2.15] both non-silent
        assert _mean_volume_db(mp4, 0.1, 0.8) > -45.0
        assert _mean_volume_db(mp4, 1.25, 0.8) > -45.0
        # caption must actually be visible (regression: a GSAP opacity:0 tween
        # once rendered the caption band blank). Bottom band has bright text.
        assert _region_max_luma(mp4, 0.5, "1920:220:0:860") > 150
    finally:
        __import__("shutil").rmtree(job, ignore_errors=True)
