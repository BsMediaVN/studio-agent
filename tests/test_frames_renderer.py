"""Phase 01 tests — FramesRenderer (HyperFrames CLI wrapper).

Validates: availability probe, render produces an MP4 with embedded audio, and
same-machine determinism (identical video+audio stream hashes across two runs).
Skipped automatically where HyperFrames isn't installed (node>=22/ffmpeg/binary).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from apps.video.frames.renderer import JOBS_DIR, FramesRenderer

_AVAILABLE = FramesRenderer.is_available()
pytestmark = pytest.mark.skipif(
    not _AVAILABLE, reason="HyperFrames not installed (run npm install in project/)"
)

_INDEX_HTML = """<!doctype html>
<html lang="vi" data-resolution="landscape">
  <head>
    <meta charset="UTF-8" />
    <script src="assets/lib/gsap.min.js"></script>
    <style>
      html, body { width: 1920px; height: 1080px; margin: 0; background: #0a0e14; }
      #t { position: absolute; top: 460px; width: 100%; text-align: center;
           font-size: 96px; color: #2dd4bf; font-family: sans-serif; }
    </style>
  </head>
  <body>
    <div id="root" data-composition-id="main" data-start="0" data-duration="2"
         data-width="1920" data-height="1080">
      <div id="t" class="clip" data-start="0" data-duration="2" data-track-index="1">Test</div>
      <audio id="voice" class="clip" data-start="0" data-duration="2" data-track-index="0"
             src="assets/tone.wav"></audio>
    </div>
    <script>
      window.__timelines = window.__timelines || {};
      const tl = gsap.timeline({ paused: true });
      tl.from("#t", { opacity: 0, duration: 0.5 }, 0);
      window.__timelines["main"] = tl;
    </script>
  </body>
</html>
"""


def _build_job(name: str) -> Path:
    """Write a self-contained fixture composition into project/jobs/<name>/."""
    job = JOBS_DIR / name
    if job.exists():
        shutil.rmtree(job)
    (job / "assets" / "lib").mkdir(parents=True)
    # vendor GSAP into the job so it is self-contained (no ../ escapes)
    shutil.copy2(
        FramesRenderer.project_dir() / "assets" / "lib" / "gsap.min.js",
        job / "assets" / "lib" / "gsap.min.js",
    )
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
         "-ar", "48000", "-ac", "1", str(job / "assets" / "tone.wav")],
        check=True, capture_output=True,
    )
    (job / "meta.json").write_text(json.dumps({"id": name, "name": name}))
    (job / "hyperframes.json").write_text(
        (FramesRenderer.project_dir() / "hyperframes.json").read_text()
    )
    (job / "index.html").write_text(_INDEX_HTML)
    return job


def _stream_hash(mp4: Path, kind: str) -> str:
    """ffmpeg streamhash of a single stream ('v' video / 'a' audio)."""
    out = subprocess.run(
        ["ffmpeg", "-i", str(mp4), "-map", f"0:{kind}", "-f", "streamhash",
         "-hash", "sha256", "-"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return out


def test_is_available() -> None:
    assert FramesRenderer.is_available() is True


@pytest.mark.asyncio
async def test_render_produces_mp4_with_audio(tmp_path: Path) -> None:
    job = _build_job("pytest-render")
    try:
        renderer = FramesRenderer(fps=30, workers=4)
        mp4 = await renderer.render(job, tmp_path)
        assert mp4.exists() and mp4.stat().st_size > 0
        # both a video and an audio stream present
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type",
             "-of", "default=nw=1:nk=1", str(mp4)],
            capture_output=True, text=True, check=True,
        ).stdout.split()
        assert "video" in probe and "audio" in probe
    finally:
        shutil.rmtree(job, ignore_errors=True)


@pytest.mark.asyncio
async def test_same_machine_determinism(tmp_path: Path) -> None:
    job = _build_job("pytest-determinism")
    try:
        renderer = FramesRenderer(fps=30, workers=4)
        mp4_a = await renderer.render(job, tmp_path / "a")
        mp4_b = await renderer.render(job, tmp_path / "b")
        assert _stream_hash(mp4_a, "v") == _stream_hash(mp4_b, "v")
        assert _stream_hash(mp4_a, "a") == _stream_hash(mp4_b, "a")
    finally:
        shutil.rmtree(job, ignore_errors=True)


@pytest.mark.asyncio
async def test_missing_composition_raises(tmp_path: Path) -> None:
    renderer = FramesRenderer()
    with pytest.raises(FileNotFoundError):
        await renderer.render(JOBS_DIR / "does-not-exist", tmp_path)
