"""VoiceGenerator — voice synthesis for video pipeline.

Wraps existing TTSManager to produce audio + word-level timestamps
for face animation lip-sync and subtitle generation.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class VoiceOutput:
    """Output from voice generation."""

    audio_path: Path
    duration_s: float
    sample_rate: int
    word_timestamps: list[dict[str, Any]] = field(default_factory=list)
    speed_applied: float = 1.0


class VoiceGenerator:
    """Voice generation for video pipeline.

    Wraps existing TTSManager singleton — no duplicate engine loading.
    Produces WAV audio + word-level timestamps via Whisper alignment.

    Usage::

        gen = VoiceGenerator(tts_manager)
        output = await gen.generate(
            text="Xin chào",
            voice_id="Binh",
            output_dir=Path("output/"),
        )
        # output.audio_path -> WAV file
        # output.word_timestamps -> [{"word": "Xin", "start_s": 0.1, "end_s": 0.3}, ...]
    """

    def __init__(self, tts: Any, extract_timestamps: bool = True):
        """Initialize VoiceGenerator.

        Parameters
        ----------
        tts : TTSManager
            Existing TTS manager instance (shared singleton).
        extract_timestamps : bool
            Whether to extract word timestamps via Whisper.
        """
        self._tts = tts
        self._extract_timestamps = extract_timestamps
        self._timestamp_extractor = None

    @property
    def available_voices(self) -> list[str]:
        """Voice ids cached in the underlying TTS manager."""
        return list(getattr(self._tts, "voice_cache", {}).keys())

    def _get_timestamp_extractor(self) -> Any:
        """Lazily initialize TimestampExtractor."""
        if self._timestamp_extractor is None:
            from apps.video.voice.timestamps import TimestampExtractor
            self._timestamp_extractor = TimestampExtractor()
        return self._timestamp_extractor

    async def generate(
        self,
        text: str,
        voice_id: str,
        output_dir: Path,
        target_duration_s: float | None = None,
        temperature: float = 0.8,
        progress_cb: Any | None = None,
        extract_timestamps: bool | None = None,
    ) -> VoiceOutput:
        """Generate voice audio with optional timestamps.

        Parameters
        ----------
        text : str
            Text to synthesize.
        voice_id : str
            Voice preset ID from TTSManager cache.
        output_dir : Path
            Directory to write output WAV.
        target_duration_s : float, optional
            Target audio duration. Adjusts speed if set.
        temperature : float
            TTS temperature parameter.
        progress_cb : callable, optional
            Callback(percent, message) for progress updates.

        Returns
        -------
        VoiceOutput
            Audio path, duration, sample rate, and word timestamps.
        """
        output_dir = Path(output_dir).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

        if not text.strip():
            raise ValueError("Text cannot be empty")

        if hasattr(self._tts, 'voice_cache') and voice_id not in self._tts.voice_cache:
            available = list(self._tts.voice_cache.keys())
            raise ValueError(f"Voice '{voice_id}' not cached. Available: {available}")

        if progress_cb:
            progress_cb(0, "Starting voice synthesis...")

        # Step 1: Synthesize via TTSManager (with timeout)
        try:
            audio_chunks = await asyncio.wait_for(
                self._synthesize_chunked(text, voice_id, temperature),
                timeout=300.0,
            )
        except asyncio.TimeoutError:
            raise RuntimeError("Voice synthesis timed out after 300s")

        if progress_cb:
            progress_cb(40, "Audio synthesized")

        # Track intermediate files for cleanup
        raw_wav = output_dir / "voice_raw.wav"
        normalized_wav = output_dir / "voice_normalized.wav"
        final_wav = output_dir / "voice.wav"
        intermediates = [raw_wav, normalized_wav]

        try:
            # Step 2: Join chunks and save as WAV
            from vieneu_utils.core_utils import join_audio_chunks

            audio = join_audio_chunks(audio_chunks, self._tts.sample_rate, silence_p=0.05)
            self._save_wav(audio, raw_wav, self._tts.sample_rate)

            actual_duration = len(audio) / self._tts.sample_rate
            logger.info("Synthesized %.1fs audio (%d samples)", actual_duration, len(audio))

            if progress_cb:
                progress_cb(50, f"Audio saved ({actual_duration:.1f}s)")

            # Step 3: Normalize audio
            from apps.studio_api import normalize_audio

            try:
                await asyncio.to_thread(normalize_audio, str(raw_wav), str(normalized_wav))
            except Exception as e:
                raise RuntimeError(f"Audio normalization failed: {e}") from e

            if progress_cb:
                progress_cb(60, "Audio normalized")

            # Step 4: Duration adjustment (optional)
            speed_applied = 1.0

            if target_duration_s is not None and target_duration_s > 0:
                from apps.studio_api import adjust_to_target_duration

                try:
                    meta = await asyncio.to_thread(
                        adjust_to_target_duration,
                        str(normalized_wav),
                        str(final_wav),
                        target_duration_s,
                        self._tts.sample_rate,
                    )
                except Exception as e:
                    raise RuntimeError(f"Duration adjustment failed: {e}") from e

                speed_applied = meta.get("speed_applied", 1.0)
                logger.info("Duration adjusted: %s", meta)
            else:
                shutil.copy2(normalized_wav, final_wav)

            if progress_cb:
                progress_cb(70, "Duration adjusted" if target_duration_s else "Ready for timestamps")

            # Step 5: Extract word timestamps (per-call override wins)
            want_timestamps = (
                self._extract_timestamps if extract_timestamps is None
                else extract_timestamps
            )
            word_timestamps: list[dict[str, Any]] = []
            if want_timestamps:
                try:
                    extractor = self._get_timestamp_extractor()
                    # Whisper runs on final_wav (post speed-adjustment),
                    # so timestamps already reflect the actual audio timing.
                    # No rescaling needed.
                    word_timestamps = await asyncio.to_thread(
                        extractor.extract, final_wav,
                    )

                    if progress_cb:
                        progress_cb(90, f"Timestamps extracted ({len(word_timestamps)} words)")
                except Exception as e:
                    logger.warning("Timestamp extraction failed: %s", e)
                    if progress_cb:
                        progress_cb(90, "Timestamps unavailable")

            # Calculate final duration
            import soundfile as sf

            try:
                data, sr = sf.read(str(final_wav))
            except Exception as e:
                raise RuntimeError(f"Cannot read final audio {final_wav}: {e}") from e

            final_duration = len(data) / sr

            if progress_cb:
                progress_cb(100, "Voice generation complete")

            return VoiceOutput(
                audio_path=final_wav,
                duration_s=round(final_duration, 3),
                sample_rate=sr,
                word_timestamps=word_timestamps,
                speed_applied=round(speed_applied, 3),
            )

        finally:
            # Cleanup intermediate files (always, even on error)
            for tmp_file in intermediates:
                if tmp_file == final_wav:
                    continue
                # Don't delete normalized_wav if final_wav copy failed
                if tmp_file == normalized_wav and not final_wav.exists():
                    continue
                if tmp_file.exists():
                    try:
                        tmp_file.unlink()
                    except OSError:
                        pass

    async def _synthesize_chunked(
        self,
        text: str,
        voice_id: str,
        temperature: float,
    ) -> list[np.ndarray]:
        """Split text into chunks and synthesize each."""
        from vieneu_utils.core_utils import split_text_into_chunks

        chunks = split_text_into_chunks(text, max_chars=256)
        logger.info("Text split into %d chunks", len(chunks))

        audio_chunks: list[np.ndarray] = []
        for i, chunk in enumerate(chunks):
            audio = await self._tts.synthesize(chunk, voice_id, temperature=temperature)
            audio_chunks.append(audio)
            logger.debug("Chunk %d/%d synthesized (%d samples)", i + 1, len(chunks), len(audio))

        return audio_chunks

    @staticmethod
    def _save_wav(audio: np.ndarray, path: Path, sample_rate: int) -> None:
        """Save numpy audio array as WAV file."""
        import soundfile as sf

        # Ensure float32 and clamp to [-1, 1]
        audio = np.clip(audio.astype(np.float32), -1.0, 1.0)
        sf.write(str(path), audio, sample_rate)
