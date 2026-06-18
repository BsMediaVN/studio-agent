"""FramesRenderer — render a HyperFrames HTML composition to MP4.

Invokes the **locally installed** HyperFrames binary (pinned in
``project/package.json``) via subprocess — never ``npx --yes`` (no render-time
network). Mirrors ``apps/video/body/renderer.py`` but delegates capture+encode
to HyperFrames. Per-job compositions live under ``project/jobs/<id>/`` so the
single installed dependency tree (incl. Chromium) is shared, never copied.
"""

from __future__ import annotations

import asyncio
import logging
import re
import shutil
import subprocess
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

_FRAMES_DIR = Path(__file__).resolve().parent
_PROJECT_DIR = _FRAMES_DIR / "project"
_LOCAL_BIN = _PROJECT_DIR / "node_modules" / ".bin" / "hyperframes"
JOBS_DIR = _PROJECT_DIR / "jobs"

_MIN_NODE_MAJOR = 22
_PROGRESS_RE = re.compile(r"(\d{1,3})\s*%")
_AVAILABLE_CACHE: bool | None = None
_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def _clean(line: str) -> str:
    """Strip ANSI control codes + trailing trace JSON for human-readable progress."""
    line = _ANSI_RE.sub("", line).strip()
    for marker in ("[INFO]", "[Render:", "{"):
        idx = line.find(marker)
        if idx > 0:
            line = line[:idx].strip()
    return line


class FramesRenderer:
    """Render an HTML composition to MP4 via the local HyperFrames CLI."""

    def __init__(
        self,
        width: int = 1920,
        height: int = 1080,
        fps: int = 30,
        workers: str | int = "auto",
        quality: str = "standard",
    ):
        # width/height come from the composition's data-resolution; kept for
        # callers/logging. No version param — pinned once in package.json (R3).
        self.width = width
        self.height = height
        self.fps = fps
        self.workers = workers
        self.quality = quality

    @staticmethod
    def project_dir() -> Path:
        """Persistent HyperFrames project root (holds the installed deps)."""
        return _PROJECT_DIR

    @staticmethod
    def binary_path() -> Path:
        """Path to the locally installed HyperFrames CLI binary."""
        return _LOCAL_BIN

    @staticmethod
    def gsap_path() -> Path:
        """Path to the vendored GSAP bundle (for self-contained jobs)."""
        return _PROJECT_DIR / "assets" / "lib" / "gsap.min.js"

    @staticmethod
    def is_available() -> bool:
        """True iff node>=22, ffmpeg on PATH, and the local HF binary exists.

        Memoized — the install state is fixed at provisioning time, so this
        avoids re-spawning `node --version` on every job.
        """
        global _AVAILABLE_CACHE
        if _AVAILABLE_CACHE is None:
            _AVAILABLE_CACHE = FramesRenderer._probe_available()
        return _AVAILABLE_CACHE

    @staticmethod
    def _probe_available() -> bool:
        if not _LOCAL_BIN.exists():
            logger.warning("HyperFrames local binary missing: %s", _LOCAL_BIN)
            return False
        if shutil.which("ffmpeg") is None:
            logger.warning("ffmpeg not found on PATH")
            return False
        node = shutil.which("node")
        if not node:
            logger.warning("node not found on PATH")
            return False
        try:
            out = subprocess.run(
                [node, "--version"], capture_output=True, text=True, timeout=10,
            ).stdout.strip().lstrip("v")
            major = int(out.split(".")[0])
        except (subprocess.SubprocessError, ValueError) as exc:
            logger.warning("node version probe failed: %s", exc)
            return False
        if major < _MIN_NODE_MAJOR:
            logger.warning("node %s < required %d", out, _MIN_NODE_MAJOR)
            return False
        return True

    async def render(
        self,
        job_dir: Path,
        output_dir: Path,
        progress_cb: Callable[[int, str], None] | None = None,
        timeout_s: float = 600.0,
    ) -> Path:
        """Render ``job_dir/index.html`` → an MP4 in ``output_dir``.

        ``job_dir`` must be a subdirectory of the persistent project (created by
        the composition builder) containing ``index.html`` + ``assets/``.
        Returns the produced MP4 path.
        """
        job_dir = Path(job_dir).resolve()
        index_html = job_dir / "index.html"
        if not index_html.exists():
            raise FileNotFoundError(f"Composition not found: {index_html}")
        if not self.is_available():
            raise RuntimeError(
                "HyperFrames not available (need node>=22, ffmpeg, local binary). "
                "Run `npm install` in apps/video/frames/project/."
            )

        output_dir = Path(output_dir).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{job_dir.name}.mp4"

        # Render the job as its OWN project dir. The `<project> -c <subpath>`
        # form resolves relative asset src against the project root, silently
        # dropping the audio track — so each job must be self-contained
        # (index.html + assets/ + meta.json + hyperframes.json). Shared deps
        # (Chromium) come from the binary's install, not the target dir.
        cmd = [
            str(_LOCAL_BIN), "render", str(job_dir),
            "-o", str(output_path),
            "-f", str(self.fps),
            "-w", str(self.workers),
            "-q", self.quality,
        ]

        if progress_cb:
            progress_cb(0, "Starting frames render...")
        logger.info("Frames render: %s", " ".join(cmd))

        await self._run(cmd, progress_cb, timeout_s)

        if not output_path.exists() or output_path.stat().st_size == 0:
            raise RuntimeError(f"Render produced no output: {output_path}")
        if progress_cb:
            progress_cb(100, "Frames render complete")
        logger.info("Frames render complete: %s (%d bytes)",
                    output_path, output_path.stat().st_size)
        return output_path

    async def _run(
        self,
        cmd: list[str],
        progress_cb: Callable[[int, str], None] | None,
        timeout_s: float,
    ) -> None:
        """Run the render subprocess, stream progress, kill cleanly on timeout."""
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(_PROJECT_DIR),
        )
        tail: list[str] = []

        async def _pump() -> None:
            assert process.stdout is not None
            async for raw in process.stdout:
                line = raw.decode(errors="replace").strip()
                if not line:
                    continue
                tail.append(_clean(line) or line)
                del tail[:-40]
                if progress_cb:
                    m = _PROGRESS_RE.search(line)
                    if m:
                        pct = min(99, max(1, int(m.group(1))))
                        progress_cb(pct, _clean(line)[:100] or "Rendering...")

        try:
            await asyncio.wait_for(asyncio.gather(_pump(), process.wait()), timeout_s)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()  # reap — no zombie / fd leak
            raise RuntimeError(f"Frames render timed out after {timeout_s:.0f}s")

        if process.returncode != 0:
            raise RuntimeError(
                "HyperFrames render failed (exit %d):\n%s"
                % (process.returncode, "\n".join(tail[-25:]))
            )
