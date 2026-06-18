"""Composition builder — dialogue segments → a valid HyperFrames index.html.

Multi-character v1: one ``<audio>`` per line sequenced at cumulative offsets,
with a per-speaker card + line-level lower-third caption. Three fixed tracks
(audio / caption / card) so same-track clips never overlap. Deterministic
(no Date.now / Math.random), offline (vendored GSAP, local relative asset
paths), and passes ``hyperframes lint``.

``build_composition`` is pure (testable, byte-deterministic). ``assemble_job``
does the IO: builds a self-contained job dir the renderer can consume directly.
"""

from __future__ import annotations

import html
import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path

# Track indices — distinct tracks avoid same-track overlap (lint rule).
_TRACK_AUDIO = 0
_TRACK_CAPTION = 1
_TRACK_CARD = 2

# Deterministic avatar palette (indexed by speaker order — no hashing on text).
_AVATAR_COLORS = ["#2dd4bf", "#60a5fa", "#f472b6", "#fbbf24", "#a78bfa", "#34d399"]


@dataclass
class DialogueSegment:
    """One spoken line with its own rendered audio."""

    speaker: str
    text: str
    audio_path: Path
    duration_s: float
    gender: str = "F"


@dataclass
class CompositionConfig:
    width: int = 1920
    height: int = 1080
    fps: int = 30
    gap_s: float = 0.15  # pause inserted between consecutive lines
    title: str = "VietVoice Studio"
    accent: str = "#2dd4bf"
    bg: str = "#0a0e14"
    fg: str = "#e6f1ff"
    # Inter is in HyperFrames' auto-resolved font set (bundled, offline) and
    # matches the brand; custom families (e.g. -apple-system) fail lint.
    font_family: str = "Inter, sans-serif"


@dataclass
class _Placed:
    seg: DialogueSegment
    index: int
    start: float
    duration: float
    color: str


def _place(segments: list[DialogueSegment], cfg: CompositionConfig) -> tuple[list[_Placed], float]:
    """Assign each segment a start offset; return (placed, total_duration)."""
    placed: list[_Placed] = []
    offset = 0.0
    speakers: dict[str, str] = {}
    for i, seg in enumerate(segments):
        if seg.speaker not in speakers:
            speakers[seg.speaker] = _AVATAR_COLORS[len(speakers) % len(_AVATAR_COLORS)]
        dur = round(float(seg.duration_s), 3)
        placed.append(_Placed(seg, i, round(offset, 3), dur, speakers[seg.speaker]))
        offset += dur + cfg.gap_s
    total = round(offset - cfg.gap_s, 3) if placed else 0.0
    return placed, max(total, 0.0)


def build_composition(segments: list[DialogueSegment], cfg: CompositionConfig | None = None) -> str:
    """Render dialogue segments → a deterministic HyperFrames index.html string."""
    if not segments:
        raise ValueError("build_composition requires at least one segment")
    cfg = cfg or CompositionConfig()
    placed, total = _place(segments, cfg)

    clips: list[str] = []
    for p in placed:
        speaker = html.escape(p.seg.speaker or "")
        text = html.escape(p.seg.text or "")
        initial = html.escape((p.seg.speaker or "?").strip()[:1].upper())
        # audio (id is mandatory or HyperFrames renders silent)
        clips.append(
            f'      <audio id="audio-{p.index}" class="clip" data-start="{p.start}" '
            f'data-duration="{p.duration}" data-track-index="{_TRACK_AUDIO}" '
            f'src="assets/line-{p.index}.wav"></audio>'
        )
        # speaker card (top-left)
        clips.append(
            f'      <div class="card clip" data-start="{p.start}" data-duration="{p.duration}" '
            f'data-track-index="{_TRACK_CARD}" id="card-{p.index}">'
            f'<span class="avatar" style="background:{p.color}">{initial}</span>'
            f'<span class="name">{speaker}</span></div>'
        )
        # lower-third caption
        clips.append(
            f'      <div class="cap clip" data-start="{p.start}" data-duration="{p.duration}" '
            f'data-track-index="{_TRACK_CAPTION}" id="cap-{p.index}">{text}</div>'
        )

    title = html.escape(cfg.title)
    return _TEMPLATE.format(
        width=cfg.width, height=cfg.height, total=total, bg=cfg.bg, fg=cfg.fg,
        accent=cfg.accent, font=cfg.font_family, title=title,
        clips="\n".join(clips),
    )


def assemble_job(
    job_dir: Path,
    segments: list[DialogueSegment],
    cfg: CompositionConfig | None = None,
    *,
    gsap_src: Path,
    hyperframes_json: Path,
) -> Path:
    """Build a self-contained job dir: index.html + assets + project metadata.

    Copies vendored GSAP + each line's wav into ``assets/`` (local relative
    paths, offline). Element visibility is driven by HyperFrames' native
    ``class="clip"`` timing; GSAP is present only to register an empty timeline
    that ``hyperframes lint`` requires. Returns ``job_dir``.
    """
    cfg = cfg or CompositionConfig()
    job_dir = Path(job_dir)
    if job_dir.exists():
        shutil.rmtree(job_dir)
    (job_dir / "assets" / "lib").mkdir(parents=True)

    shutil.copy2(gsap_src, job_dir / "assets" / "lib" / "gsap.min.js")
    for i, seg in enumerate(segments):
        shutil.copy2(seg.audio_path, job_dir / "assets" / f"line-{i}.wav")

    (job_dir / "index.html").write_text(build_composition(segments, cfg), encoding="utf-8")
    (job_dir / "meta.json").write_text(json.dumps({"id": job_dir.name, "name": job_dir.name}))
    (job_dir / "hyperframes.json").write_text(Path(hyperframes_json).read_text())
    return job_dir


_TEMPLATE = """<!doctype html>
<html lang="vi" data-resolution="landscape">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width={width}, height={height}" />
    <script src="assets/lib/gsap.min.js"></script>
    <style>
      * {{ margin: 0; padding: 0; box-sizing: border-box; }}
      html, body {{ width: {width}px; height: {height}px; overflow: hidden;
        background: {bg}; color: {fg}; font-family: {font}; }}
      .brand {{ position: absolute; top: 56px; right: 72px; font-size: 34px;
        font-weight: 800; color: {accent}; letter-spacing: -1px; }}
      .card {{ position: absolute; top: 56px; left: 72px; display: flex;
        align-items: center; gap: 20px; }}
      .avatar {{ width: 76px; height: 76px; border-radius: 50%; display: flex;
        align-items: center; justify-content: center; font-size: 36px;
        font-weight: 800; color: #0a0e14; }}
      .name {{ font-size: 40px; font-weight: 700; }}
      .cap {{ position: absolute; left: 50%; transform: translateX(-50%);
        bottom: 120px; width: 78%; text-align: center; font-size: 56px;
        font-weight: 600; line-height: 1.3; text-shadow: 0 2px 12px rgba(0,0,0,.6); }}
    </style>
  </head>
  <body>
    <div id="root" data-composition-id="main" data-start="0" data-duration="{total}"
         data-width="{width}" data-height="{height}">
      <div class="brand">{title}</div>
{clips}
    </div>
    <script>
      // Empty paused timeline — required by hyperframes lint; visibility is
      // handled by class="clip" timing, so NO opacity tweens (those hide clips).
      window.__timelines = window.__timelines || {{}};
      window.__timelines["main"] = gsap.timeline({{ paused: true }});
    </script>
  </body>
</html>
"""
