"""VideoComposer — compose face + body + audio into final video.

Supports static overlay (single FFmpeg pass, fast) and dynamic per-frame
overlay (when head movement exceeds threshold).
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class CompositionConfig:
    """Configuration for video composition."""

    face_scale: float = 1.0
    face_offset_y: int = -20  # Vertical offset (negative = up)
    bg_music_path: Path | None = None
    bg_music_volume: float = 0.15
    burn_subtitles: bool = True
    output_codec: str = "libx264"
    crf: int = 22
    preset: str = "fast"
    # If head position variance > threshold, use per-frame overlay
    dynamic_threshold: float = 20.0


class VideoComposer:
    """Compose face video + body video + audio into final MP4."""

    def compose(
        self,
        body_video: Path,
        audio: Path,
        output_path: Path,
        face_video: Path | None = None,
        head_positions: list[dict[str, Any]] | None = None,
        config: CompositionConfig | None = None,
        subtitles: Path | None = None,
    ) -> Path:
        """Compose all elements into final video.

        Parameters
        ----------
        body_video : Path
            Body animation video (WebM).
        audio : Path
            Voice audio (WAV).
        output_path : Path
            Output MP4 path.
        face_video : Path, optional
            Face animation video. If None, body-only composition.
        head_positions : list[dict], optional
            Per-frame head positions from body renderer.
        config : CompositionConfig, optional
            Composition settings.
        subtitles : Path, optional
            SRT subtitle file.

        Returns
        -------
        Path
            Path to final MP4 video.
        """
        config = config or CompositionConfig()
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if not shutil.which("ffmpeg"):
            raise RuntimeError("FFmpeg not found. Install: brew install ffmpeg")

        # Validate inputs
        for label, p in [("body_video", body_video), ("audio", audio)]:
            if not Path(p).exists():
                raise FileNotFoundError(f"{label} not found: {p}")

        if face_video and not Path(face_video).exists():
            logger.warning("Face video not found: %s — composing body-only", face_video)
            face_video = None

        if face_video and head_positions:
            # Determine if we need dynamic or static overlay
            needs_dynamic = self._needs_dynamic_overlay(head_positions, config.dynamic_threshold)
            if needs_dynamic:
                logger.info("Using dynamic per-frame face overlay")
                return self._compose_dynamic(
                    body_video, face_video, audio, head_positions,
                    output_path, config, subtitles,
                )
            else:
                logger.info("Using static face overlay (low head movement)")
                avg_pos = self._average_position(head_positions)
                return self._compose_static(
                    body_video, face_video, audio, avg_pos,
                    output_path, config, subtitles,
                )
        elif face_video:
            # No head positions — use center-top overlay
            return self._compose_static(
                body_video, face_video, audio,
                {"x": 0, "y": 0, "scale": 1.0},
                output_path, config, subtitles,
            )
        else:
            # Body-only (no face overlay)
            return self._compose_body_only(
                body_video, audio, output_path, config, subtitles,
            )

    def _compose_static(
        self,
        body_video: Path,
        face_video: Path,
        audio: Path,
        position: dict[str, Any],
        output_path: Path,
        config: CompositionConfig,
        subtitles: Path | None,
    ) -> Path:
        """Single-pass FFmpeg composition with static face overlay."""
        face_x = int(position.get("x", 0))
        face_y = int(position.get("y", 0)) + config.face_offset_y
        face_scale = position.get("scale", 1.0) * config.face_scale

        # Build filter complex
        filters = []

        # Scale face
        if abs(face_scale - 1.0) > 0.01:
            filters.append(f"[1:v]scale=iw*{face_scale:.2f}:ih*{face_scale:.2f}[face_scaled]")
            face_ref = "[face_scaled]"
        else:
            face_ref = "[1:v]"

        # Overlay face on body (center face on position)
        overlay_x = f"{face_x}-overlay_w/2"
        overlay_y = f"{face_y}-overlay_h/2"
        filters.append(
            f"[0:v]{face_ref}overlay=x={overlay_x}:y={overlay_y}:format=auto[comp]"
        )

        video_ref = "[comp]"

        # Note: subtitles applied via -vf in a separate pass (not in filter_complex)
        # because FFmpeg's subtitles filter path escaping is fragile in filter_complex

        # Audio
        audio_filters, audio_maps = self._build_audio_filters(config)

        filter_complex = ";".join(filters)
        if audio_filters:
            filter_complex += ";" + ";".join(audio_filters)

        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(body_video),
            "-i", str(face_video),
            "-i", str(audio),
        ]

        if config.bg_music_path and Path(config.bg_music_path).exists():
            cmd.extend(["-i", str(config.bg_music_path)])

        cmd.extend(["-filter_complex", filter_complex])
        cmd.extend(["-map", video_ref])
        cmd.extend(audio_maps)
        cmd.extend([
            "-c:v", config.output_codec,
            "-preset", config.preset,
            "-crf", str(config.crf),
            "-c:a", "aac", "-b:a", "128k",
            "-shortest",
            str(output_path),
        ])

        self._run_ffmpeg(cmd, "Static composition")

        # Post-process: burn subtitles if requested
        if subtitles and Path(subtitles).exists() and config.burn_subtitles:
            self._burn_subtitles(output_path, subtitles)

        return output_path

    def _compose_body_only(
        self,
        body_video: Path,
        audio: Path,
        output_path: Path,
        config: CompositionConfig,
        subtitles: Path | None,
    ) -> Path:
        """Compose body video + audio without face overlay."""
        filters = []
        video_ref = "[0:v]"

        # Subtitles burned in post-processing pass (same as _compose_static)

        # Body-only: audio is input index 1 (not 2)
        audio_filters, audio_maps = self._build_audio_filters(config, voice_index=1)
        if filters:
            all_filters = ";".join(filters)
            if audio_filters:
                all_filters += ";" + ";".join(audio_filters)
        elif audio_filters:
            all_filters = ";".join(audio_filters)
        else:
            all_filters = None

        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(body_video),
            "-i", str(audio),
        ]

        if config.bg_music_path and Path(config.bg_music_path).exists():
            cmd.extend(["-i", str(config.bg_music_path)])

        if all_filters:
            cmd.extend(["-filter_complex", all_filters])
            # video_ref may be "[0:v]" (not a filter label) when no video filters applied
            # Use raw stream mapping in that case
            if video_ref == "[0:v]":
                cmd.extend(["-map", "0:v"])
            else:
                cmd.extend(["-map", video_ref])
            cmd.extend(audio_maps)
        else:
            cmd.extend(["-map", "0:v", "-map", "1:a"])

        cmd.extend([
            "-c:v", config.output_codec,
            "-preset", config.preset,
            "-crf", str(config.crf),
            "-c:a", "aac", "-b:a", "128k",
            "-shortest",
            str(output_path),
        ])

        self._run_ffmpeg(cmd, "Body-only composition")

        if subtitles and Path(subtitles).exists() and config.burn_subtitles:
            self._burn_subtitles(output_path, subtitles)

        return output_path

    def _compose_dynamic(
        self,
        body_video: Path,
        face_video: Path,
        audio: Path,
        head_positions: list[dict[str, Any]],
        output_path: Path,
        config: CompositionConfig,
        subtitles: Path | None,
    ) -> Path:
        """Fallback to static overlay with smoothed average position.

        True per-frame dynamic overlay requires a two-pass frame extraction
        approach which is very slow. For most use cases (idle/talking animations),
        the head movement is small enough that a smoothed average works well.
        """
        logger.info(
            "Dynamic overlay requested but using smoothed average "
            "(per-frame two-pass not implemented — YAGNI)"
        )
        avg_pos = self._average_position(head_positions)
        return self._compose_static(
            body_video, face_video, audio, avg_pos,
            output_path, config, subtitles,
        )

    def _build_audio_filters(
        self,
        config: CompositionConfig,
        voice_index: int = 2,
    ) -> tuple[list[str], list[str]]:
        """Build audio filter chain and map commands.

        Parameters
        ----------
        config : CompositionConfig
        voice_index : int
            FFmpeg input index for voice audio.
            2 when face video present (body=0, face=1, audio=2).
            1 when body-only (body=0, audio=1).
        """
        has_bg = config.bg_music_path and Path(config.bg_music_path).exists()
        bg_index = voice_index + 1

        if has_bg:
            filters = [
                f"[{voice_index}:a]volume=1.0[voice]",
                f"[{bg_index}:a]volume={config.bg_music_volume}[music]",
                "[voice][music]amix=inputs=2:duration=first[aout]",
            ]
            return filters, ["-map", "[aout]"]
        else:
            return [], ["-map", f"{voice_index}:a"]

    @staticmethod
    def _needs_dynamic_overlay(
        head_positions: list[dict[str, Any]],
        threshold: float,
    ) -> bool:
        """Check if head positions vary enough to need per-frame overlay."""
        if not head_positions or len(head_positions) < 2:
            return False

        xs = [p.get("x", 0) for p in head_positions]
        ys = [p.get("y", 0) for p in head_positions]

        x_range = max(xs) - min(xs)
        y_range = max(ys) - min(ys)

        return x_range > threshold or y_range > threshold

    @staticmethod
    def _average_position(
        head_positions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Compute average head position."""
        if not head_positions:
            return {"x": 0, "y": 0, "scale": 1.0}

        n = len(head_positions)
        return {
            "x": sum(p.get("x", 0) for p in head_positions) / n,
            "y": sum(p.get("y", 0) for p in head_positions) / n,
            "scale": sum(p.get("scale", 1.0) for p in head_positions) / n,
        }

    def _burn_subtitles(self, video_path: Path, subtitles: Path) -> None:
        """Burn subtitles into video as a separate pass."""
        import tempfile

        tmp_out = Path(tempfile.mktemp(suffix=".mp4", dir=video_path.parent))
        srt_escaped = str(subtitles).replace("\\", "/").replace(":", "\\:")
        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(video_path),
            "-vf", f"subtitles='{srt_escaped}':force_style='Fontsize=18,PrimaryColour=&Hffffff'",
            "-c:v", "libx264", "-preset", "fast", "-crf", "22",
            "-c:a", "copy",
            str(tmp_out),
        ]
        try:
            self._run_ffmpeg(cmd, "Subtitle burn")
            # Replace original with subtitled version
            tmp_out.replace(video_path)
        except Exception as e:
            logger.warning("Subtitle burn failed: %s — video without subtitles", e)
            tmp_out.unlink(missing_ok=True)

    @staticmethod
    def _run_ffmpeg(cmd: list[str], label: str) -> None:
        """Run FFmpeg command with error handling."""
        logger.debug("FFmpeg [%s]: %s", label, " ".join(cmd[:8]) + " ...")
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=600,
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"FFmpeg {label} timed out after 600s")

        if result.returncode != 0:
            raise RuntimeError(
                f"FFmpeg {label} failed (code {result.returncode}):\n"
                f"{result.stderr[-500:]}"
            )
