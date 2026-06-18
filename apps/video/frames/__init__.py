"""Frames render mode — HTML composition → MP4 via the HyperFrames engine.

Product-layer alternative to the bespoke ``body/`` capture + ``composer/`` stitch.
Deterministic, CPU-only, offline (local pinned HyperFrames binary + vendored GSAP).
"""

from apps.video.frames.renderer import FramesRenderer

__all__ = ["FramesRenderer"]
