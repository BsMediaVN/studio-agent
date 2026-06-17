"""Word-level timestamp extraction using Whisper forced alignment."""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class TimestampExtractor:
    """Extract word-level timestamps from audio using Whisper.

    Uses the `tiny` model (~39MB) for fast forced alignment.
    Model is loaded lazily on first call and reused across extractions.
    Thread-safe via threading.Lock for model loading.
    """

    def __init__(self, model_size: str = "tiny", language: str = "vi"):
        self._model_size = model_size
        self._language = language
        self._model: Any = None
        self._load_lock = threading.Lock()

    def _ensure_model(self) -> None:
        """Load Whisper model lazily on first use (thread-safe)."""
        if self._model is not None:
            return
        with self._load_lock:
            if self._model is not None:
                return  # Double-check after acquiring lock
            try:
                import whisper
                logger.info("Loading Whisper '%s' model...", self._model_size)
                self._model = whisper.load_model(self._model_size)
                logger.info("Whisper model loaded")
            except ImportError:
                raise RuntimeError(
                    "openai-whisper not installed. Run: uv pip install openai-whisper"
                )

    def extract(self, audio_path: Path) -> list[dict[str, Any]]:
        """Extract word timestamps from audio file.

        Parameters
        ----------
        audio_path : Path
            Audio file (WAV preferred).

        Returns
        -------
        list[dict]
            List of {"word": str, "start_s": float, "end_s": float}.
            Empty list if no words detected.
        """
        audio_path = Path(audio_path)
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        self._ensure_model()

        result = self._model.transcribe(
            str(audio_path),
            word_timestamps=True,
            language=self._language,
        )

        timestamps: list[dict[str, Any]] = []
        for segment in result.get("segments", []):
            for word_info in segment.get("words", []):
                word = word_info.get("word", "").strip()
                if not word:
                    continue
                timestamps.append({
                    "word": word,
                    "start_s": round(float(word_info["start"]), 3),
                    "end_s": round(float(word_info["end"]), 3),
                })

        logger.info(
            "Extracted %d word timestamps from %s (%.1fs audio)",
            len(timestamps),
            audio_path.name,
            timestamps[-1]["end_s"] if timestamps else 0,
        )
        return timestamps

    def _rescale_timestamps(
        self,
        timestamps: list[dict[str, Any]],
        speed_factor: float,
    ) -> list[dict[str, Any]]:
        """Rescale timestamps after audio speed adjustment.

        Parameters
        ----------
        timestamps : list[dict]
            Original word timestamps.
        speed_factor : float
            Speed multiplier applied to audio (e.g., 1.2 = 20% faster).

        Returns
        -------
        list[dict]
            Rescaled timestamps.
        """
        if abs(speed_factor - 1.0) < 0.01:
            return timestamps

        return [
            {
                "word": ts["word"],
                "start_s": round(ts["start_s"] / speed_factor, 3),
                "end_s": round(ts["end_s"] / speed_factor, 3),
            }
            for ts in timestamps
        ]
