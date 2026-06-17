"""SadTalker+pirender backend for audio-driven face animation."""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

from apps.video.face.backends.base import FaceBackend

logger = logging.getLogger(__name__)

# Default paths relative to project root
_VIDEO_DIR = Path(__file__).resolve().parent.parent.parent
_SADTALKER_DIR = _VIDEO_DIR / "models" / "sadtalker"


class SadTalkerBackend(FaceBackend):
    """SadTalker with pirender face renderer.

    Uses subprocess to call SadTalker's inference.py with --facerender pirender.
    This avoids importing SadTalker's code directly (dependency isolation).
    """

    def __init__(
        self,
        sadtalker_dir: Path | None = None,
        resolution: int = 256,
        timeout_s: int = 600,
    ):
        self._sadtalker_dir = Path(sadtalker_dir) if sadtalker_dir else _SADTALKER_DIR
        self._python_bin = self._find_python()
        self._resolution = resolution
        self._timeout_s = timeout_s

    def _find_python(self) -> str:
        """Find the correct Python binary (prefer venv)."""
        venv_python = _VIDEO_DIR.parent.parent / ".venv" / "bin" / "python3.12"
        if venv_python.exists():
            return str(venv_python)
        venv_python3 = _VIDEO_DIR.parent.parent / ".venv" / "bin" / "python3"
        if venv_python3.exists():
            return str(venv_python3)
        return "python3"

    @property
    def name(self) -> str:
        return "SadTalker+pirender"

    @property
    def output_resolution(self) -> int:
        return self._resolution

    def is_available(self) -> bool:
        """Check SadTalker repo + checkpoints exist."""
        inference_py = self._sadtalker_dir / "inference.py"
        checkpoints = self._sadtalker_dir / "checkpoints"
        if not inference_py.exists():
            return False
        try:
            return checkpoints.exists() and any(checkpoints.iterdir())
        except (PermissionError, OSError):
            return False

    async def infer(
        self,
        face_image: Path,
        audio_path: Path,
        output_dir: Path,
        progress_cb: Callable[[int, str], None] | None = None,
        **kwargs: Any,
    ) -> Path:
        """Run SadTalker inference via subprocess.

        Returns path to generated MP4 video.
        """
        if not self.is_available():
            raise RuntimeError(
                f"SadTalker not available at {self._sadtalker_dir}. "
                "Run: bash apps/video/scripts/setup_sadtalker.sh"
            )

        face_image = Path(face_image).resolve()
        audio_path = Path(audio_path).resolve()
        output_dir = Path(output_dir).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

        if progress_cb:
            progress_cb(5, "Starting SadTalker inference...")

        # Build command — no shell=True for security
        cmd = [
            self._python_bin,
            str(self._sadtalker_dir / "inference.py"),
            "--driven_audio", str(audio_path),
            "--source_image", str(face_image),
            "--result_dir", str(output_dir),
            "--facerender", "pirender",
            "--size", str(self._resolution),
            "--preprocess", "crop",
            "--still",
            "--enhancer", "gfpgan",
        ]

        env = os.environ.copy()
        env["PYTORCH_ENABLE_MPS_FALLBACK"] = "1"

        logger.info("Running SadTalker: %s", " ".join(cmd[:5]) + " ...")

        start_time = time.time()

        try:
            result = await asyncio.to_thread(
                subprocess.run,
                cmd,
                capture_output=True,
                text=True,
                timeout=self._timeout_s,
                cwd=str(self._sadtalker_dir),
                env=env,
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError(
                f"SadTalker inference timed out after {self._timeout_s}s"
            )

        elapsed = time.time() - start_time
        logger.info("SadTalker finished in %.1fs (exit code %d)", elapsed, result.returncode)

        if result.returncode != 0:
            error_msg = result.stderr[-500:] if result.stderr else "No error output"
            raise RuntimeError(f"SadTalker inference failed:\n{error_msg}")

        if progress_cb:
            progress_cb(80, f"Inference complete ({elapsed:.1f}s)")

        # Find output video — SadTalker writes to result_dir with timestamp
        output_video = self._find_output_video(output_dir, min_mtime=start_time)
        if not output_video:
            raise RuntimeError(
                f"SadTalker produced no output video in {output_dir}. "
                f"stdout: {result.stdout[-300:]}"
            )

        logger.info("Output video: %s (%.1f MB)", output_video, output_video.stat().st_size / 1e6)
        return output_video

    @staticmethod
    def _find_output_video(output_dir: Path, min_mtime: float = 0) -> Path | None:
        """Find the most recent MP4 file in output directory (recursive).

        Parameters
        ----------
        output_dir : Path
            Directory to search.
        min_mtime : float
            Minimum modification time — filters out stale pre-existing files.
        """
        candidates: list[tuple[float, Path]] = []
        for p in output_dir.rglob("*.mp4"):
            try:
                mtime = p.stat().st_mtime
            except (OSError, FileNotFoundError):
                continue
            if mtime >= min_mtime:
                candidates.append((mtime, p))
        if not candidates:
            return None
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]
