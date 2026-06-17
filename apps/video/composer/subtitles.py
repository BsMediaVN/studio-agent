"""SRT subtitle generation from word timestamps."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def generate_srt(
    word_timestamps: list[dict[str, Any]],
    output_path: Path,
    words_per_line: int = 5,
) -> Path:
    """Generate SRT subtitle file from word timestamps.

    Groups words into chunks for readable subtitle display.

    Parameters
    ----------
    word_timestamps : list[dict]
        List of {"word": str, "start_s": float, "end_s": float}.
    output_path : Path
        Where to write the .srt file.
    words_per_line : int
        Number of words per subtitle line.

    Returns
    -------
    Path
        Path to the generated SRT file.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not word_timestamps:
        # Write empty SRT
        output_path.write_text("")
        return output_path

    lines: list[str] = []
    index = 1

    # Group words into chunks
    for i in range(0, len(word_timestamps), words_per_line):
        chunk = word_timestamps[i : i + words_per_line]
        start_s = chunk[0]["start_s"]
        end_s = chunk[-1]["end_s"]
        text = " ".join(w["word"] for w in chunk)

        lines.append(str(index))
        lines.append(f"{_format_time(start_s)} --> {_format_time(end_s)}")
        lines.append(text)
        lines.append("")
        index += 1

    output_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("SRT generated: %d entries -> %s", index - 1, output_path.name)
    return output_path


def _format_time(seconds: float) -> str:
    """Format seconds as SRT time code: HH:MM:SS,mmm"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
