"""Video Pipeline API — FastAPI endpoints for video generation.

Registers endpoints on the existing studio_app router.
Follows patterns from studio_api.py: JobManager, WebSocket progress,
Pydantic validation, background tasks.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import time
import uuid
from pathlib import Path
from typing import Any, Literal

from fastapi import File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

_OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "output" / "studio" / "video"
_MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------

class VideoGenerateRequest(BaseModel):
    """Request parameters for video generation."""

    prompt: str = Field(min_length=1, max_length=20000)
    voice_id: str
    # "frames" (animated, default, no face image) | "face" (SadTalker realistic)
    render_mode: Literal["frames", "face"] = "frames"
    # None = auto (length follows the content); set = fit content to this time.
    target_duration_s: float | None = Field(default=None, ge=3, le=600)
    burn_subtitles: bool = True
    body_test_mode: bool = True  # True until Mixamo assets available
    # frames mode only: fetch content-matched Pexels background imagery (opt-in).
    frames_broll: bool = False


class VideoStatusResponse(BaseModel):
    """Video pipeline status."""

    face_engine_available: bool
    body_renderer_ready: bool
    frames_renderer_ready: bool
    video_pipeline_enabled: bool
    # B-roll background imagery is usable only when a Pexels key is configured.
    broll_available: bool = False


# ---------------------------------------------------------------------------
# VideoProducer — API-layer wrapper
# ---------------------------------------------------------------------------

class VideoProducer:
    """Manages video generation jobs: file I/O, job tracking, background tasks."""

    def __init__(self, pipeline: Any, job_manager: Any):
        from apps.video.pipeline import VideoPipeline
        self._pipeline: VideoPipeline = pipeline
        self._jobs = job_manager
        self._output_files: dict[str, str] = {}

    async def start_job(
        self,
        face_image: UploadFile | None,
        config: VideoGenerateRequest,
    ) -> str:
        """Validate image, create job, launch pipeline in background."""
        # Create job (JobManager generates the job_id)
        job_id = await self._jobs.create_job()

        # Face image only needed for realistic (face) mode.
        face_path: Path | None = None
        if config.render_mode == "face":
            face_anim = self._pipeline._face_anim
            if face_anim is None or not getattr(face_anim, "is_available", False):
                raise HTTPException(
                    422,
                    "Realistic (face) mode is unavailable on this server "
                    "(SadTalker / OpenCV not installed). Use Animated mode.",
                )
            if face_image is None:
                raise HTTPException(422, "face_image is required for realistic (face) mode")
            face_path = await self._save_face_image(face_image, job_id)

        # Build pipeline config
        from apps.video.pipeline import PipelineConfig

        pipeline_config = PipelineConfig(
            render_mode=config.render_mode,
            voice_id=config.voice_id,
            target_duration_s=config.target_duration_s,
            burn_subtitles=config.burn_subtitles,
            body_test_mode=config.body_test_mode,
            frames_broll=config.frames_broll,
        )

        # Launch in background
        async def _run() -> None:
            t0 = time.monotonic()
            try:
                loop = asyncio.get_running_loop()

                def _progress(pct: int, msg: str) -> None:
                    loop.call_soon_threadsafe(
                        asyncio.ensure_future,
                        self._jobs.update(
                            job_id,
                            progress=pct,
                            current_step=msg,
                        ),
                    )

                # Read the pasted content verbatim — TTS each line/sentence and
                # render. Multi-speaker via "Name: line" markers.
                output = await self._pipeline.produce(
                    job_id=job_id,
                    face_image=face_path,
                    dialogue_text=config.prompt,
                    config=pipeline_config,
                    progress_cb=_progress,
                )

                self._output_files[job_id] = str(output)
                duration_ms = round((time.monotonic() - t0) * 1000)
                await self._jobs.update(
                    job_id,
                    status="complete",
                    progress=100,
                    current_step="Done",
                    result_url=f"/studio/video/download/{job_id}",
                )
                logger.info(
                    "video_production_completed job_id=%s duration_ms=%d",
                    job_id, duration_ms,
                )

            except Exception as e:
                logger.exception("Video production failed job_id=%s", job_id)
                await self._jobs.update(
                    job_id, status="error", error=str(e)[:500],
                )
                # Cleanup failed job directory
                job_dir = _OUTPUT_DIR / job_id
                if job_dir.exists():
                    shutil.rmtree(job_dir, ignore_errors=True)

        asyncio.create_task(_run())

        logger.info(
            "video_production_queued job_id=%s voice=%s duration_target=%s",
            job_id, config.voice_id, config.target_duration_s,
        )
        return job_id

    async def _save_face_image(
        self, face_image: UploadFile, job_id: str,
    ) -> Path:
        """Validate and save uploaded face image."""
        # Read content
        content = await face_image.read()

        # Validate size
        if len(content) > _MAX_IMAGE_SIZE:
            raise HTTPException(
                413, f"Image too large ({len(content) / 1e6:.1f}MB). Max: 10MB"
            )

        if len(content) < 100:
            raise HTTPException(400, "Image file is empty or too small")

        # Validate image type via PIL (imghdr removed in Python 3.13)
        import io
        try:
            from PIL import Image
            img = Image.open(io.BytesIO(content))
            img_format = (img.format or "").lower()  # Read before verify
            img.verify()
        except Exception:
            raise HTTPException(400, "Invalid or corrupt image file")

        if img_format not in ("png", "jpeg", "bmp", "gif"):
            raise HTTPException(
                400,
                f"Invalid image type: {img_format}. "
                f"Allowed: PNG, JPEG, BMP",
            )

        # Save to job directory
        job_dir = _OUTPUT_DIR / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        ext = ".png" if img_format == "png" else ".jpg"
        face_path = job_dir / f"input_face{ext}"
        face_path.write_bytes(content)

        logger.info(
            "Face image saved: %s (%d bytes, type=%s)",
            face_path.name, len(content), img_format,
        )
        return face_path

    def get_output_path(self, job_id: str) -> str | None:
        """Get output file path for a completed job."""
        return self._output_files.get(job_id)


# ---------------------------------------------------------------------------
# Module-level state (initialized by init_video_pipeline)
# ---------------------------------------------------------------------------

video_producer: VideoProducer | None = None
_tts_manager_ref: Any = None  # Stored reference to avoid import issues


def init_video_pipeline(tts_manager: Any, job_manager: Any) -> None:
    """Initialize video pipeline components.

    Called from studio_api.py init_studio() or standalone.
    """
    global video_producer, _tts_manager_ref
    _tts_manager_ref = tts_manager

    from apps.video.voice.generator import VoiceGenerator
    from apps.video.frames.renderer import FramesRenderer
    from apps.video.pipeline import VideoPipeline

    voice_gen = VoiceGenerator(tts_manager, extract_timestamps=True)

    # Face/realistic stack (SadTalker + body + composer) needs cv2/torch and may
    # be unavailable. Frames mode does NOT need it — keep the pipeline working
    # for frames even when the face stack fails to import/construct.
    face_anim = body_renderer = composer = None
    try:
        from apps.video.face.animator import FaceAnimator
        from apps.video.body.renderer import BodyRenderer
        from apps.video.composer.composer import VideoComposer

        face_anim = FaceAnimator(backend="sadtalker")
        body_renderer = BodyRenderer(fps=30, width=1280, height=720)
        composer = VideoComposer()
    except Exception as e:
        logger.warning(
            "Realistic (face) video mode unavailable: %s — frames mode still enabled", e,
        )

    # Reuse the studio's LLM stack for B-roll keyword extraction (DRY).
    try:
        from apps.studio_api import LLMScriptGenerator
        llm = LLMScriptGenerator()
    except Exception as e:  # noqa: BLE001 — broll falls back to flat bg without it
        logger.warning("LLM unavailable for B-roll keyword extraction: %s", e)
        llm = None

    # B-roll tunables (orientation, cache_dir) from config.yaml → studio.video.broll.
    broll_settings: dict = {}
    try:
        import yaml
        cfg_path = Path(__file__).resolve().parents[2] / "config.yaml"
        data = yaml.safe_load(cfg_path.read_text()) or {}
        broll_settings = (((data.get("studio") or {}).get("video") or {}).get("broll")) or {}
    except Exception as e:  # noqa: BLE001 — defaults are fine without config
        logger.warning("Could not read B-roll config: %s", e)

    pipeline = VideoPipeline(
        voice_gen=voice_gen,
        face_anim=face_anim,
        body_renderer=body_renderer,
        composer=composer,
        llm=llm,
        broll_settings=broll_settings,
    )

    video_producer = VideoProducer(pipeline, job_manager)
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    logger.info(
        "Video pipeline initialized: frames=%s, face=%s",
        FramesRenderer.is_available(), face_anim is not None,
    )


def register_video_endpoints(studio_app: Any) -> None:
    """Register video pipeline endpoints on the studio FastAPI app.

    Call this after creating studio_app in studio_api.py.
    """

    @studio_app.post("/video/generate")
    async def generate_video(
        # Accept str too: browsers (incl. cached builds) may send an empty
        # face_image field in frames mode — tolerate it instead of 422-ing.
        face_image: UploadFile | str | None = File(None),
        prompt: str = Form(..., min_length=1, max_length=20000),
        voice_id: str = Form(...),
        render_mode: Literal["frames", "face"] = Form("frames"),
        target_duration_s: float | None = Form(None, ge=3, le=600),
        burn_subtitles: bool = Form(True),
        body_test_mode: bool = Form(True),
        frames_broll: bool = Form(False),
    ) -> dict[str, str]:
        """Start a video generation job.

        frames mode (default): text prompt → animated video (no face image).
        face mode: upload a face image → realistic talking head.
        Returns job_id for progress tracking via WebSocket.
        """
        if video_producer is None:
            raise HTTPException(503, "Video pipeline not initialized")

        # Disk space check
        _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        free_space = shutil.disk_usage(_OUTPUT_DIR).free
        if free_space < 500 * 1024 * 1024:
            raise HTTPException(
                507,
                f"Insufficient disk space: {free_space / 1e6:.0f}MB free",
            )

        # Validate voice_id (match studio_api.py pattern — 503 if not loaded)
        if not _tts_manager_ref or not _tts_manager_ref.is_loaded:
            raise HTTPException(503, "TTS engine not loaded yet")
        available = set(_tts_manager_ref.voice_cache.keys())
        if voice_id not in available:
            raise HTTPException(
                422,
                f"Unknown voice_id '{voice_id}'. Available: {sorted(available)}",
            )

        config = VideoGenerateRequest(
            prompt=prompt,
            voice_id=voice_id,
            render_mode=render_mode,
            target_duration_s=target_duration_s,
            burn_subtitles=burn_subtitles,
            body_test_mode=body_test_mode,
            frames_broll=frames_broll,
        )

        # Only a real uploaded file counts; an empty/string field → no image.
        face_file = face_image if isinstance(face_image, UploadFile) else None
        job_id = await video_producer.start_job(face_file, config)
        return {"status": "ok", "job_id": job_id}

    @studio_app.get("/video/download/{job_id}")
    async def download_video(job_id: str) -> FileResponse:
        """Download the generated video file."""
        # Validate job_id format (match the pipeline's sanitizer)
        if not re.match(r'^[a-zA-Z0-9_-]+$', job_id):
            raise HTTPException(400, "Invalid job_id format")

        if video_producer is None:
            raise HTTPException(503, "Video pipeline not initialized")

        file_path = video_producer.get_output_path(job_id)
        if not file_path:
            raise HTTPException(404, "Video not found or job not complete")

        resolved = Path(file_path).resolve()
        safe_dir = _OUTPUT_DIR.resolve()

        # Path traversal guard
        if not resolved.is_relative_to(safe_dir):
            raise HTTPException(403, "Forbidden")

        if not resolved.exists():
            raise HTTPException(404, "Video file not found on disk")

        return FileResponse(
            str(resolved),
            media_type="video/mp4",
            filename=f"video_{job_id}.mp4",
        )

    @studio_app.get("/video/status")
    async def video_status() -> dict[str, Any]:
        """Get video pipeline status."""
        from apps.video.frames import FramesRenderer

        broll_available = bool(os.environ.get("PEXELS_API_KEY"))
        if video_producer is None:
            return VideoStatusResponse(
                face_engine_available=False,
                body_renderer_ready=False,
                frames_renderer_ready=FramesRenderer.is_available(),
                video_pipeline_enabled=False,
                broll_available=broll_available,
            ).model_dump()

        face_anim = video_producer._pipeline._face_anim
        return VideoStatusResponse(
            face_engine_available=bool(face_anim and getattr(face_anim, "is_available", False)),
            body_renderer_ready=video_producer._pipeline._body_renderer is not None,
            frames_renderer_ready=FramesRenderer.is_available(),
            video_pipeline_enabled=True,
            broll_available=broll_available,
        ).model_dump()

    logger.info("Video pipeline endpoints registered")
