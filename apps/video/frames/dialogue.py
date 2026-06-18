"""Dialogue parsing + voice assignment for frames mode.

Turns a raw script string into per-line ``(speaker, text)`` segments and maps
each distinct speaker to a TTS voice (rotating through the available presets so
multi-character dialogue gets distinct voices). Plain text with no ``Name:``
markers → a single narrator line.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# "Name: spoken text" — name is short, must contain a letter (so "10:30" or a
# bare URL scheme isn't mistaken for a speaker), allows Vietnamese letters.
_SPEAKER_RE = re.compile(r"^(?=[\wÀ-ỹ .'-]*[A-Za-zÀ-ỹ])([\wÀ-ỹ .'-]{1,30}):\s*(.+)$")
# A bare "Name:" marker with no spoken text → dropped, not voiced.
_BARE_MARKER_RE = re.compile(r"^[\wÀ-ỹ .'-]{1,30}:\s*$")
_DEFAULT_SPEAKER = "Người kể"


@dataclass
class ParsedLine:
    speaker: str
    text: str


def parse_dialogue(text: str, default_speaker: str = _DEFAULT_SPEAKER) -> list[ParsedLine]:
    """Parse a script into dialogue lines.

    Lines like ``Bình: Xin chào`` become ``(Bình, Xin chào)``; lines without a
    marker are attributed to ``default_speaker``. Empty lines and bare ``Name:``
    markers (no text) are dropped.
    """
    lines: list[ParsedLine] = []
    for raw in (text or "").splitlines():
        raw = raw.strip()
        if not raw or _BARE_MARKER_RE.match(raw):
            continue
        m = _SPEAKER_RE.match(raw)
        if m and m.group(2).strip():
            lines.append(ParsedLine(m.group(1).strip(), m.group(2).strip()))
        elif not m:
            lines.append(ParsedLine(default_speaker, raw))
        # else: bare "Name:" with no text → dropped
    return [ln for ln in lines if ln.text.strip()]


def assign_voices(
    speakers: list[str],
    available: list[str],
    default: str | None = None,
) -> dict[str, str]:
    """Map each distinct speaker → a voice id, rotating through ``available``.

    The default voice (if valid) is assigned to the first speaker so the primary
    voice stays stable; remaining speakers rotate through the rest.
    """
    if not available:
        raise ValueError("No TTS voices available for assignment")
    distinct: list[str] = []
    for s in speakers:
        if s not in distinct:
            distinct.append(s)

    rotation = list(available)
    if default and default in rotation:
        rotation.remove(default)
        rotation.insert(0, default)

    return {sp: rotation[i % len(rotation)] for i, sp in enumerate(distinct)}
