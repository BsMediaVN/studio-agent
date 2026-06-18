"""VideoPipeline — full orchestrator: prompt + face image -> final video.

Chains all modules: script generation -> voice -> face animation ->
body animation -> video composition.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Literal

from apps.video.composer.composer import CompositionConfig, VideoComposer
from apps.video.composer.subtitles import generate_srt
from apps.video.voice.generator import VoiceGenerator, VoiceOutput

if TYPE_CHECKING:  # heavy face/body stack imported lazily — frames mode skips it
    from apps.video.body.renderer import BodyRenderer
    from apps.video.face.animator import FaceAnimator

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_OUTPUT_DIR = _PROJECT_ROOT / "output" / "studio" / "video"


@dataclass
class PipelineConfig:
    """Configuration for the video pipeline."""

    # "frames" (default) = animated HTML composition via HyperFrames (no face
    # image needed); "face" = photorealistic SadTalker talking head.
    render_mode: Literal["frames", "face"] = "frames"
    voice_id: str = "Binh"
    target_duration_s: float | None = None
    temperature: float = 0.8
    extract_alpha: bool = False
    body_fps: int = 30
    body_width: int = 1280
    body_height: int = 720
    body_test_mode: bool = True  # True until Mixamo assets available
    burn_subtitles: bool = True
    composition: CompositionConfig = field(default_factory=CompositionConfig)
    keep_intermediates: bool = False
    # frames mode rendering
    frames_fps: int = 30
    frames_width: int = 1920
    frames_height: int = 1080
    frames_workers: str | int = "auto"
    frames_gap_s: float = 0.15


class VideoPipeline:
    """Full video generation pipeline.

    Usage::

        pipeline = VideoPipeline(voice_gen, face_anim, body_renderer)
        result = await pipeline.produce(
            job_id="abc123",
            face_image=Path("face.png"),
            prompt="Nhân vật giới thiệu về AI",
            config=PipelineConfig(voice_id="Binh"),
        )
    """

    def __init__(
        self,
        voice_gen: VoiceGenerator,
        face_anim: FaceAnimator,
        body_renderer: BodyRenderer,
        composer: VideoComposer | None = None,
    ):
        self._voice_gen = voice_gen
        self._face_anim = face_anim
        self._body_renderer = body_renderer
        self._composer = composer or VideoComposer()
        self._semaphore = asyncio.Semaphore(1)

    async def produce(
        self,
        job_id: str,
        face_image: Path | None,
        dialogue_text: str,
        config: PipelineConfig | None = None,
        progress_cb: Callable[[int, str], None] | None = None,
        voice_map: dict[str, str] | None = None,
    ) -> Path:
        """Run the full video generation pipeline.

        Parameters
        ----------
        job_id : str
            Unique job identifier.
        face_image : Path
            Input face image.
        dialogue_text : str
            Text for the character to speak.
        config : PipelineConfig, optional
            Pipeline configuration.
        progress_cb : callable, optional
            Callback(percent, message) for progress updates.

        Returns
        -------
        Path
            Path to final MP4 video.
        """
        config = config or PipelineConfig()

        async with self._semaphore:
            return await self._produce_impl(
                job_id, face_image, dialogue_text, config, progress_cb, voice_map,
            )

    async def _produce_impl(
        self,
        job_id: str,
        face_image: Path | None,
        dialogue_text: str,
        config: PipelineConfig,
        progress_cb: Callable[[int, str], None] | None,
        voice_map: dict[str, str] | None = None,
    ) -> Path:
        """Internal pipeline implementation."""
        if not dialogue_text.strip():
            raise ValueError("Dialogue text cannot be empty")

        # Sanitize job_id (prevent path traversal)
        if not re.match(r'^[a-zA-Z0-9_-]+$', job_id):
            raise ValueError(f"Invalid job_id: must be alphanumeric/hyphen/underscore")

        # Ensure output dir exists before disk check
        _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        # Check disk space (500MB minimum)
        free_space = shutil.disk_usage(_OUTPUT_DIR).free
        if free_space < 500 * 1024 * 1024:
            raise RuntimeError(
                f"Insufficient disk space: {free_space / 1e6:.0f}MB free, need 500MB+"
            )

        # Create job output directory
        job_dir = _OUTPUT_DIR / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        # Frames mode (default): animated composition, no face image required.
        if config.render_mode == "frames":
            try:
                return await self._produce_frames(
                    job_id, dialogue_text, config, job_dir, progress_cb, voice_map,
                )
            except Exception as e:
                logger.error("Frames pipeline failed for job %s: %s", job_id, e)
                raise

        # Face mode: requires a face image.
        if face_image is None:
            raise ValueError("face_image is required when render_mode='face'")
        face_image = Path(face_image).resolve()
        if not face_image.exists():
            raise FileNotFoundError(f"Face image not found: {face_image}")

        try:
            # Stage 1: Voice Generation (0-30%)
            if progress_cb:
                progress_cb(0, "Generating voice...")

            voice_output = await self._generate_voice(
                dialogue_text, config, job_dir, progress_cb,
            )

            # Stage 2: Face Animation (30-70%)
            if progress_cb:
                progress_cb(30, "Animating face...")

            face_video = await self._generate_face(
                face_image, voice_output, config, job_dir, progress_cb,
            )

            # Stage 3: Subtitles (70-75%)
            if progress_cb:
                progress_cb(70, "Generating subtitles...")

            srt_path = None
            if config.burn_subtitles and voice_output.word_timestamps:
                srt_path = job_dir / "subtitles.srt"
                generate_srt(voice_output.word_timestamps, srt_path)

            final_video = job_dir / "final.mp4"

            if config.body_test_mode or face_video is None:
                # Talking head mode: face video + audio directly (no body)
                if progress_cb:
                    progress_cb(75, "Composing talking head video...")

                if face_video and face_video.exists():
                    await asyncio.to_thread(
                        self._compose_talking_head,
                        face_video, voice_output.audio_path,
                        final_video, srt_path,
                    )
                else:
                    raise RuntimeError("Face animation failed — no face video produced")
            else:
                # Full mode: face + body + composition
                if progress_cb:
                    progress_cb(75, "Rendering body animation...")

                body_video, head_positions = await self._generate_body(
                    voice_output, config, job_dir, progress_cb,
                )

                if progress_cb:
                    progress_cb(90, "Composing final video...")

                await asyncio.to_thread(
                    self._composer.compose,
                    body_video=body_video,
                    audio=voice_output.audio_path,
                    output_path=final_video,
                    face_video=face_video,
                    head_positions=head_positions,
                    config=config.composition,
                    subtitles=srt_path,
                )

            # Stage 6: Cleanup (95-100%)
            if not config.keep_intermediates:
                self._cleanup_intermediates(job_dir, final_video)

            if progress_cb:
                progress_cb(100, "Video generation complete")

            size_mb = final_video.stat().st_size / 1e6
            logger.info(
                "Pipeline complete: job=%s, output=%s (%.1f MB)",
                job_id, final_video.name, size_mb,
            )
            return final_video

        except Exception as e:
            logger.error("Pipeline failed for job %s: %s", job_id, e)
            raise

    async def _produce_frames(
        self,
        job_id: str,
        dialogue_text: str,
        config: PipelineConfig,
        job_dir: Path,
        progress_cb: Callable[[int, str], None] | None,
        voice_map: dict[str, str] | None = None,
    ) -> Path:
        """Frames mode: dialogue → per-line voice → HTML composition → MP4."""
        from apps.video.frames import FramesRenderer
        from apps.video.frames.composition import (
            CompositionConfig as FramesCompositionConfig,
            DialogueSegment,
            assemble_job,
        )
        from apps.video.frames.dialogue import assign_voices, parse_dialogue

        if not FramesRenderer.is_available():
            raise RuntimeError(
                "Frames mode unavailable: need node>=22, ffmpeg, and the local "
                "HyperFrames install (run `make setup-frames`)."
            )

        lines = parse_dialogue(dialogue_text)
        if not lines:
            raise ValueError("No dialogue lines parsed from input text")

        # Prefer a caller-supplied (e.g. gender-aware) voice map; else rotate.
        voices = voice_map or assign_voices(
            [ln.speaker for ln in lines], self._voice_gen.available_voices, config.voice_id,
        )

        # Optional total-duration target: fit the speech to it by adjusting each
        # line's speed, allocated proportionally by text length. None = natural.
        line_targets: list[float | None] = [None] * len(lines)
        if config.target_duration_s:
            total_chars = sum(len(ln.text) for ln in lines) or 1
            gap_total = config.frames_gap_s * max(0, len(lines) - 1)
            speech_target = max(1.0, config.target_duration_s - gap_total)
            line_targets = [
                max(0.6, speech_target * len(ln.text) / total_chars) for ln in lines
            ]

        segments: list[DialogueSegment] = []
        for i, line in enumerate(lines):
            if progress_cb:
                progress_cb(int(i / len(lines) * 55), f"Voicing line {i + 1}/{len(lines)}...")
            # Line-level captions need no word timestamps → skip Whisper per line.
            vo = await self._voice_gen.generate(
                text=line.text,
                voice_id=voices.get(line.speaker) or config.voice_id,
                output_dir=job_dir / f"line-{i}",
                target_duration_s=line_targets[i],
                temperature=config.temperature,
                extract_timestamps=False,
            )
            segments.append(DialogueSegment(
                speaker=line.speaker, text=line.text,
                audio_path=vo.audio_path, duration_s=vo.duration_s,
            ))

        if progress_cb:
            progress_cb(60, "Building composition...")

        comp_dir = FramesRenderer.project_dir() / "jobs" / job_id
        assemble_job(
            comp_dir, segments,
            FramesCompositionConfig(
                width=config.frames_width, height=config.frames_height,
                fps=config.frames_fps, gap_s=config.frames_gap_s,
            ),
            gsap_src=FramesRenderer.gsap_path(),
            hyperframes_json=FramesRenderer.project_dir() / "hyperframes.json",
        )

        def _render_progress(pct: int, msg: str) -> None:
            if progress_cb:
                progress_cb(60 + int(pct * 0.38), msg)

        renderer = FramesRenderer(
            width=config.frames_width, height=config.frames_height,
            fps=config.frames_fps, workers=config.frames_workers,
        )
        try:
            rendered = await renderer.render(comp_dir, job_dir, progress_cb=_render_progress)
            final_video = job_dir / "final.mp4"
            shutil.move(str(rendered), str(final_video))
        finally:
            # comp_dir is an engine-internal artifact under the shared HyperFrames
            # project tree — always remove it (even on failure / keep_intermediates).
            shutil.rmtree(comp_dir, ignore_errors=True)
            if not config.keep_intermediates:
                for line_dir in job_dir.glob("line-*"):
                    shutil.rmtree(line_dir, ignore_errors=True)

        if progress_cb:
            progress_cb(100, "Video generation complete")
        logger.info("Frames pipeline complete: job=%s, %d line(s), %s",
                    job_id, len(segments), final_video.name)
        return final_video

    async def _generate_voice(
        self,
        text: str,
        config: PipelineConfig,
        job_dir: Path,
        progress_cb: Callable[[int, str], None] | None,
    ) -> VoiceOutput:
        """Stage 1: Generate voice audio + timestamps."""
        def _voice_progress(pct: int, msg: str) -> None:
            if progress_cb:
                mapped = int(pct * 0.3)  # 0-30% of pipeline
                progress_cb(mapped, msg)

        return await self._voice_gen.generate(
            text=text,
            voice_id=config.voice_id,
            output_dir=job_dir,
            target_duration_s=config.target_duration_s,
            temperature=config.temperature,
            progress_cb=_voice_progress,
        )

    async def _generate_face(
        self,
        face_image: Path,
        voice_output: VoiceOutput,
        config: PipelineConfig,
        job_dir: Path,
        progress_cb: Callable[[int, str], None] | None,
    ) -> Path | None:
        """Stage 2: Generate face animation video."""
        if self._face_anim is None or not self._face_anim.is_available:
            logger.warning("Face animation not available — skipping")
            if progress_cb:
                progress_cb(55, "Face animation skipped (not available)")
            return None

        def _face_progress(pct: int, msg: str) -> None:
            if progress_cb:
                mapped = 30 + int(pct * 0.25)  # 30-55% of pipeline
                progress_cb(mapped, msg)

        return await self._face_anim.generate(
            face_image=face_image,
            audio_path=voice_output.audio_path,
            output_dir=job_dir / "face",
            progress_cb=_face_progress,
        )

    async def _generate_body(
        self,
        voice_output: VoiceOutput,
        config: PipelineConfig,
        job_dir: Path,
        progress_cb: Callable[[int, str], None] | None,
    ) -> tuple[Path, list[dict[str, Any]]]:
        """Stage 3: Generate body animation video."""
        # Build animation timeline from voice duration
        duration_ms = int(voice_output.duration_s * 1000)
        timeline = {
            "duration_ms": duration_ms,
            "animations": [
                {
                    "clip": "idle",
                    "start_ms": 0,
                    "end_ms": duration_ms,
                    "crossfade_ms": 300,
                },
            ],
            "camera": [
                {"t_ms": 0, "zoom": 1.0, "pan_x": 0, "pan_y": 0},
                {"t_ms": duration_ms, "zoom": 1.05, "pan_x": 0, "pan_y": 0},
            ],
        }

        def _body_progress(pct: int, msg: str) -> None:
            if progress_cb:
                mapped = 55 + int(pct * 0.25)  # 55-80% of pipeline
                progress_cb(mapped, msg)

        return await self._body_renderer.render(
            timeline=timeline,
            output_dir=job_dir / "body",
            test_mode=config.body_test_mode,
            progress_cb=_body_progress,
        )

    @staticmethod
    def _compose_talking_head(
        face_video: Path,
        audio: Path,
        output_path: Path,
        subtitles: Path | None = None,
    ) -> None:
        """Compose face video + audio into talking head MP4 (no body)."""
        import subprocess

        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(face_video),
            "-i", str(audio),
            "-map", "0:v",
            "-map", "1:a",
            "-c:v", "libx264", "-preset", "fast", "-crf", "22",
            "-c:a", "aac", "-b:a", "128k",
            "-shortest",
            str(output_path),
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            raise RuntimeError(f"Talking head composition failed: {result.stderr[-300:]}")

        # Burn subtitles if available
        if subtitles and Path(subtitles).exists():
            import tempfile

            tmp_out = Path(tempfile.mktemp(suffix=".mp4", dir=output_path.parent))
            srt_escaped = str(subtitles).replace("\\", "/").replace(":", "\\:")
            sub_cmd = [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-i", str(output_path),
                "-vf", f"subtitles='{srt_escaped}':force_style='Fontsize=18,PrimaryColour=&Hffffff'",
                "-c:v", "libx264", "-preset", "fast", "-crf", "22",
                "-c:a", "copy",
                str(tmp_out),
            ]
            try:
                result = subprocess.run(sub_cmd, capture_output=True, text=True, timeout=300)
                if result.returncode == 0:
                    tmp_out.replace(output_path)
                else:
                    tmp_out.unlink(missing_ok=True)
            except Exception:
                tmp_out.unlink(missing_ok=True)

    @staticmethod
    def _cleanup_intermediates(job_dir: Path, final_video: Path) -> None:
        """Remove intermediate files, keeping only final video."""
        for subdir in ["face", "body"]:
            sub = job_dir / subdir
            if sub.exists() and sub.is_dir():
                shutil.rmtree(sub, ignore_errors=True)

        # Remove intermediate audio files (keep final voice.wav for reference)
        for pattern in ["voice_raw.wav", "voice_normalized.wav"]:
            p = job_dir / pattern
            if p.exists():
                p.unlink(missing_ok=True)

        logger.debug("Cleaned up intermediates for %s", job_dir.name)
