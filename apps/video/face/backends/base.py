"""Abstract base class for face animation backends."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Callable


class FaceBackend(ABC):
    """Base class for face animation engines.

    Each backend takes a face image + audio file and produces a video
    of the face speaking with lip-sync.
    """

    @abstractmethod
    async def infer(
        self,
        face_image: Path,
        audio_path: Path,
        output_dir: Path,
        progress_cb: Callable[[int, str], None] | None = None,
        **kwargs: Any,
    ) -> Path:
        """Run face animation inference.

        Parameters
        ----------
        face_image : Path
            Preprocessed face image (cropped + aligned).
        audio_path : Path
            Audio file (WAV) to drive lip-sync.
        output_dir : Path
            Directory to write output video.
        progress_cb : callable, optional
            Callback(percent, message) for progress updates.

        Returns
        -------
        Path
            Path to generated face video (MP4).
        """
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this backend is installed and ready."""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Backend display name."""
        ...

    @property
    def output_resolution(self) -> int:
        """Default output resolution (square)."""
        return 256
