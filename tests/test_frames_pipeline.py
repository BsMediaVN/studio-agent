"""Phase 03 tests — frames pipeline integration.

Dialogue parsing/voice-assignment are pure unit tests. The end-to-end
`_produce_frames` test uses a STUB voice generator (real TTS needs torch/uv) so
it still exercises parse → per-line voice → composition → HyperFrames render →
final.mp4 with multi-speaker audio.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import apps.video.frames.broll as broll_mod
import apps.video.frames.composition as comp_mod
from apps.video.frames.dialogue import assign_voices, parse_dialogue
from apps.video.frames.renderer import FramesRenderer
from apps.video.pipeline import PipelineConfig, VideoPipeline
from apps.video.voice.generator import VoiceOutput

_AVAILABLE = FramesRenderer.is_available()


# --- pure: dialogue parsing -----------------------------------------------

def test_parse_multispeaker() -> None:
    lines = parse_dialogue("Bình: Xin chào.\nLan: Chào bạn!")
    assert [(l.speaker, l.text) for l in lines] == [
        ("Bình", "Xin chào."), ("Lan", "Chào bạn!")]


def test_parse_plain_text_is_narrator() -> None:
    lines = parse_dialogue("Một câu kể chuyện.")
    assert len(lines) == 1 and lines[0].speaker == "Người kể"


def test_parse_drops_bare_marker_and_blank() -> None:
    lines = parse_dialogue("Bình: Có nội dung\nLan:\n\n   \n")
    assert len(lines) == 1 and lines[0].speaker == "Bình"


def test_parse_digit_colon_is_not_speaker() -> None:
    # "10:30 ..." must not be parsed as speaker "10" (needs a letter in name)
    lines = parse_dialogue("10:30 cuộc họp bắt đầu")
    assert len(lines) == 1 and lines[0].speaker == "Người kể"


def test_parse_prose_splits_sentences_and_strips_markdown() -> None:
    lines = parse_dialogue("# Tiêu đề\nCâu một. Câu hai! Câu ba?")
    texts = [ln.text for ln in lines]
    assert "Tiêu đề" in texts                       # markdown '#' stripped
    assert "Câu một." in texts and "Câu hai!" in texts and "Câu ba?" in texts
    assert all(ln.speaker == "Người kể" for ln in lines)


def test_assign_voices_rotates_and_prefers_default() -> None:
    v = assign_voices(["A", "B", "C", "A"], ["x", "y", "z"], default="y")
    assert v["A"] == "y"  # default goes first
    assert v["B"] != v["A"] and v["C"] != v["B"]
    assert len(set(v.values())) == 3


def test_assign_voices_empty_raises() -> None:
    with pytest.raises(ValueError):
        assign_voices(["A"], [])


# --- end-to-end frames pipeline with a stub TTS ---------------------------

class _StubTTS:
    voice_cache = {"Binh": object(), "Doan": object()}


class _StubVoiceGen:
    """Stands in for VoiceGenerator: writes a tone wav per call."""

    def __init__(self) -> None:
        self._tts = _StubTTS()

    @property
    def available_voices(self) -> list[str]:
        return list(self._tts.voice_cache.keys())

    async def generate(self, *, text, voice_id, output_dir, temperature=0.8,
                        extract_timestamps=None, **_) -> VoiceOutput:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        wav = output_dir / "voice.wav"
        freq = 440 if voice_id == "Binh" else 880
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i",
             f"sine=frequency={freq}:duration=1", "-ar", "48000", "-ac", "1", str(wav)],
            check=True, capture_output=True,
        )
        return VoiceOutput(audio_path=wav, duration_s=1.0, sample_rate=48000)


@pytest.mark.asyncio
@pytest.mark.skipif(not _AVAILABLE, reason="HyperFrames not installed")
async def test_produce_frames_end_to_end() -> None:
    pipeline = VideoPipeline(
        voice_gen=_StubVoiceGen(), face_anim=None, body_renderer=None,
    )
    cfg = PipelineConfig(render_mode="frames", voice_id="Binh")
    final = await pipeline.produce(
        job_id="pytestframesE2E", face_image=None,
        dialogue_text="Bình: Câu một.\nLan: Câu hai.", config=cfg,
    )
    try:
        assert final.exists() and final.name == "final.mp4"
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type",
             "-of", "default=nw=1:nk=1", str(final)],
            capture_output=True, text=True, check=True,
        ).stdout.split()
        assert "video" in probe and "audio" in probe
    finally:
        __import__("shutil").rmtree(final.parent, ignore_errors=True)


# --- B-roll wiring (Phase 05) — render patched, no HyperFrames needed ------

async def _run_frames_broll(monkeypatch, *, frames_broll, attach):
    """Drive _produce_frames with render/assemble patched; return captured segments."""
    captured: dict = {}

    def fake_assemble(comp_dir, segments, cfg=None, *, gsap_src, hyperframes_json):
        captured["segments"] = list(segments)
        Path(comp_dir).mkdir(parents=True, exist_ok=True)
        return Path(comp_dir)

    async def fake_render(self, comp_dir, out_dir, progress_cb=None, timeout_s=600.0):
        out = Path(comp_dir) / f"{Path(comp_dir).name}.mp4"
        out.write_bytes(b"\x00")
        return out

    monkeypatch.setattr(FramesRenderer, "is_available", staticmethod(lambda: True))
    monkeypatch.setattr(FramesRenderer, "render", fake_render)
    monkeypatch.setattr(comp_mod, "assemble_job", fake_assemble)
    monkeypatch.setattr(broll_mod, "attach_broll", attach)

    pipeline = VideoPipeline(voice_gen=_StubVoiceGen(), face_anim=None, body_renderer=None)
    cfg = PipelineConfig(render_mode="frames", voice_id="Binh", frames_broll=frames_broll)
    final = await pipeline.produce(
        job_id="pytestbroll", face_image=None, dialogue_text="Một câu kể.", config=cfg,
    )
    return final, captured


@pytest.mark.asyncio
async def test_frames_broll_off_skips_attach(monkeypatch) -> None:
    calls = {"n": 0}

    async def attach(segments, *, llm, cfg):
        calls["n"] += 1

    final, captured = await _run_frames_broll(monkeypatch, frames_broll=False, attach=attach)
    try:
        assert calls["n"] == 0  # broll never invoked when off
        assert all(s.image_path is None for s in captured["segments"])
    finally:
        __import__("shutil").rmtree(final.parent, ignore_errors=True)


@pytest.mark.asyncio
async def test_frames_broll_on_attaches_images(monkeypatch) -> None:
    async def attach(segments, *, llm, cfg):
        for s in segments:
            s.image_path = Path("/cache/x.jpg")  # simulate a successful fetch

    final, captured = await _run_frames_broll(monkeypatch, frames_broll=True, attach=attach)
    try:
        assert captured["segments"] and all(
            s.image_path == Path("/cache/x.jpg") for s in captured["segments"]
        )
    finally:
        __import__("shutil").rmtree(final.parent, ignore_errors=True)


@pytest.mark.asyncio
async def test_frames_broll_failure_still_completes(monkeypatch) -> None:
    async def attach(segments, *, llm, cfg):
        raise RuntimeError("pexels exploded")

    final, captured = await _run_frames_broll(monkeypatch, frames_broll=True, attach=attach)
    try:
        assert final.exists() and final.name == "final.mp4"  # job survived broll failure
        assert all(s.image_path is None for s in captured["segments"])  # flat-bg fallback
    finally:
        __import__("shutil").rmtree(final.parent, ignore_errors=True)
