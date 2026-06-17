"""BodyRenderer — Python orchestrator for Three.js body animation.

Launches Puppeteer to render a character model with animation clips,
captures frames, stitches into VP9+alpha WebM, exports head bone positions.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable

from apps.video.body.stitch import stitch_frames_to_video

logger = logging.getLogger(__name__)

_BODY_DIR = Path(__file__).resolve().parent
_WEB_DIR = _BODY_DIR / "web"
_CAPTURE_SCRIPT = _WEB_DIR / "capture.js"
_SCRIPTS_DIR = _BODY_DIR.parent / "scripts"  # For node_modules (Puppeteer)


class BodyRenderer:
    """Renders body animation to video using Three.js + Puppeteer.

    Usage::

        renderer = BodyRenderer(fps=30, width=1280, height=720)
        video_path, head_positions = await renderer.render(
            timeline=timeline_dict,
            output_dir=Path("output/"),
        )
    """

    def __init__(
        self,
        fps: int = 30,
        width: int = 1280,
        height: int = 720,
    ):
        self.fps = fps
        self.width = width
        self.height = height

    async def render(
        self,
        timeline: dict[str, Any],
        output_dir: Path,
        character_glb: Path | None = None,
        animation_clips: dict[str, Path] | None = None,
        test_mode: bool = False,
        progress_cb: Callable[[int, str], None] | None = None,
    ) -> tuple[Path, list[dict[str, Any]]]:
        """Render body animation to WebM video.

        Parameters
        ----------
        timeline : dict
            Animation timeline JSON (duration_ms, animations, camera).
        output_dir : Path
            Directory to write output files.
        character_glb : Path, optional
            Path to character GLB model file.
        animation_clips : dict, optional
            Mapping of clip name -> GLB file path.
        test_mode : bool
            If True, render a simple test scene without GLB assets.
        progress_cb : callable, optional
            Callback(percent, message).

        Returns
        -------
        tuple[Path, list[dict]]
            (video_path, head_positions) where head_positions is a list of
            per-frame {frame, x, y, scale} dicts for face overlay.
        """
        output_dir = Path(output_dir).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

        if not test_mode and character_glb and not Path(character_glb).exists():
            raise FileNotFoundError(f"Character GLB not found: {character_glb}")

        duration_ms = timeline.get("duration_ms", 10000)

        if progress_cb:
            progress_cb(0, "Preparing body animation render...")

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)

            # Write capture config
            config = self._build_config(
                timeline, character_glb, animation_clips, test_mode, duration_ms
            )
            config_path = tmp / "capture_config.json"
            config_path.write_text(json.dumps(config, indent=2))

            capture_output_dir = tmp / "capture"
            capture_output_dir.mkdir()

            if progress_cb:
                progress_cb(5, "Launching Puppeteer...")

            # Run Puppeteer capture
            head_positions = await self._run_capture(
                config_path, capture_output_dir, progress_cb, duration_ms
            )

            # Stitch frames to video
            frames_dir = capture_output_dir / "frames"
            if not frames_dir.exists() or not any(frames_dir.glob("*.png")):
                raise RuntimeError("Puppeteer produced no frames")

            if progress_cb:
                progress_cb(85, "Stitching frames to video...")

            video_output = output_dir / "body_video.webm"
            await asyncio.to_thread(
                stitch_frames_to_video,
                frames_dir,
                video_output,
                fps=self.fps,
            )

        # Save head positions
        head_pos_path = output_dir / "head_positions.json"
        head_pos_path.write_text(json.dumps(head_positions, indent=2))

        if progress_cb:
            progress_cb(95, "Body animation complete")

        logger.info(
            "Body render complete: %s (%d head positions)",
            video_output.name, len(head_positions),
        )

        return video_output, head_positions

    def _build_config(
        self,
        timeline: dict[str, Any],
        character_glb: Path | None,
        animation_clips: dict[str, Path] | None,
        test_mode: bool,
        duration_ms: int,
    ) -> dict[str, Any]:
        """Build capture config JSON for Puppeteer."""
        config: dict[str, Any] = {
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "duration_ms": duration_ms,
            "timeline": timeline,
            "test_mode": test_mode,
        }

        if character_glb:
            # Use /asset/ route on local HTTP server (not file:// — CORS blocked)
            config["character_url"] = f"/asset/{Path(character_glb).resolve()}"

        if animation_clips:
            config["animation_clips"] = {
                name: f"/asset/{Path(p).resolve()}"
                for name, p in animation_clips.items()
            }

        return config

    async def _run_capture(
        self,
        config_path: Path,
        output_dir: Path,
        progress_cb: Callable[[int, str], None] | None,
        duration_ms: int,
    ) -> list[dict[str, Any]]:
        """Run Puppeteer capture subprocess and parse output."""
        # Use node from scripts dir (has puppeteer installed)
        node_path = shutil.which("node")
        if not node_path:
            raise RuntimeError("Node.js not found")

        cmd = [
            node_path,
            str(_CAPTURE_SCRIPT),
            "--config", str(config_path),
            "--output", str(output_dir),
        ]

        total_frames = int((duration_ms / 1000) * self.fps)

        # Estimate timeout: 2s per frame + 60s overhead
        timeout_s = max(300, total_frames * 2 + 60)

        logger.info(
            "Running Puppeteer capture: %d frames, timeout=%ds",
            total_frames, timeout_s,
        )

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(_SCRIPTS_DIR),  # So Puppeteer finds node_modules
        )

        head_positions: list[dict[str, Any]] = []

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout_s,
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            raise RuntimeError(
                f"Puppeteer capture timed out after {timeout_s}s"
            )

        if process.returncode != 0:
            error_msg = stderr.decode()[-500:] if stderr else "No error output"
            raise RuntimeError(f"Puppeteer capture failed:\n{error_msg}")

        # Parse JSON lines from stdout
        for line in stdout.decode().strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
                if msg.get("status") == "progress" and progress_cb:
                    pct = 5 + int(msg.get("percent", 0) * 0.8)
                    progress_cb(pct, f"Frame {msg.get('frame', 0)}/{total_frames}")
            except json.JSONDecodeError:
                logger.debug("Non-JSON output: %s", line[:100])

        # Read head positions from file
        head_pos_file = output_dir / "head_positions.json"
        if head_pos_file.exists():
            head_positions = json.loads(head_pos_file.read_text())

        return head_positions
