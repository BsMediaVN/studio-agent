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

from apps.video.frames.composition_template import HTML_TEMPLATE as _TEMPLATE

# Track indices — distinct tracks avoid same-track overlap (lint rule).
_TRACK_AUDIO = 0
_TRACK_CAPTION = 1
_TRACK_CARD = 2
_TRACK_BG = 3  # background B-roll image (one <img> clip per imaged segment)

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
    # Optional B-roll background image; None → flat-bg behaviour (unchanged).
    image_path: Path | None = None


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


def _bg_fragments(placed: list[_Placed], cfg: CompositionConfig) -> tuple[str, str, str]:
    """Build (bg_block, bg_css, kenburns) for segments that carry an image.

    Returns three empty strings when no segment has an image, so the no-image
    path stays byte-identical to the flat-bg output.
    """
    imaged = [p for p in placed if p.seg.image_path is not None]
    if not imaged:
        return "", "", ""

    # bg <img> clips (track 3) FIRST in DOM (painted behind) + a static scrim.
    lines = [
        f'      <img id="bg-{p.index}" class="bg clip" data-start="{p.start}" '
        f'data-duration="{p.duration}" data-track-index="{_TRACK_BG}" '
        f'src="assets/bg-{p.index}.jpg" alt="" />'
        for p in imaged
    ]
    lines.append('      <div class="scrim"></div>')
    bg_block = "\n".join(lines) + "\n"

    # These fragments are inserted as .format() VALUES (not re-formatted), so
    # braces here are literal single braces in the output.
    bg_css = (
        f"\n      .bg {{ position: absolute; top: 0; left: 0; width: {cfg.width}px; "
        f"height: {cfg.height}px; object-fit: cover; will-change: transform; }}"
        f"\n      .scrim {{ position: absolute; inset: 0; background: linear-gradient("
        f"180deg, rgba(10,14,20,.25) 0%, rgba(10,14,20,.15) 45%, rgba(10,14,20,.85) 100%); }}"
    )

    # Ken Burns: transform-only tween per bg clip (NO opacity — that hides clips),
    # positioned at the clip's start on the registered main timeline.
    kenburns = "".join(
        f'\n      window.__timelines["main"].fromTo("#bg-{p.index}", '
        f'{{ scale: 1, xPercent: 0, yPercent: 0 }}, '
        f'{{ scale: 1.08, xPercent: -2, yPercent: -2, duration: {p.duration}, ease: "none" }}, '
        f'{p.start});'
        for p in imaged
    )
    return bg_block, bg_css, kenburns


def build_composition(segments: list[DialogueSegment], cfg: CompositionConfig | None = None) -> str:
    """Render dialogue segments → a deterministic HyperFrames index.html string."""
    if not segments:
        raise ValueError("build_composition requires at least one segment")
    cfg = cfg or CompositionConfig()
    placed, total = _place(segments, cfg)
    bg_block, bg_css, kenburns = _bg_fragments(placed, cfg)

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
        clips="\n".join(clips), bg_block=bg_block, bg_css=bg_css, kenburns=kenburns,
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
        # B-roll background image (optional) — index matches build_composition.
        if seg.image_path is not None:
            shutil.copy2(seg.image_path, job_dir / "assets" / f"bg-{i}.jpg")

    (job_dir / "index.html").write_text(build_composition(segments, cfg), encoding="utf-8")
    (job_dir / "meta.json").write_text(json.dumps({"id": job_dir.name, "name": job_dir.name}))
    (job_dir / "hyperframes.json").write_text(Path(hyperframes_json).read_text())
    return job_dir
