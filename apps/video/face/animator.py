"""FaceAnimator — main face animation engine.

Orchestrates: face preprocessing -> backend inference -> optional alpha extraction.
Provides a clean API: face_image + audio -> face video.
"""

from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path
from typing import Any, Callable

from apps.video.face.backends.base import FaceBackend
from apps.video.face.backends.sadtalker import SadTalkerBackend
from apps.video.face.preprocessor import detect_and_crop_face, has_human_face

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent


def _validate_path(path: Path, label: str) -> Path:
    """Ensure path is within project root or /tmp (prevent path traversal)."""
    resolved = path.resolve()
    allowed_roots = [_PROJECT_ROOT, Path("/tmp"), Path(tempfile.gettempdir())]
    if not any(resolved.is_relative_to(root) for root in allowed_roots):
        raise ValueError(
            f"{label} path '{resolved}' is outside allowed directories"
        )
    return resolved


class FaceAnimator:
    """Face animation engine with backend abstraction.

    Usage::

        animator = FaceAnimator(backend="sadtalker")
        result = await animator.generate(
            face_image=Path("face.png"),
            audio_path=Path("audio.wav"),
            output_dir=Path("output/"),
        )
    """

    _BACKENDS: dict[str, type[FaceBackend]] = {
        "sadtalker": SadTalkerBackend,
    }

    def __init__(
        self,
        backend: str = "sadtalker",
        extract_alpha: bool = False,
        backend_kwargs: dict[str, Any] | None = None,
    ):
        if backend not in self._BACKENDS:
            raise ValueError(
                f"Unknown backend '{backend}'. Available: {list(self._BACKENDS.keys())}"
            )

        self._backend_name = backend
        self._extract_alpha = extract_alpha
        self._backend: FaceBackend = self._BACKENDS[backend](**(backend_kwargs or {}))
        self._lock = asyncio.Lock()

        logger.info(
            "FaceAnimator initialized: backend=%s, alpha=%s",
            backend, extract_alpha,
        )

    @property
    def backend(self) -> FaceBackend:
        return self._backend

    @property
    def is_available(self) -> bool:
        return self._backend.is_available()

    async def generate(
        self,
        face_image: Path,
        audio_path: Path,
        output_dir: Path,
        progress_cb: Callable[[int, str], None] | None = None,
    ) -> Path:
        """Generate face animation video from image + audio.

        Parameters
        ----------
        face_image : Path
            Input face image (any size, will be auto-cropped).
        audio_path : Path
            Audio file (WAV) for lip-sync.
        output_dir : Path
            Directory to write output files.
        progress_cb : callable, optional
            Callback(percent, message) for progress updates.

        Returns
        -------
        Path
            Path to face video (MP4 or WebM with alpha).
        """
        face_image = _validate_path(Path(face_image), "face_image")
        audio_path = _validate_path(Path(audio_path), "audio_path")
        output_dir = _validate_path(Path(output_dir), "output_dir")
        output_dir.mkdir(parents=True, exist_ok=True)

        if not face_image.exists():
            raise FileNotFoundError(f"Face image not found: {face_image}")
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        async with self._lock:
            return await self._generate_impl(
                face_image, audio_path, output_dir, progress_cb
            )

    async def _generate_impl(
        self,
        face_image: Path,
        audio_path: Path,
        output_dir: Path,
        progress_cb: Callable[[int, str], None] | None,
    ) -> Path:
        """Internal generate implementation (called under lock)."""

        # Stage 0: Validate face exists in image
        has_face = await asyncio.to_thread(has_human_face, face_image)
        if not has_face:
            raise ValueError(
                "No human face detected in the uploaded image. "
                "SadTalker requires a clear photo of a human face."
            )

        # Stage 1: Preprocess face (10%)
        if progress_cb:
            progress_cb(0, "Preprocessing face...")

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            cropped_face = tmp / "face_cropped.png"

            await asyncio.to_thread(
                detect_and_crop_face,
                face_image,
                cropped_face,
                target_size=self._backend.output_resolution,
            )

            if progress_cb:
                progress_cb(10, "Face cropped and aligned")

            # Stage 2: Backend inference (10% -> 80%)
            def _inference_progress(pct: int, msg: str) -> None:
                if progress_cb:
                    # Map backend's 0-100 to our 10-80 range
                    mapped = 10 + int(pct * 0.7)
                    progress_cb(mapped, msg)

            raw_video = await self._backend.infer(
                face_image=cropped_face,
                audio_path=audio_path,
                output_dir=tmp / "inference",
                progress_cb=_inference_progress,
            )

            if progress_cb:
                progress_cb(80, "Inference complete")

            # Copy raw video out of temp dir BEFORE it's deleted
            import shutil

            final_output = output_dir / "face_raw.mp4"
            shutil.copy2(raw_video, final_output)

        # After temp dir cleanup — work with copied file
        if self._extract_alpha:
            if progress_cb:
                progress_cb(80, "Extracting alpha mask...")

            from apps.video.face.alpha_extractor import extract_alpha_video

            alpha_output = output_dir / "face_alpha.webm"

            def _alpha_progress(pct: int, msg: str) -> None:
                if progress_cb:
                    mapped = 80 + int(pct * 15 // 100)
                    progress_cb(mapped, msg)

            await asyncio.to_thread(
                extract_alpha_video,
                final_output,
                alpha_output,
                progress_cb=_alpha_progress,
            )

            if progress_cb:
                progress_cb(95, "Alpha extraction complete")

            return alpha_output
        else:
            if progress_cb:
                progress_cb(95, "Face video ready")

            return final_output
