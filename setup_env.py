#!/usr/bin/env python3
"""One-shot environment bootstrap for VietVoice Studio (macOS / Linux).

Installs, idempotently, everything the backend needs — run ONCE with the
system Python, then start the app:

    python3 setup_env.py
    uv run python -m apps.studio_api      # serves API + built FE on :8001

Steps:
  1. uv            — Python package manager        (curl installer → ~/.local/bin)
  2. eSpeak NG     — TTS phonemizer (required)      (brew / apt / pacman)
  3. Node.js ≥22 + FFmpeg — needed by frames mode   (brew / apt / pacman)
  4. Python deps   — torch, fastapi, TTS, ...       (uv sync)
  5. Frames engine — local HyperFrames + Chromium   (npm install)

Safe to re-run: every step checks before installing.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HOME = Path.home()
LOCAL_BIN = HOME / ".local" / "bin"


def info(msg: str) -> None:
    print(f"\n\033[1;36m>> {msg}\033[0m")


def run(cmd: list[str] | str, shell: bool = False) -> None:
    """Run a command, streaming output; raise on failure."""
    printable = cmd if isinstance(cmd, str) else " ".join(cmd)
    print(f"   $ {printable}")
    subprocess.run(cmd, shell=shell, cwd=str(ROOT), check=True)


def find_uv() -> str | None:
    return shutil.which("uv") or next(
        (str(p) for p in (LOCAL_BIN / "uv", HOME / ".cargo" / "bin" / "uv") if p.exists()),
        None,
    )


def ensure_uv() -> str:
    uv = find_uv()
    if uv:
        info(f"uv already installed: {uv}")
        return uv
    info("Installing uv (Python package manager)...")
    run("curl -LsSf https://astral.sh/uv/install.sh | sh", shell=True)
    uv = find_uv()
    if not uv:
        sys.exit("uv install failed — install manually: https://docs.astral.sh/uv/")
    return uv


def ensure_tool(label: str, check: str, brew: str, apt: str = "", pacman: str = "") -> None:
    """Install a system tool via the platform package manager if missing."""
    if shutil.which(check):
        info(f"{label} already installed")
        return
    info(f"Installing {label}...")
    if platform.system() == "Darwin" and shutil.which("brew"):
        run(["brew", "install", brew])
    elif shutil.which("apt") and apt:
        run(f"sudo apt update && sudo apt install -y {apt}", shell=True)
    elif shutil.which("pacman") and pacman:
        run(f"sudo pacman -S --noconfirm {pacman}", shell=True)
    else:
        print(f"   !! Could not auto-install {label}. Install it manually, then re-run.")


def ensure_espeak() -> None:
    if shutil.which("espeak-ng") or shutil.which("espeak"):
        info("eSpeak NG already installed")
        return
    ensure_tool("eSpeak NG (TTS phonemizer)", "espeak-ng", "espeak-ng", "espeak-ng", "espeak-ng")


def ensure_node_ffmpeg() -> None:
    """Node>=22 + FFmpeg — required by the default 'frames' video mode."""
    ensure_tool("FFmpeg", "ffmpeg", "ffmpeg", "ffmpeg", "ffmpeg")
    ensure_tool("Node.js", "node", "node", "nodejs npm", "nodejs npm")
    node = shutil.which("node")
    if node:
        try:
            major = int(subprocess.run(
                [node, "--version"], capture_output=True, text=True, check=True,
            ).stdout.strip().lstrip("v").split(".")[0])
            if major < 22:
                print(f"   !! Node {major} < 22 — frames mode needs Node ≥22. "
                      "Upgrade (e.g. `brew upgrade node` or use nvm).")
        except (subprocess.SubprocessError, ValueError):
            pass


def ensure_python_deps(uv: str) -> None:
    info("Installing Python deps (uv sync — may take a while on first run)...")
    run([uv, "sync"])


def ensure_frames_engine() -> None:
    if not (shutil.which("node") and shutil.which("ffmpeg")):
        print("\n   !! node>=22 + ffmpeg not both found — skipping frames engine.")
        print("      Frames (animated) video mode will be unavailable until installed.")
        return
    project = ROOT / "apps" / "video" / "frames" / "project"
    if (project / "node_modules" / ".bin" / "hyperframes").exists():
        info("Frames engine (HyperFrames) already provisioned")
        return
    info("Provisioning frames engine (HyperFrames + Chromium, one-time)...")
    subprocess.run(
        ["npm", "install", "--no-audit", "--no-fund"],
        cwd=str(project), check=True,
    )


def main() -> None:
    print("VietVoice Studio — environment bootstrap")
    uv = ensure_uv()
    ensure_espeak()
    ensure_node_ffmpeg()
    ensure_python_deps(uv)
    ensure_frames_engine()

    on_path = shutil.which("uv") is not None
    info("Done ✅")
    print("\nNext steps:")
    if not on_path:
        print('  1. Add uv to PATH for this shell:')
        print('       export PATH="$HOME/.local/bin:$PATH"')
        print("     (the installer also added it to your shell rc — new terminals get it)")
    print("  • Start the backend (serves API + built FE on :8001):")
    print("       uv run python -m apps.studio_api")
    print("  • Open http://localhost:8001 → Video tab → 'Animated' mode")


if __name__ == "__main__":
    os.environ.setdefault("PATH", "")
    os.environ["PATH"] = f"{LOCAL_BIN}:{os.environ['PATH']}"
    main()
