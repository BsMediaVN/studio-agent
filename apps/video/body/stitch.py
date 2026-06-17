"""FFmpeg frame stitching — PNG sequence to VP9+alpha WebM."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def stitch_frames_to_video(
    frames_dir: Path,
    output_path: Path,
    fps: int = 30,
    bitrate: str = "2M",
    timeout_s: int = 300,
) -> Path:
    """Stitch PNG frame sequence into VP9+alpha WebM video.

    Parameters
    ----------
    frames_dir : Path
        Directory containing %06d.png frame files.
    output_path : Path
        Output WebM file path.
    fps : int
        Framerate.
    bitrate : str
        Target video bitrate.
    timeout_s : int
        FFmpeg timeout in seconds.

    Returns
    -------
    Path
        Path to output WebM video.
    """
    frames_dir = Path(frames_dir)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    import shutil as _shutil
    if not _shutil.which("ffmpeg"):
        raise RuntimeError("FFmpeg not found. Install: brew install ffmpeg")

    # Count frames
    frame_count = len(list(frames_dir.glob("*.png")))
    if frame_count == 0:
        raise RuntimeError(f"No PNG frames found in {frames_dir}")

    logger.info("Stitching %d frames at %dfps -> %s", frame_count, fps, output_path.name)

    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-framerate", str(fps),
        "-i", str(frames_dir / "%06d.png"),
        "-c:v", "libvpx-vp9",
        "-pix_fmt", "yuva420p",
        "-auto-alt-ref", "0",
        "-b:v", bitrate,
        str(output_path),
    ]

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout_s,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"FFmpeg stitching timed out after {timeout_s}s")

    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg stitching failed: {result.stderr[-300:]}")

    if not output_path.exists():
        raise RuntimeError(f"FFmpeg produced no output: {output_path}")

    size_mb = output_path.stat().st_size / 1e6
    logger.info("Video stitched: %s (%.1f MB, %d frames)", output_path.name, size_mb, frame_count)
    return output_path
