"""Keyword extraction for B-roll: Vietnamese line(s) → English search phrase(s).

Split from ``broll.py`` to keep each file focused (keyword/LLM logic here, the
fetch/cache pipeline there). Uses the existing ``LLMScriptGenerator`` (DRY) and
never raises — any failure yields an empty keyword so the caller uses a flat bg.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

_KEYWORD_SYSTEM = (
    "You turn a line of Vietnamese narration into ONE short English search "
    "phrase (1-4 words) naming a concrete, filmable visual scene for stock "
    "footage. Output ONLY the phrase — no quotes, punctuation, or explanation."
)
_KEYWORD_BATCH_SYSTEM = (
    "For each numbered Vietnamese line, output ONE short English search phrase "
    "(1-4 words) naming a concrete, filmable visual scene for stock footage. "
    "Output exactly one line per input, in the SAME numbering: '1. phrase'. "
    "No quotes, no extra text."
)
_NUM_LINE_RE = re.compile(r"^\s*(\d+)[.)\]]\s*(.+)$")


def _clean_keyword(raw: str) -> str:
    return " ".join((raw or "").split()).strip().strip('".')[:60]


async def extract_keyword(text: str, llm) -> str:
    """VN text → one English visual keyword. Returns '' on any failure."""
    if not (text and text.strip()):
        return ""
    try:
        # 500-char cap: one line is short; bounds prompt size + keeps the call cheap.
        raw = await llm.complete_text(text.strip()[:500], system=_KEYWORD_SYSTEM)
        return _clean_keyword(raw)
    except Exception as e:  # noqa: BLE001 — degrade, never break the job
        logger.warning("broll keyword extraction failed: %s", e)
        return ""


async def extract_keywords(texts: list[str], llm) -> list[str]:
    """Batch VN→EN keyword extraction: ONE LLM call for all lines instead of N
    serial calls (M2 — caps latency/cost on long scripts). Returns a list aligned
    to ``texts`` ('' where unknown). Never raises."""
    items = [(t or "").strip()[:300] for t in texts]
    if not any(items):
        return ["" for _ in texts]
    numbered = "\n".join(f"{i + 1}. {t or '(skip)'}" for i, t in enumerate(items))
    try:
        raw = await llm.complete_text(
            numbered, system=_KEYWORD_BATCH_SYSTEM, max_tokens=16 * len(items) + 32,
        )
        parsed: dict[int, str] = {}
        for line in (raw or "").splitlines():
            m = _NUM_LINE_RE.match(line)
            if m:
                parsed[int(m.group(1))] = _clean_keyword(m.group(2))
        return [parsed.get(i + 1, "") for i in range(len(texts))]
    except Exception as e:  # noqa: BLE001 — degrade to all-flat-bg, never break
        logger.warning("broll batch keyword extraction failed: %s", e)
        return ["" for _ in texts]
