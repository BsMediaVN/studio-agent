"""Alpha mask extraction for face video transparency.

Extracts per-frame masks using background removal, then merges with
the original video to produce a VP9+alpha WebM for clean composition.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)


def extract_alpha_video(
    input_video: Path,
    output_path: Path,
    progress_cb: Callable[[int, str], None] | None = None,
) -> Path:
    """Convert face video to VP9+alpha WebM using background removal.

    Parameters
    ----------
    input_video : Path
        Input face video (MP4 from SadTalker).
    output_path : Path
        Output WebM path with alpha channel.
    progress_cb : callable, optional
        Progress callback(percent, message).

    Returns
    -------
    Path
        Path to VP9+alpha WebM video.
    """
    input_video = Path(input_video)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not input_video.exists():
        raise FileNotFoundError(f"Input video not found: {input_video}")

    with tempfile.TemporaryDirectory() as tmpdir:
        frames_dir = Path(tmpdir) / "frames"
        masks_dir = Path(tmpdir) / "masks"
        frames_dir.mkdir()
        masks_dir.mkdir()

        # Step 1: Extract frames
        if progress_cb:
            progress_cb(0, "Extracting frames...")

        _extract_frames(input_video, frames_dir)
        frame_files = sorted(frames_dir.glob("*.png"))
        total_frames = len(frame_files)

        if total_frames == 0:
            raise RuntimeError("No frames extracted from video")

        logger.info("Extracted %d frames from %s", total_frames, input_video.name)

        # Step 2: Generate masks using RMBG or fallback
        if progress_cb:
            progress_cb(10, f"Generating masks for {total_frames} frames...")

        _generate_masks(frame_files, masks_dir, progress_cb, total_frames)

        # Step 3: Merge frames + masks -> VP9+alpha WebM
        if progress_cb:
            progress_cb(85, "Encoding VP9+alpha video...")

        fps = _get_video_fps(input_video)
        _encode_alpha_video(frames_dir, masks_dir, output_path, fps)

    if not output_path.exists():
        raise RuntimeError(f"Failed to create alpha video: {output_path}")

    logger.info(
        "Alpha video created: %s (%.1f MB)",
        output_path.name, output_path.stat().st_size / 1e6,
    )
    return output_path


def _extract_frames(video_path: Path, output_dir: Path) -> None:
    """Extract all frames from video as PNG sequence."""
    cmd = [
        "ffmpeg", "-y", "-i", str(video_path),
        "-vsync", "0",
        str(output_dir / "%06d.png"),
    ]
    subprocess.run(cmd, check=True, capture_output=True, timeout=120)


def _get_video_fps(video_path: Path) -> float:
    """Get video framerate using ffprobe."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-select_streams", "v:0",
                "-show_entries", "stream=r_frame_rate",
                "-of", "csv=p=0",
                str(video_path),
            ],
            capture_output=True, text=True, timeout=10,
        )
        fps_str = result.stdout.strip()
        if "/" in fps_str:
            num, den = fps_str.split("/")
            return float(num) / float(den)
        return float(fps_str)
    except Exception:
        return 25.0  # Default


def _generate_masks(
    frame_files: list[Path],
    masks_dir: Path,
    progress_cb: Callable[[int, str], None] | None,
    total_frames: int,
) -> None:
    """Generate binary masks for each frame.

    Tries RMBG (transformers pipeline) first, falls back to simple thresholding.
    """
    try:
        _generate_masks_rmbg(frame_files, masks_dir, progress_cb, total_frames)
    except Exception as e:
        logger.warning("RMBG failed (%s), using fallback mask generation", e)
        _generate_masks_fallback(frame_files, masks_dir, progress_cb, total_frames)


def _generate_masks_rmbg(
    frame_files: list[Path],
    masks_dir: Path,
    progress_cb: Callable[[int, str], None] | None,
    total_frames: int,
) -> None:
    """Generate masks using RMBG-2.0 background removal model."""
    from PIL import Image
    from transformers import pipeline

    # Pin to specific commit to mitigate supply chain risk with trust_remote_code
    pipe = pipeline(
        "image-segmentation",
        model="briaai/RMBG-2.0",
        revision="refs/pr/23",
        trust_remote_code=True,
    )

    for i, frame_path in enumerate(frame_files):
        img = Image.open(frame_path)
        result = pipe(img)

        # Result can be list[dict] or dict depending on transformers version
        mask = None
        if isinstance(result, list) and result and isinstance(result[0], dict):
            if "mask" in result[0]:
                mask = result[0]["mask"].convert("L")
        elif isinstance(result, dict) and "mask" in result:
            mask = result["mask"].convert("L")

        if mask is None:
            mask = Image.new("L", img.size, 255)

        mask_path = masks_dir / frame_path.name
        mask.save(str(mask_path))

        if progress_cb and i % 5 == 0:
            pct = 10 + int((i / total_frames) * 75)
            progress_cb(pct, f"Mask {i+1}/{total_frames}")


def _generate_masks_fallback(
    frame_files: list[Path],
    masks_dir: Path,
    progress_cb: Callable[[int, str], None] | None,
    total_frames: int,
) -> None:
    """Simple fallback: create white masks (no transparency).

    This means the face video won't have alpha but can still be overlaid
    with a solid background.
    """
    import cv2

    for i, frame_path in enumerate(frame_files):
        img = cv2.imread(str(frame_path))
        if img is None:
            continue
        h, w = img.shape[:2]
        # Create a circular mask centered on the face
        mask = _create_ellipse_mask(w, h)
        mask_path = masks_dir / frame_path.name
        cv2.imwrite(str(mask_path), mask)

        if progress_cb and i % 10 == 0:
            pct = 10 + int((i / total_frames) * 75)
            progress_cb(pct, f"Fallback mask {i+1}/{total_frames}")

    logger.info("Generated %d fallback ellipse masks", total_frames)


def _create_ellipse_mask(width: int, height: int) -> "np.ndarray":
    """Create an elliptical mask with feathered edges."""
    import cv2
    import numpy as np

    mask = np.zeros((height, width), dtype=np.uint8)
    center = (width // 2, height // 2)
    axes = (int(width * 0.42), int(height * 0.48))
    cv2.ellipse(mask, center, axes, 0, 0, 360, 255, -1)

    # Feather edges with Gaussian blur
    mask = cv2.GaussianBlur(mask, (21, 21), 10)
    return mask


def _encode_alpha_video(
    frames_dir: Path,
    masks_dir: Path,
    output_path: Path,
    fps: float,
) -> None:
    """Encode frames + masks into VP9+alpha WebM."""
    cmd = [
        "ffmpeg", "-y",
        "-framerate", str(fps),
        "-i", str(frames_dir / "%06d.png"),
        "-framerate", str(fps),
        "-i", str(masks_dir / "%06d.png"),
        "-filter_complex", "[0][1]alphamerge",
        "-c:v", "libvpx-vp9",
        "-pix_fmt", "yuva420p",
        "-auto-alt-ref", "0",
        "-b:v", "2M",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg alpha encode failed: {result.stderr[-300:]}")
