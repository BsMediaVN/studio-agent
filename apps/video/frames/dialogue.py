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
# Markdown noise to strip from pasted prose (headings, bullets, emphasis, rules).
_MD_PREFIX_RE = re.compile(r"^[#>\-\*•\s]+")
_MD_INLINE_RE = re.compile(r"[*_`]+")
# Split prose into sentences so each caption stays short (keeps terminal punctuation).
_SENT_RE = re.compile(r"[^.!?…]+[.!?…]+|\S[^.!?…]*$")
_DEFAULT_SPEAKER = "Người kể"


@dataclass
class ParsedLine:
    speaker: str
    text: str


def _clean_prose(line: str) -> str:
    """Strip markdown markers from a pasted prose line."""
    return _MD_INLINE_RE.sub("", _MD_PREFIX_RE.sub("", line)).strip()


def _sentences(text: str) -> list[str]:
    """Break prose into sentence-sized chunks (for readable captions)."""
    return [m.group(0).strip() for m in _SENT_RE.finditer(text) if m.group(0).strip()]


def parse_dialogue(text: str, default_speaker: str = _DEFAULT_SPEAKER) -> list[ParsedLine]:
    """Parse pasted content into dialogue/narration lines.

    ``Bình: Xin chào`` → ``(Bình, Xin chào)`` (one turn per line). Prose lines
    (no ``Name:`` marker) are markdown-stripped and split into sentences,
    attributed to ``default_speaker``. Empty lines, markdown rules, and bare
    ``Name:`` markers are dropped.
    """
    lines: list[ParsedLine] = []
    for raw in (text or "").splitlines():
        raw = raw.strip()
        if not raw or _BARE_MARKER_RE.match(raw):
            continue
        m = _SPEAKER_RE.match(raw)
        if m and m.group(2).strip():
            lines.append(ParsedLine(m.group(1).strip(), _MD_INLINE_RE.sub("", m.group(2)).strip()))
        elif not m:
            cleaned = _clean_prose(raw)
            for sentence in _sentences(cleaned):
                lines.append(ParsedLine(default_speaker, sentence))
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
