"""
Studio Voice API — Multi-character voice production backend.

Endpoints:
  POST /generate-script  — LLM-powered script generation
  POST /produce          — Full TTS production pipeline
  GET  /voices           — Available voice presets
  GET  /status           — Engine status
  GET  /download/{job_id} — Download produced audio
  WS   /progress/{job_id} — Real-time production progress
"""

import os
import re
import json
import uuid
import time
import shutil
import asyncio
import logging
import tempfile
import subprocess
from pathlib import Path
from typing import ClassVar, Literal, Optional

import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from vieneu import Vieneu
from vieneu_utils.core_utils import (
    join_audio_chunks, split_text_into_chunks,
    compute_speed_for_duration, trim_audio, pad_audio,
)
from apps.logging_config import setup_logging, get_request_id
from apps.middleware import RequestLoggingMiddleware

# Configure structured logging (console + rotating JSON file)
setup_logging(dev_mode=bool(os.environ.get("STUDIO_DEV", "1")))

logger = logging.getLogger("studio_api")

# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------

class ScriptCharacter(BaseModel):
    name: str
    gender: Literal["M", "F"]
    voice_tone: str = ""
    voice_id: str = ""


class DialogueLine(BaseModel):
    character: str
    text: str
    emotion: str = "neutral"
    pause_after_ms: int = 300
    line_type: Literal["dialogue", "narration"] = "dialogue"


class Scene(BaseModel):
    scene_num: int
    setting: str = ""
    dialogue: list[DialogueLine]


class Script(BaseModel):
    title: str
    characters: list[ScriptCharacter]
    scenes: list[Scene]


class CharacterPreset(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    gender: Literal["M", "F"]


class GenerateScriptRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)
    max_characters: int = Field(default=4, le=10, ge=1)
    language: str = "vi"
    mode: Literal["dialogue", "story"] = "dialogue"
    genre: str = ""
    target_duration_s: Optional[float] = Field(default=None, ge=0.5, le=600, description="Target audio duration in seconds. Constrains script length.")
    characters: Optional[list[CharacterPreset]] = Field(default=None, description="Pre-configured characters. When provided, LLM must use exactly these characters.")


class ProduceRequest(BaseModel):
    script: Script
    voice_map: dict[str, str]  # {character_name: voice_id}
    silence_gap: float = 0.3
    crossfade: float = 0.0
    output_format: Literal["wav", "mp3"] = "wav"
    normalize: bool = True
    temperature: float = Field(default=0.8, ge=0.1, le=1.5)
    top_k: int = Field(default=50, ge=10, le=100)
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    target_duration_s: Optional[float] = Field(default=None, ge=0.5, le=600, description="Target audio duration in seconds. Mutually exclusive with speed.")


class JobStatus(BaseModel):
    job_id: str
    status: Literal["queued", "processing", "complete", "error"] = "queued"
    progress: int = 0  # 0-100
    current_step: str = ""
    result_url: str | None = None
    error: str | None = None
    created_at: float = 0.0


# ---------------------------------------------------------------------------
# TTSManager — singleton, caches all voice presets
# ---------------------------------------------------------------------------

class TTSManager:
    def __init__(self):
        self.engine: Optional[Vieneu] = None
        self.voice_cache: dict[str, dict] = {}
        self.sample_rate: int = 24000
        self._lock = asyncio.Lock()
        self._loaded = False

    async def init(self, backbone_repo: str, codec_repo: str,
                   backbone_device: str = "cpu", codec_device: str = "cpu"):
        """Load TTS engine and cache all voice presets."""
        logger.info("Loading TTS engine: %s", backbone_repo)
        self.engine = Vieneu(
            mode="standard",
            backbone_repo=backbone_repo,
            codec_repo=codec_repo,
            backbone_device=backbone_device,
            codec_device=codec_device,
        )
        self.sample_rate = getattr(self.engine, "sample_rate", 24000)

        # Cache all preset voices
        voices = self.engine.list_preset_voices()
        for desc, vid in voices:
            try:
                self.voice_cache[vid] = self.engine.get_preset_voice(vid)
                logger.info("Cached voice: %s (%s)", vid, desc)
            except Exception as e:
                logger.warning("Failed to cache voice %s: %s", vid, e)

        self._loaded = True
        logger.info("TTS ready — %d voices cached", len(self.voice_cache))

    def init_from_existing(self, engine: Vieneu):
        """Reuse an already-loaded TTS engine (shared with web_stream)."""
        self.engine = engine
        self.sample_rate = getattr(engine, "sample_rate", 24000)

        voices = engine.list_preset_voices()
        for item in voices:
            if isinstance(item, tuple):
                desc, vid = item
            else:
                vid = item
            try:
                self.voice_cache[vid] = engine.get_preset_voice(vid)
            except Exception:
                pass

        self._loaded = True
        logger.info("TTS shared — %d voices cached", len(self.voice_cache))

    @property
    def is_loaded(self) -> bool:
        return self._loaded and self.engine is not None

    async def synthesize(self, text: str, voice_name: str,
                         temperature: float = 0.8, top_k: int = 50) -> np.ndarray:
        """Synthesize text with a cached voice preset. Thread-safe via asyncio.Lock."""
        if not self.is_loaded:
            raise RuntimeError("TTS engine not loaded")
        voice_data = self.voice_cache.get(voice_name)
        if voice_data is None:
            raise ValueError(f"Voice '{voice_name}' not found. Available: {list(self.voice_cache.keys())}")

        try:
            async with self._lock:
                loop = asyncio.get_running_loop()
                audio = await loop.run_in_executor(
                    None, lambda: self.engine.infer(
                        text=text, voice=voice_data,
                        temperature=temperature, top_k=top_k,
                    )
                )
            return audio
        except Exception as e:
            logger.error("TTS synthesize failed for voice '%s': %s", voice_name, e)
            raise

    def synthesize_stream_sync(self, text: str, voice_data: dict,
                                temperature: float = 0.8, top_k: int = 50):
        """Synchronous streaming synthesis — yields audio chunks under the lock."""
        if not self.is_loaded:
            raise RuntimeError("TTS engine not loaded")
        try:
            yield from self.engine.infer_stream(text, voice=voice_data,
                                                 temperature=temperature, top_k=top_k)
        except Exception as e:
            logger.error("TTS stream failed: %s", e)
            raise

    def close(self):
        if self.engine:
            try:
                self.engine.close()
            except Exception:
                pass
            self.engine = None
            self._loaded = False

    def get_voice_list(self) -> list[dict]:
        """Return voice metadata for the API."""
        voices = []
        if self.engine:
            for item in self.engine.list_preset_voices():
                if isinstance(item, tuple):
                    desc, vid = item
                else:
                    desc, vid = item, item
                voices.append({
                    "id": vid,
                    "name": desc,
                    "cached": vid in self.voice_cache,
                })
        return voices


# ---------------------------------------------------------------------------
# LLMScriptGenerator — Claude SDK or OpenAI API
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a professional Vietnamese screenplay writer. Generate a structured dialogue script from the user's prompt.

RULES:
- Output ONLY valid JSON matching the schema below. No explanation text.
- Maximum {max_characters} characters. Detect gender from Vietnamese names (M/F).
- Each character must have distinct personality reflected in dialogue.
- All dialogue text must be in Vietnamese.
- Include natural pauses (pause_after_ms: 200-1000) between lines.
- Use emotion tags appropriately: neutral, happy, sad, angry, fearful, surprised, whisper.

JSON SCHEMA:
{{
  "title": "string",
  "characters": [
    {{"name": "string", "gender": "M|F", "voice_tone": "description of voice quality"}}
  ],
  "scenes": [
    {{
      "scene_num": 1,
      "setting": "optional scene description",
      "dialogue": [
        {{
          "character": "character name (must match characters array)",
          "text": "Vietnamese dialogue line",
          "emotion": "neutral|happy|sad|angry|fearful|surprised|whisper",
          "pause_after_ms": 300
        }}
      ]
    }}
  ]
}}

GENDER DETECTION GUIDELINES (Vietnamese names):
- Common male names: Binh, Tuan, Minh, Duc, Hung, Nam, Thanh, Hieu, Long, Quang, Vinh, Tuyen
- Common female names: Lan, Huong, Ngoc, Ly, Doan, Mai, Thao, Linh, Hoa, Trang, Phuong
- When ambiguous, default to context clues or assign based on role description."""

STORY_SYSTEM_PROMPT = """You are a professional Vietnamese audiobook writer. Generate a structured story script with narration and dialogue from the user's prompt.

RULES:
- Output ONLY valid JSON matching the schema below. No explanation text.
- Maximum {max_characters} speaking characters PLUS a special "Narrator" character.
- The Narrator reads descriptions, scene settings, actions, transitions, and introduces who is speaking.
- Alternate between narration and dialogue naturally, like a real audiobook.
- Before each character speaks, add a narration line like "Minh noi:" or "Lan dap:" to indicate the speaker.
- All text must be in Vietnamese.
- Include natural pauses: narration lines 400-800ms, dialogue 200-500ms.
- Use emotion tags: neutral, happy, sad, angry, fearful, surprised, whisper.

IMPORTANT: The "Narrator" character MUST be included in the characters array with gender "M" or "F" (pick one for narrator voice).

JSON SCHEMA:
{{
  "title": "string",
  "characters": [
    {{"name": "Narrator", "gender": "M|F", "voice_tone": "calm, clear storytelling voice"}},
    {{"name": "string", "gender": "M|F", "voice_tone": "description"}}
  ],
  "scenes": [
    {{
      "scene_num": 1,
      "setting": "scene description",
      "dialogue": [
        {{
          "character": "Narrator",
          "text": "narration/description text",
          "emotion": "neutral",
          "pause_after_ms": 500,
          "line_type": "narration"
        }},
        {{
          "character": "Narrator",
          "text": "Minh noi:",
          "emotion": "neutral",
          "pause_after_ms": 200,
          "line_type": "narration"
        }},
        {{
          "character": "Minh",
          "text": "character dialogue",
          "emotion": "happy",
          "pause_after_ms": 300,
          "line_type": "dialogue"
        }}
      ]
    }}
  ]
}}

PATTERN: Narration -> "Character noi:" -> Character dialogue -> Narration -> ...

GENDER DETECTION GUIDELINES (Vietnamese names):
- Common male names: Binh, Tuan, Minh, Duc, Hung, Nam, Thanh, Hieu, Long, Quang, Vinh, Tuyen
- Common female names: Lan, Huong, Ngoc, Ly, Doan, Mai, Thao, Linh, Hoa, Trang, Phuong
- When ambiguous, default to context clues."""


class LLMScriptGenerator:
    """LLM script generator with 3 modes:
    - claude_cli: Uses local Claude CLI (subscription, no API key needed) — DEFAULT
    - claude: Uses Anthropic SDK (requires ANTHROPIC_API_KEY)
    - openai: Uses OpenAI SDK (requires OPENAI_API_KEY)

    All config read from env vars:
      STUDIO_LLM_PROVIDER=claude_cli|claude|openai  (default: claude_cli)
      STUDIO_LLM_MODEL=model-name                   (default per provider)
      ANTHROPIC_API_KEY=sk-ant-...                   (for provider=claude)
      OPENAI_API_KEY=sk-...                          (for provider=openai)
    """

    def __init__(self, provider: str | None = None, config: dict | None = None):
        self.provider = provider or os.environ.get("STUDIO_LLM_PROVIDER", "claude_cli")
        self.config = config or {}
        self.model = (
            os.environ.get("STUDIO_LLM_MODEL")
            or self.config.get("model")
            or self._default_model()
        )

    def _default_model(self) -> str:
        if self.provider == "openai":
            return "gpt-4o"
        return "claude-sonnet-4-20250514"

    async def generate(self, prompt: str, max_characters: int = 4, mode: str = "dialogue", target_duration_s: float | None = None, genre: str = "", characters: list[dict] | None = None) -> dict:
        if mode == "story":
            system = STORY_SYSTEM_PROMPT.format(max_characters=max_characters)
        else:
            system = SYSTEM_PROMPT.format(max_characters=max_characters)

        if genre:
            system += f"\n\nSTORY GENRE: Write in the style of a {genre} story. Match the tone, pacing, and themes of this genre."

        # Inject pre-configured characters into prompt
        if characters:
            char_lines = []
            for c in characters:
                gender_label = "nam" if c.get("gender") == "M" else "nữ"
                char_lines.append(f"- {c['name']} ({gender_label})")
            char_list = "\n".join(char_lines)
            system += f"""

CHARACTER CONSTRAINT (CRITICAL):
You MUST use EXACTLY the following characters. Do NOT add new characters. Do NOT rename them. Do NOT change their gender.
{char_list}
- Use all listed characters in the dialogue. Each character must appear at least once."""

        # Add duration constraint to prompt so LLM generates appropriately-sized script
        if target_duration_s is not None:
            # Vietnamese TTS: ~10 chars/second → target chars = duration * 10
            target_chars = int(target_duration_s * 10)
            if target_duration_s < 60:
                duration_label = f"{int(target_duration_s)} giây"
            else:
                mins = int(target_duration_s // 60)
                secs = int(target_duration_s % 60)
                duration_label = f"{mins} phút" + (f" {secs}s" if secs else "")
            system += f"""

DURATION CONSTRAINT (CRITICAL):
- Target audio duration: {duration_label}.
- Vietnamese TTS reads ~10 characters/second.
- Total dialogue text across ALL lines MUST be approximately {target_chars} characters.
- You MUST write ENOUGH content to fill the target duration. Do NOT write less.
- Add more scenes, more dialogue lines, more detail, longer sentences to reach {target_chars} characters total.
- If target is long (>1 minute), create a rich, detailed story with multiple scenes and exchanges."""

        if self.provider == "openai":
            return await self._call_openai(prompt, system)
        elif self.provider == "claude":
            return await self._call_claude_sdk(prompt, system)
        else:
            return await self._call_claude_cli(prompt, system)

    async def complete_text(self, prompt: str, system: str = "") -> str:
        """Freeform short-text completion (no JSON parsing) using the configured
        provider. Used for small side-tasks like B-roll keyword extraction —
        keeps a single LLM stack (DRY) instead of a second client."""
        loop = asyncio.get_running_loop()
        if self.provider == "openai":
            import openai
            api_key = os.environ.get("OPENAI_API_KEY")
            if not api_key:
                raise RuntimeError("OPENAI_API_KEY not set")
            client = openai.OpenAI(api_key=api_key)
            resp = await loop.run_in_executor(None, lambda: client.chat.completions.create(
                model=self.model, max_tokens=64,
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": prompt}],
            ))
            return resp.choices[0].message.content or ""
        if self.provider == "claude":
            import anthropic
            api_key = os.environ.get("ANTHROPIC_API_KEY")
            if not api_key:
                raise RuntimeError("ANTHROPIC_API_KEY not set")
            client = anthropic.Anthropic(api_key=api_key)
            resp = await loop.run_in_executor(None, lambda: client.messages.create(
                model=self.model, max_tokens=64,
                system=system or "You are a helpful assistant.",
                messages=[{"role": "user", "content": prompt}],
            ))
            return resp.content[0].text
        # claude_cli (default) — uses local subscription, no API key.
        claude_bin = shutil.which("claude")
        if not claude_bin:
            raise RuntimeError("Claude CLI not found")
        full = f"{system}\n\n---\n\n{prompt}" if system else prompt
        result = await loop.run_in_executor(None, lambda: subprocess.run(
            [claude_bin, "-p", full, "--output-format", "json"],
            capture_output=True, text=True, timeout=120,
        ))
        if result.returncode != 0:
            raise RuntimeError(f"Claude CLI failed: {result.stderr[:200]}")
        try:
            return json.loads(result.stdout).get("result", result.stdout)
        except json.JSONDecodeError:
            return result.stdout

    async def _call_claude_cli(self, prompt: str, system: str) -> dict:
        """Call Claude via local CLI (uses subscription, no API key needed)."""
        import shutil
        claude_bin = shutil.which("claude")
        if not claude_bin:
            raise RuntimeError(
                "Claude CLI not found. Install it or switch to provider=claude/openai in .env"
            )

        full_prompt = f"{system}\n\n---\n\nUser request: {prompt}"
        cmd = [claude_bin, "-p", full_prompt, "--output-format", "json"]

        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, lambda: subprocess.run(
            cmd, capture_output=True, text=True, timeout=300
        ))

        if result.returncode != 0:
            stderr = result.stderr.strip()
            raise RuntimeError(f"Claude CLI failed (exit {result.returncode}): {stderr[:200]}")

        # Claude CLI --output-format json wraps response in {"result": "...", ...}
        try:
            cli_output = json.loads(result.stdout)
            raw = cli_output.get("result", result.stdout)
        except json.JSONDecodeError:
            raw = result.stdout

        return self._parse_json(raw)

    async def _call_claude_sdk(self, prompt: str, system: str) -> dict:
        """Call Claude via Anthropic SDK (requires ANTHROPIC_API_KEY)."""
        try:
            import anthropic
        except ImportError:
            raise RuntimeError("anthropic package not installed. pip install anthropic")

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set in .env")

        client = anthropic.Anthropic(api_key=api_key)
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(None, lambda: client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        ))

        raw = response.content[0].text
        return self._parse_json(raw)

    async def _call_openai(self, prompt: str, system: str) -> dict:
        """Call OpenAI API (requires OPENAI_API_KEY)."""
        try:
            import openai
        except ImportError:
            raise RuntimeError("openai package not installed. pip install openai")

        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY not set in .env")

        client = openai.OpenAI(api_key=api_key)
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(None, lambda: client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
        ))

        raw = response.choices[0].message.content
        return self._parse_json(raw)

    @staticmethod
    def _parse_json(raw: str) -> dict:
        """Extract JSON from LLM response, stripping markdown fences if present."""
        text = raw.strip()
        # Strip ```json ... ``` fences
        match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if match:
            text = match.group(1).strip()
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            logger.warning("LLM raw response (first 500 chars): %s", text[:500])
            raise
        # Validate against Pydantic model
        Script(**data)
        return data


# ---------------------------------------------------------------------------
# JobManager — in-memory async job tracking
# ---------------------------------------------------------------------------

class JobManager:
    def __init__(self):
        self._jobs: dict[str, JobStatus] = {}
        self._lock = asyncio.Lock()

    async def create_job(self) -> str:
        job_id = uuid.uuid4().hex[:12]
        async with self._lock:
            self._jobs[job_id] = JobStatus(
                job_id=job_id,
                status="queued",
                created_at=time.time(),
            )
        return job_id

    async def update(self, job_id: str, **kwargs):
        async with self._lock:
            job = self._jobs.get(job_id)
            if job:
                for k, v in kwargs.items():
                    setattr(job, k, v)

    async def get(self, job_id: str) -> JobStatus | None:
        return self._jobs.get(job_id)

    async def cleanup_old(self, max_age: float = 3600, output_files: dict | None = None):
        """Remove jobs older than max_age seconds and their output files."""
        now = time.time()
        async with self._lock:
            expired = [jid for jid, j in self._jobs.items() if now - j.created_at > max_age]
            for jid in expired:
                self._jobs.pop(jid, None)
                if output_files is not None:
                    path = output_files.pop(jid, None)
                    if path:
                        for suffix in ["", "_norm.wav", ".mp3"]:
                            p = Path(path).with_suffix(suffix) if suffix else Path(path)
                            p.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# FFmpeg Helpers
# ---------------------------------------------------------------------------

def _run_ffmpeg(args: list[str]) -> subprocess.CompletedProcess:
    """Run FFmpeg with error handling."""
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"] + args
    return subprocess.run(cmd, capture_output=True, text=True, check=True)


def normalize_audio(input_path: str, output_path: str):
    _run_ffmpeg(["-i", input_path, "-af", "loudnorm=I=-23", output_path])


def convert_to_mp3(input_path: str, output_path: str):
    _run_ffmpeg(["-i", input_path, "-codec:a", "libmp3lame", "-q:a", "4", output_path])


def _build_atempo_chain(speed: float) -> str:
    """Build chained atempo filters for speed factors outside 0.5-2.0."""
    filters = []
    remaining = speed
    while remaining > 2.0:
        filters.append("atempo=2.0")
        remaining /= 2.0
    while remaining < 0.5:
        filters.append("atempo=0.5")
        remaining /= 0.5
    filters.append(f"atempo={remaining:.4f}")
    return ",".join(filters)


def adjust_speed(input_path: str, output_path: str, speed: float):
    """Adjust audio playback speed using FFmpeg atempo filter.
    Supports chained atempo for factors outside 0.5-2.0."""
    af = _build_atempo_chain(speed)
    _run_ffmpeg(["-i", input_path, "-af", af, output_path])


def adjust_to_target_duration(
    input_path: str, output_path: str,
    target_s: float, sample_rate: int = 24000,
) -> dict:
    """Adjust audio file to match target duration. Returns metadata."""
    import soundfile as _sf
    data, sr = _sf.read(input_path)
    actual_s = len(data) / sr

    speed, needs_trim, needs_pad = compute_speed_for_duration(actual_s, target_s)

    # Apply speed via FFmpeg
    if abs(speed - 1.0) > 0.01:
        adjust_speed(input_path, output_path, speed)
        data, sr = _sf.read(output_path)
    else:
        import shutil as _shutil
        _shutil.copy2(input_path, output_path)

    target_samples = int(target_s * sr)

    if needs_trim:
        data = trim_audio(data, target_samples, sr=sr)
        _sf.write(output_path, data, sr)
    elif needs_pad:
        data = pad_audio(data, target_samples)
        _sf.write(output_path, data, sr)

    achieved_s = len(data) / sr
    return {
        "target_duration_s": target_s,
        "actual_duration_s": round(achieved_s, 2),
        "speed_applied": round(speed, 3),
        "was_trimmed": needs_trim,
        "was_padded": needs_pad,
    }


def has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


# ---------------------------------------------------------------------------
# StudioProducer — full production pipeline
# ---------------------------------------------------------------------------

class StudioProducer:
    def __init__(self, tts: TTSManager, jobs: JobManager):
        self.tts = tts
        self.jobs = jobs
        self._semaphore = asyncio.Semaphore(1)  # max 1 concurrent production

    async def produce(self, job_id: str, request: ProduceRequest) -> str:
        """Run full pipeline: parse script -> TTS per segment -> merge -> post-process.
        Returns path to output audio file.
        """
        async with self._semaphore:
            return await self._produce_inner(job_id, request)

    async def _produce_inner(self, job_id: str, request: ProduceRequest) -> str:
        script = request.script
        voice_map = request.voice_map

        # Flatten all dialogue lines across scenes
        segments: list[tuple[str, str, int]] = []  # (voice_id, text, pause_ms)
        for scene in script.scenes:
            for line in scene.dialogue:
                voice_id = voice_map.get(line.character)
                if not voice_id:
                    raise ValueError(f"No voice mapped for character '{line.character}'")
                segments.append((voice_id, line.text, line.pause_after_ms))

        total = len(segments)
        if total == 0:
            raise ValueError("Script has no dialogue lines")

        await self.jobs.update(job_id, status="processing", current_step="Synthesizing audio")

        # Synthesize each segment
        audio_chunks: list[np.ndarray] = []
        pause_chunks: list[np.ndarray] = []  # silence after each segment

        for i, (voice_id, text, pause_ms) in enumerate(segments):
            step_label = f"Segment {i + 1}/{total}"
            await self.jobs.update(
                job_id,
                progress=int((i / total) * 80),
                current_step=step_label,
            )

            # Split long text into smaller chunks for TTS
            text_chunks = split_text_into_chunks(text, max_chars=256)
            seg_audios = []
            for chunk in text_chunks:
                audio = await self.tts.synthesize(
                    chunk, voice_id,
                    temperature=request.temperature, top_k=request.top_k,
                )
                seg_audios.append(audio)

            # Join sub-chunks of same segment (no gap)
            if len(seg_audios) == 1:
                segment_audio = seg_audios[0]
            else:
                segment_audio = join_audio_chunks(seg_audios, sr=self.tts.sample_rate)

            audio_chunks.append(segment_audio)

            # Add pause after segment
            if pause_ms > 0:
                silence_samples = int(self.tts.sample_rate * pause_ms / 1000)
                pause_chunks.append(np.zeros(silence_samples, dtype=np.float32))
            else:
                pause_chunks.append(np.array([], dtype=np.float32))

        # Merge all segments with configured silence/crossfade
        await self.jobs.update(job_id, progress=80, current_step="Merging audio")

        # Interleave audio and pauses
        merged_parts: list[np.ndarray] = []
        for i, chunk in enumerate(audio_chunks):
            merged_parts.append(chunk)
            if i < len(audio_chunks) - 1:  # no pause after last segment
                # Use per-line pause or fallback to request silence_gap
                if len(pause_chunks[i]) > 0:
                    merged_parts.append(pause_chunks[i])
                elif request.silence_gap > 0:
                    silence_samples = int(self.tts.sample_rate * request.silence_gap)
                    merged_parts.append(np.zeros(silence_samples, dtype=np.float32))

        if request.crossfade > 0:
            final_audio = join_audio_chunks(
                merged_parts, sr=self.tts.sample_rate, crossfade_p=request.crossfade
            )
        else:
            final_audio = np.concatenate(merged_parts) if merged_parts else np.array([], dtype=np.float32)

        # Save to temp file
        output_dir = Path(tempfile.gettempdir()) / "studio_voice_output"
        output_dir.mkdir(exist_ok=True)

        wav_path = str(output_dir / f"{job_id}.wav")
        self.tts.engine.save(final_audio, wav_path)

        # Post-processing
        final_path = wav_path
        ffmpeg_available = has_ffmpeg()
        duration_meta = None

        # Speed adjustment (before normalize)
        if request.speed != 1.0 and ffmpeg_available:
            await self.jobs.update(job_id, progress=85, current_step="Adjusting speed")
            speed_path = str(output_dir / f"{job_id}_speed.wav")
            loop = asyncio.get_running_loop()
            try:
                await loop.run_in_executor(None, adjust_speed, final_path, speed_path, request.speed)
                final_path = speed_path
            except subprocess.CalledProcessError as e:
                logger.warning("FFmpeg speed adjust failed: %s", e.stderr)

        if request.normalize and ffmpeg_available:
            await self.jobs.update(job_id, progress=90, current_step="Normalizing audio")
            norm_path = str(output_dir / f"{job_id}_norm.wav")
            loop = asyncio.get_running_loop()
            try:
                await loop.run_in_executor(None, normalize_audio, final_path, norm_path)
                final_path = norm_path
            except subprocess.CalledProcessError as e:
                logger.warning("FFmpeg normalize failed: %s", e.stderr)

        if request.output_format == "mp3" and ffmpeg_available:
            await self.jobs.update(job_id, progress=95, current_step="Converting to MP3")
            mp3_path = str(output_dir / f"{job_id}.mp3")
            loop = asyncio.get_running_loop()
            try:
                await loop.run_in_executor(None, convert_to_mp3, final_path, mp3_path)
                final_path = mp3_path
            except subprocess.CalledProcessError as e:
                logger.warning("FFmpeg MP3 conversion failed: %s", e.stderr)

        await self.jobs.update(
            job_id,
            status="complete",
            progress=100,
            current_step="Done",
            result_url=f"/studio/download/{job_id}",
        )

        return final_path


# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------

studio_app = FastAPI(title="Studio Voice API")

studio_app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:8001", "*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)
studio_app.add_middleware(RequestLoggingMiddleware)


# Serve client HTML at root
_CLIENT_HTML = Path(__file__).parent.parent / "client" / "client.html"


@studio_app.get("/", response_class=HTMLResponse)
async def serve_client():
    """Serve the Studio Voice web client."""
    if _CLIENT_HTML.exists():
        return HTMLResponse(_CLIENT_HTML.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Client not found</h1>", status_code=404)


# Global exception handler — catches unhandled errors, logs them, returns clean JSON
from starlette.requests import Request
from starlette.responses import JSONResponse
from fastapi.exceptions import RequestValidationError


@studio_app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Log 422 validation failures with the exact offending fields."""
    logger.warning(
        "422 validation on %s %s: %s", request.method, request.url.path, exc.errors(),
    )
    return JSONResponse(status_code=422, content={"detail": exc.errors()})


@studio_app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch all unhandled exceptions — log full traceback, return safe error."""
    logger.exception(
        "Unhandled error on %s %s request_id=%s",
        request.method, request.url.path, get_request_id(),
    )
    # Don't expose internal details to client
    if isinstance(exc, HTTPException):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "path": str(request.url.path)},
    )

# Shared state — initialized by mount_studio() or lifespan
tts_manager = TTSManager()
job_manager = JobManager()
producer: StudioProducer | None = None
llm_generator: LLMScriptGenerator | None = None

# Map job_id -> output file path
_output_files: dict[str, str] = {}


def init_studio(config: dict | None = None):
    """Initialize studio components. Called during app startup.
    LLM provider/model read from env vars (STUDIO_LLM_PROVIDER, STUDIO_LLM_MODEL).
    """
    global producer, llm_generator
    config = config or {}

    producer = StudioProducer(tts_manager, job_manager)

    # Provider from env, fallback to config, fallback to claude_cli
    llm_generator = LLMScriptGenerator()
    logger.info("LLM provider: %s, model: %s", llm_generator.provider, llm_generator.model)

    # Load custom cloned voices from disk
    _load_custom_voices()


# --- Endpoints ---

@studio_app.post("/generate-script")
async def generate_script(req: GenerateScriptRequest):
    """Generate a structured script from a natural language prompt via LLM."""
    if llm_generator is None:
        raise HTTPException(500, "LLM generator not initialized")
    t0 = time.monotonic()
    logger.info(
        "script_generation_started prompt_len=%d provider=%s mode=%s request_id=%s",
        len(req.prompt), llm_generator.provider, req.mode, get_request_id(),
    )
    try:
        chars_dicts = [c.model_dump() for c in req.characters] if req.characters else None
        script_data = await llm_generator.generate(req.prompt, req.max_characters, req.mode, req.target_duration_s, req.genre, chars_dicts)
        duration_ms = round((time.monotonic() - t0) * 1000)
        char_count = len(script_data.get("characters", []))
        scene_count = len(script_data.get("scenes", []))
        logger.info(
            "script_generation_completed provider=%s duration_ms=%d characters=%d scenes=%d request_id=%s",
            llm_generator.provider, duration_ms, char_count, scene_count, get_request_id(),
        )
        return {"status": "ok", "script": script_data}
    except json.JSONDecodeError as e:
        logger.warning("LLM returned invalid JSON request_id=%s error=%s", get_request_id(), str(e)[:200])
        raise HTTPException(422, "LLM returned invalid JSON. Try again.")
    except ValueError as e:
        logger.warning("LLM schema validation failed request_id=%s error=%s", get_request_id(), str(e)[:200])
        raise HTTPException(422, "LLM output did not match expected script schema")
    except RuntimeError as e:
        raise HTTPException(500, str(e))
    except Exception:
        logger.exception("Script generation failed request_id=%s", get_request_id())
        raise HTTPException(500, "Internal error during script generation")


@studio_app.post("/produce")
async def produce_audio(req: ProduceRequest):
    """Start a production job. Returns job_id for progress tracking."""
    if producer is None:
        raise HTTPException(500, "Producer not initialized")
    if not tts_manager.is_loaded:
        raise HTTPException(503, "TTS engine not loaded yet")

    # Validate all characters have voice mappings
    char_names = {c.name for c in req.script.characters}
    missing = char_names - set(req.voice_map.keys())
    if missing:
        raise HTTPException(422, f"Missing voice mapping for characters: {sorted(missing)}")

    # Validate voice_ids exist
    available = set(tts_manager.voice_cache.keys())
    invalid = set(req.voice_map.values()) - available
    if invalid:
        raise HTTPException(422, f"Unknown voice IDs: {sorted(invalid)}. Available: {sorted(available)}")

    # Validate max characters
    if len(req.script.characters) > 10:
        raise HTTPException(422, f"Maximum 10 characters allowed")

    job_id = await job_manager.create_job()
    segments_count = sum(len(s.dialogue) for s in req.script.scenes)
    request_id_snapshot = get_request_id()

    logger.info(
        "tts_production_queued job_id=%s segments=%d provider=%s request_id=%s",
        job_id, segments_count, llm_generator.provider if llm_generator else "n/a",
        request_id_snapshot,
    )

    async def _run():
        t0 = time.monotonic()
        try:
            output_path = await producer.produce(job_id, req)
            _output_files[job_id] = output_path
            duration_ms = round((time.monotonic() - t0) * 1000)
            logger.info(
                "tts_production_completed job_id=%s segments=%d duration_ms=%d request_id=%s",
                job_id, segments_count, duration_ms, request_id_snapshot,
            )
        except Exception as e:
            logger.exception(
                "Production failed job_id=%s request_id=%s", job_id, request_id_snapshot,
            )
            await job_manager.update(job_id, status="error", error=str(e))

    asyncio.create_task(_run())
    return {"status": "ok", "job_id": job_id}


@studio_app.get("/voices")
async def get_voices():
    """Return available voice presets with metadata."""
    return {"voices": tts_manager.get_voice_list()}


@studio_app.get("/status")
async def get_status():
    """Return engine status."""
    return {
        "engine_loaded": tts_manager.is_loaded,
        "voices_cached": len(tts_manager.voice_cache),
        "voice_ids": list(tts_manager.voice_cache.keys()),
        "sample_rate": tts_manager.sample_rate,
        "ffmpeg_available": has_ffmpeg(),
    }


@studio_app.get("/download/{job_id}")
async def download_audio(job_id: str):
    """Download the produced audio file."""
    file_path = _output_files.get(job_id)
    if not file_path:
        # Fall back to job-based check for regular production jobs
        job = await job_manager.get(job_id)
        if not job:
            raise HTTPException(404, "Job not found")
        if job.status != "complete":
            raise HTTPException(409, f"Job not complete (status: {job.status})")
        file_path = _output_files.get(job_id)
    if not file_path or not Path(file_path).exists():
        raise HTTPException(404, "Output file not found")

    # Path traversal guard
    safe_dir = Path(tempfile.gettempdir()) / "studio_voice_output"
    if not Path(file_path).resolve().is_relative_to(safe_dir.resolve()):
        raise HTTPException(403, "Forbidden")

    media_type = "audio/mpeg" if file_path.endswith(".mp3") else "audio/wav"
    filename = f"studio_{job_id}{Path(file_path).suffix}"
    return FileResponse(file_path, media_type=media_type, filename=filename)


@studio_app.get("/job/{job_id}")
async def get_job_status(job_id: str):
    """Get current job status."""
    job = await job_manager.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job.model_dump()


@studio_app.websocket("/progress/{job_id}")
async def ws_progress(websocket: WebSocket, job_id: str):
    """WebSocket for real-time production progress updates."""
    await websocket.accept()

    job = await job_manager.get(job_id)
    if not job:
        await websocket.send_json({"error": "Job not found"})
        await websocket.close()
        return

    try:
        while True:
            job = await job_manager.get(job_id)
            if not job:
                break
            await websocket.send_json(job.model_dump())
            if job.status in ("complete", "error"):
                break
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Pipeline — full auto: text in → audio out
# ---------------------------------------------------------------------------

class PipelineRequest(BaseModel):
    """One-shot pipeline: text → script → voices → audio."""
    text: str = Field(min_length=1, max_length=2000)
    mode: Literal["dialogue", "story"] = "dialogue"
    max_characters: int = Field(default=4, le=10, ge=1)
    voice_overrides: dict[str, str] = Field(default_factory=dict)  # optional {char: voice_id}
    output_format: Literal["wav", "mp3"] = "wav"
    normalize: bool = True
    silence_gap: float = 0.3
    crossfade: float = 0.0
    temperature: float = Field(default=0.8, ge=0.1, le=1.5)
    top_k: int = Field(default=50, ge=10, le=100)
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    target_duration_s: Optional[float] = Field(default=None, ge=0.5, le=600)


def _auto_assign_voices(characters: list[dict], available: list[str],
                         overrides: dict[str, str] | None = None) -> dict[str, str]:
    """Auto-assign voices from available pool by gender. Returns {char_name: voice_id}."""
    overrides = overrides or {}
    # Known gender pools (fallback if model has these voices)
    known_male = ["Binh", "Tuyen", "Vinh"]
    known_female = ["Doan", "Ly", "Ngoc"]
    male_pool = [v for v in known_male if v in available] or available
    female_pool = [v for v in known_female if v in available] or available

    assignment = {}
    used = set(overrides.values())
    mi, fi = 0, 0

    for char in characters:
        name = char.get("name", "")
        if name in overrides:
            assignment[name] = overrides[name]
            continue

        gender = char.get("gender", "M")
        pool = female_pool if gender == "F" else male_pool

        # Find unused voice from pool
        assigned = False
        for _ in range(len(pool)):
            voice = pool[mi % len(pool)] if gender == "M" else pool[fi % len(pool)]
            if gender == "M":
                mi += 1
            else:
                fi += 1
            if voice not in used:
                assignment[name] = voice
                used.add(voice)
                assigned = True
                break

        # Fallback: use any available voice
        if not assigned:
            for v in available:
                if v not in used:
                    assignment[name] = v
                    used.add(v)
                    break
            else:
                # All exhausted, reuse first available
                assignment[name] = available[0] if available else ""

    return assignment


@studio_app.post("/pipeline")
async def pipeline(req: PipelineRequest):
    """Full auto pipeline: text → LLM script → auto voice assign → TTS produce → audio file.

    Returns the audio file directly. No need to call multiple endpoints.
    """
    if not tts_manager.is_loaded:
        raise HTTPException(503, "TTS engine not loaded")
    if llm_generator is None or producer is None:
        raise HTTPException(500, "Studio not initialized")

    # Step 1: Generate script
    try:
        script_data = await llm_generator.generate(req.text, req.max_characters, req.mode, req.target_duration_s)
        script = Script(**script_data)
    except Exception as e:
        logger.exception("Pipeline: script generation failed")
        raise HTTPException(422, f"Script generation failed: {str(e)[:200]}")

    # Step 2: Auto-assign voices
    available_voices = list(tts_manager.voice_cache.keys())
    if not available_voices:
        raise HTTPException(503, "No voices cached")

    char_dicts = [{"name": c.name, "gender": c.gender} for c in script.characters]
    voice_map = _auto_assign_voices(char_dicts, available_voices, req.voice_overrides)

    # Validate all characters have voices
    for c in script.characters:
        if c.name not in voice_map or voice_map[c.name] not in available_voices:
            voice_map[c.name] = available_voices[0]

    # Step 3: Produce audio (synchronous — wait for result)
    job_id = await job_manager.create_job()
    produce_req = ProduceRequest(
        script=script,
        voice_map=voice_map,
        silence_gap=req.silence_gap,
        crossfade=req.crossfade,
        output_format=req.output_format,
        normalize=req.normalize,
        temperature=req.temperature,
        top_k=req.top_k,
        speed=req.speed,
        target_duration_s=req.target_duration_s,
    )

    try:
        output_path = await producer.produce(job_id, produce_req)
        _output_files[job_id] = output_path
    except Exception as e:
        logger.exception("Pipeline: production failed")
        raise HTTPException(500, f"Audio production failed: {str(e)[:200]}")

    # Step 4: Return audio file
    if not Path(output_path).exists():
        raise HTTPException(500, "Output file not found")

    media_type = "audio/mpeg" if output_path.endswith(".mp3") else "audio/wav"
    filename = f"vietvoice_{job_id}.{req.output_format}"
    return FileResponse(output_path, media_type=media_type, filename=filename)


@studio_app.post("/pipeline/json")
async def pipeline_json(req: PipelineRequest):
    """Same as /pipeline but returns JSON with script + job info instead of audio file.
    Use GET /download/{job_id} to fetch the audio separately.
    """
    if not tts_manager.is_loaded:
        raise HTTPException(503, "TTS engine not loaded")
    if llm_generator is None or producer is None:
        raise HTTPException(500, "Studio not initialized")

    # Step 1: Generate script
    try:
        script_data = await llm_generator.generate(req.text, req.max_characters, req.mode, req.target_duration_s)
        script = Script(**script_data)
    except Exception as e:
        logger.exception("Pipeline: script generation failed")
        raise HTTPException(422, f"Script generation failed: {str(e)[:200]}")

    # Step 2: Auto-assign voices
    available_voices = list(tts_manager.voice_cache.keys())
    if not available_voices:
        raise HTTPException(503, "No voices cached")

    char_dicts = [{"name": c.name, "gender": c.gender} for c in script.characters]
    voice_map = _auto_assign_voices(char_dicts, available_voices, req.voice_overrides)

    for c in script.characters:
        if c.name not in voice_map or voice_map[c.name] not in available_voices:
            voice_map[c.name] = available_voices[0]

    # Step 3: Produce
    job_id = await job_manager.create_job()
    produce_req = ProduceRequest(
        script=script,
        voice_map=voice_map,
        silence_gap=req.silence_gap,
        crossfade=req.crossfade,
        output_format=req.output_format,
        normalize=req.normalize,
        temperature=req.temperature,
        top_k=req.top_k,
        speed=req.speed,
        target_duration_s=req.target_duration_s,
    )

    try:
        output_path = await producer.produce(job_id, produce_req)
        _output_files[job_id] = output_path
    except Exception as e:
        logger.exception("Pipeline: production failed")
        raise HTTPException(500, f"Audio production failed: {str(e)[:200]}")

    return {
        "status": "ok",
        "job_id": job_id,
        "script": script_data,
        "voice_map": voice_map,
        "download_url": f"/studio/download/{job_id}",
        "output_format": req.output_format,
    }


# ---------------------------------------------------------------------------
# Voice Cloning
# ---------------------------------------------------------------------------

CUSTOM_VOICES_DIR = Path.home() / ".vietvoice" / "custom_voices"


def _load_custom_voices():
    """Load persisted custom voice presets from disk into tts_manager."""
    if not CUSTOM_VOICES_DIR.exists():
        return
    for f in CUSTOM_VOICES_DIR.glob("*.json"):
        try:
            data = json.loads(f.read_text())
            name = f.stem
            # Convert codes list back to tensor-like dict format
            import torch
            codes = torch.tensor(data["codes"])
            tts_manager.voice_cache[name] = {"codes": codes, "text": data["text"]}
            logger.info("Loaded custom voice: %s", name)
        except Exception as e:
            logger.warning("Failed to load custom voice %s: %s", f.name, e)


def _save_custom_voice(name: str, codes, text: str):
    """Persist a cloned voice to disk."""
    CUSTOM_VOICES_DIR.mkdir(parents=True, exist_ok=True)
    # Convert tensor to list for JSON serialization
    if hasattr(codes, "tolist"):
        codes_list = codes.tolist()
    else:
        codes_list = list(codes)
    data = {"text": text, "codes": codes_list}
    (CUSTOM_VOICES_DIR / f"{name}.json").write_text(
        json.dumps(data, ensure_ascii=False)
    )


from fastapi import UploadFile, File, Form


@studio_app.post("/clone-voice")
async def clone_voice_endpoint(
    file: UploadFile = File(...),
    name: str = Form("custom_voice"),
    text: str = Form(""),
):
    """Clone a voice from reference audio (3-5s WAV) + transcript text."""
    if not tts_manager.is_loaded:
        raise HTTPException(503, "TTS engine not loaded")

    # Validate file
    if not file.filename.lower().endswith((".wav", ".mp3", ".flac", ".ogg")):
        raise HTTPException(422, "Audio file must be WAV, MP3, FLAC, or OGG")

    # Sanitize name
    import re as _re
    safe_name = _re.sub(r"[^a-zA-Z0-9_-]", "_", name.strip())[:50]
    if not safe_name:
        raise HTTPException(422, "Invalid voice name")

    # Check name not taken by preset
    if safe_name in tts_manager.voice_cache:
        # Allow overwrite of custom voices, not presets
        preset_ids = set()
        if tts_manager.engine:
            for item in tts_manager.engine.list_preset_voices():
                preset_ids.add(item[1] if isinstance(item, tuple) else item)
        if safe_name in preset_ids:
            raise HTTPException(409, f"Cannot overwrite preset voice '{safe_name}'")

    # Save uploaded file to temp
    tmp_path = Path(tempfile.gettempdir()) / f"clone_{safe_name}_{uuid.uuid4().hex[:6]}.wav"
    try:
        content = await file.read()
        if len(content) > 10 * 1024 * 1024:  # 10MB limit
            raise HTTPException(413, "File too large (max 10MB)")
        tmp_path.write_bytes(content)

        # Encode reference audio
        async with tts_manager._lock:
            loop = asyncio.get_running_loop()
            codes = await loop.run_in_executor(
                None, lambda: tts_manager.engine.encode_reference(str(tmp_path))
            )

        # Store in cache
        tts_manager.voice_cache[safe_name] = {"codes": codes, "text": text}

        # Persist to disk
        _save_custom_voice(safe_name, codes, text)

        return {
            "status": "ok",
            "voice_id": safe_name,
            "message": f"Voice '{safe_name}' cloned successfully",
        }
    finally:
        tmp_path.unlink(missing_ok=True)


@studio_app.delete("/clone-voice/{voice_name}")
async def delete_cloned_voice(voice_name: str):
    """Delete a custom cloned voice."""
    # Don't allow deleting preset voices
    preset_ids = set()
    if tts_manager.engine:
        for item in tts_manager.engine.list_preset_voices():
            preset_ids.add(item[1] if isinstance(item, tuple) else item)
    if voice_name in preset_ids:
        raise HTTPException(409, "Cannot delete preset voice")

    # Remove from cache
    tts_manager.voice_cache.pop(voice_name, None)

    # Remove from disk
    voice_file = CUSTOM_VOICES_DIR / f"{voice_name}.json"
    voice_file.unlink(missing_ok=True)

    return {"status": "ok", "message": f"Voice '{voice_name}' deleted"}


@studio_app.get("/clone-voice")
async def list_cloned_voices():
    """List custom cloned voices."""
    preset_ids = set()
    if tts_manager.engine:
        for item in tts_manager.engine.list_preset_voices():
            preset_ids.add(item[1] if isinstance(item, tuple) else item)

    custom = []
    for vid in tts_manager.voice_cache:
        if vid not in preset_ids:
            custom.append({"id": vid, "has_text": bool(tts_manager.voice_cache[vid].get("text"))})
    return {"custom_voices": custom}


# ---------------------------------------------------------------------------
# Workflows & Webhooks — save/trigger automated pipelines
# ---------------------------------------------------------------------------

class WorkflowConfig(BaseModel):
    """Saved workflow configuration."""
    name: str = Field(min_length=1, max_length=100)
    description: str = ""
    mode: Literal["dialogue", "story"] = "dialogue"
    max_characters: int = Field(default=4, le=10, ge=1)
    output_format: Literal["wav", "mp3"] = "wav"
    normalize: bool = True
    silence_gap: float = 0.3
    crossfade: float = 0.0
    temperature: float = Field(default=0.8, ge=0.1, le=1.5)
    top_k: int = Field(default=50, ge=10, le=100)
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    target_duration_s: Optional[float] = Field(default=None, ge=0.5, le=600)
    voice_overrides: dict[str, str] = Field(default_factory=dict)
    # Drawflow editor state (nodes + connections JSON)
    editor_data: dict = Field(default_factory=dict)


class WorkflowRecord(BaseModel):
    id: str
    config: WorkflowConfig
    webhook_url: str
    created_at: float
    run_count: int = 0
    last_run: float | None = None


class WorkflowRunRecord(BaseModel):
    run_id: str
    workflow_id: str
    status: Literal["success", "error"]
    input_text: str
    output_url: str | None = None
    error: str | None = None
    started_at: float
    finished_at: float


class WebhookTriggerRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    voice_overrides: dict[str, str] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Series / Audiobook Models
# ---------------------------------------------------------------------------

class Episode(BaseModel):
    episode_num: int
    title: str = ""
    script_data: dict = Field(default_factory=dict)
    voice_map: dict[str, str] = Field(default_factory=dict)
    job_id: str = ""
    audio_path: str = ""
    summary: str = ""
    duration_s: float = 0.0
    created_at: float = Field(default_factory=time.time)


class Series(BaseModel):
    id: str
    title: str
    mode: Literal["dialogue", "story"] = "story"
    voice_map: dict[str, str] = Field(default_factory=dict)
    characters: list[dict] = Field(default_factory=list)
    episodes: list[Episode] = Field(default_factory=list)
    temperature: float = Field(default=0.8, ge=0.1, le=1.5)
    top_k: int = Field(default=50, ge=10, le=100)
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    target_duration_s: Optional[float] = Field(default=None, ge=0.5, le=600)
    created_at: float = Field(default_factory=time.time)

    MAX_EPISODES: ClassVar[int] = 50


class CreateSeriesRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    mode: Literal["dialogue", "story"] = "story"
    script_data: dict | None = None
    voice_map: dict[str, str] = Field(default_factory=dict)
    characters: list[dict] = Field(default_factory=list)
    temperature: float = Field(default=0.8, ge=0.1, le=1.5)
    top_k: int = Field(default=50, ge=10, le=100)
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    target_duration_s: Optional[float] = None


class UpdateSeriesRequest(BaseModel):
    title: str | None = None
    voice_map: dict[str, str] | None = None
    characters: list[dict] | None = None
    temperature: float | None = Field(default=None, ge=0.1, le=1.5)
    top_k: int | None = Field(default=None, ge=10, le=100)
    speed: float | None = Field(default=None, ge=0.5, le=2.0)
    target_duration_s: Optional[float] = Field(default=None, ge=0.5, le=600)


class ContinueSeriesRequest(BaseModel):
    prompt: str = Field(default="", max_length=500)
    max_characters: int = Field(default=4, le=10, ge=1)


class BatchGenerateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    prompt: str = Field(min_length=1, max_length=2000)
    num_episodes: int = Field(default=3, ge=2, le=20)
    mode: Literal["dialogue", "story"] = "story"
    genre: str = ""
    max_characters: int = Field(default=4, le=10, ge=1)
    target_duration_s: Optional[float] = Field(default=None, ge=0.5, le=600)
    characters: Optional[list[CharacterPreset]] = Field(default=None, description="Pre-configured characters for all episodes.")


class SeriesManager:
    def __init__(self):
        self._series: dict[str, Series] = {}
        self._dir = Path.home() / ".vietvoice"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._file = self._dir / "series.json"
        self._lock = asyncio.Lock()
        self._load()

    def _load(self):
        if self._file.exists():
            try:
                data = json.loads(self._file.read_text())
                self._series = {sid: Series(**s) for sid, s in data.items()}
            except Exception:
                self._series = {}

    def _save(self):
        data = {sid: s.model_dump() for sid, s in self._series.items()}
        self._file.write_text(json.dumps(data, ensure_ascii=False, indent=2))

    def update(self, sid: str, req: UpdateSeriesRequest) -> Series | None:
        series = self._series.get(sid)
        if not series:
            return None
        for field in ["title", "voice_map", "characters", "temperature", "top_k", "speed", "target_duration_s"]:
            val = getattr(req, field, None)
            if val is not None:
                setattr(series, field, val)
        self._save()
        return series

    def create(self, req: CreateSeriesRequest) -> Series:
        sid = uuid.uuid4().hex[:10]
        series = Series(
            id=sid, title=req.title, mode=req.mode,
            voice_map=req.voice_map, characters=req.characters,
            temperature=req.temperature, top_k=req.top_k,
            speed=req.speed, target_duration_s=req.target_duration_s,
        )
        if req.script_data:
            ep = Episode(episode_num=1, script_data=req.script_data, voice_map=req.voice_map)
            series.episodes.append(ep)
        self._series[sid] = series
        self._save()
        return series

    def get(self, sid: str) -> Series | None:
        return self._series.get(sid)

    def list_all(self) -> list[Series]:
        return list(self._series.values())

    def add_episode(self, sid: str, episode: Episode):
        series = self._series.get(sid)
        if not series:
            raise ValueError("Series not found")
        if len(series.episodes) >= Series.MAX_EPISODES:
            raise ValueError(f"Max {Series.MAX_EPISODES} episodes reached")
        series.episodes.append(episode)
        self._save()

    def update_episode(self, sid: str, ep_num: int, **kwargs):
        series = self._series.get(sid)
        if series:
            for ep in series.episodes:
                if ep.episode_num == ep_num:
                    for k, v in kwargs.items():
                        setattr(ep, k, v)
                    break
            self._save()

    def delete(self, sid: str):
        self._series.pop(sid, None)
        self._save()


series_manager = SeriesManager()


# ---------------------------------------------------------------------------
# Series Helpers — LLM context, summarization, audio duration
# ---------------------------------------------------------------------------

def _get_audio_duration(path: str) -> float:
    try:
        import soundfile as sf
        data, sr = sf.read(path)
        return round(len(data) / sr, 2)
    except Exception:
        return 0.0


def _extract_dialogue_summary(script_data: dict, max_chars: int = 1500) -> str:
    """Extract key dialogue lines from script_data as fallback summary."""
    lines = []
    title = script_data.get("title", "")
    if title:
        lines.append(f"Title: {title}")
    for scene in script_data.get("scenes", []):
        setting = scene.get("setting", "")
        if setting:
            lines.append(f"[{setting}]")
        for d in scene.get("dialogue", []):
            char = d.get("character", "")
            text = d.get("text", "")
            if char and text and d.get("line_type") != "narration":
                lines.append(f"{char}: {text}")
            elif char == "Narrator" and text and len(text) > 50:
                lines.append(text[:100])
    combined = " ".join(lines)
    return combined[:max_chars]


def _build_series_context(series: Series) -> str:
    """Build context string from episode summaries. Cap ~2000 chars."""
    summaries = []
    for ep in reversed(series.episodes):
        if ep.summary:
            summaries.append(f"Ep {ep.episode_num}: {ep.summary}")
        elif ep.script_data:
            # Fallback: extract dialogue from script_data
            fallback = _extract_dialogue_summary(ep.script_data)
            if fallback:
                summaries.append(f"Ep {ep.episode_num}: {fallback}")

    context_parts = []
    total = 0
    for s in summaries:
        if total + len(s) > 2000:
            break
        context_parts.append(s)
        total += len(s)

    context_parts.reverse()
    return "\n".join(context_parts)


def _build_continuation_prompt(series: Series, context: str, user_hint: str = "") -> str:
    char_desc = ", ".join(
        f"{c.get('name', '?')} ({c.get('gender', '?')})"
        for c in series.characters
    )

    parts = [
        f"Continue the {series.mode} series '{series.title}'.",
        f"Characters: {char_desc}" if char_desc else "",
        f"Previous episodes:\n{context}" if context else "This is the first episode.",
        f"User direction: {user_hint}" if user_hint else "",
        "IMPORTANT: Generate the NEXT episode that CONTINUES the story from where the previous episode ended.",
        "Do NOT retell or repeat the previous episodes. Move the plot FORWARD with new events.",
        "Keep same characters. Vietnamese language.",
    ]
    return "\n".join(p for p in parts if p)


_SUMMARIZE_HEADER = """Summarize this Vietnamese script episode in ~300 characters Vietnamese.
Focus on: key plot points, character actions, emotional beats.
Return ONLY the summary text, no JSON, no markdown.

Script content:
"""


async def _call_llm_raw(prompt: str) -> str:
    """Call LLM and return raw text (not parsed as JSON)."""
    if llm_generator is None:
        return ""

    if llm_generator.provider == "claude_cli":
        import shutil as _sh
        claude_bin = _sh.which("claude")
        if not claude_bin:
            return ""
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, lambda: subprocess.run(
            [claude_bin, "-p", prompt, "--output-format", "json"],
            capture_output=True, text=True, timeout=120
        ))
        if result.returncode == 0:
            try:
                cli_out = json.loads(result.stdout)
                return cli_out.get("result", result.stdout)
            except json.JSONDecodeError:
                return result.stdout
        return ""

    elif llm_generator.provider == "claude":
        import anthropic
        client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
        loop = asyncio.get_running_loop()
        resp = await loop.run_in_executor(None, lambda: client.messages.create(
            model=llm_generator.model, max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        ))
        return resp.content[0].text

    elif llm_generator.provider == "openai":
        import openai
        client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        loop = asyncio.get_running_loop()
        resp = await loop.run_in_executor(None, lambda: client.chat.completions.create(
            model=llm_generator.model, max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        ))
        return resp.choices[0].message.content

    return ""


async def _summarize_episode(script_data: dict) -> str:
    """Auto-summarize episode via LLM. Returns ~300 char Vietnamese summary."""
    if llm_generator is None:
        return ""
    try:
        prompt = _SUMMARIZE_HEADER + json.dumps(script_data, ensure_ascii=False)[:3000]
        raw = await _call_llm_raw(prompt)
        return raw.strip()[:400]
    except Exception as e:
        logger.warning("Episode summarization failed: %s", e)
        return ""


# In-memory storage (persisted to JSON file)
_workflows: dict[str, WorkflowRecord] = {}
_workflow_runs: list[WorkflowRunRecord] = []
_VIETVOICE_DIR = Path.home() / ".vietvoice"
_VIETVOICE_DIR.mkdir(parents=True, exist_ok=True)
_WORKFLOWS_FILE = _VIETVOICE_DIR / "workflows.json"


def _save_workflows():
    """Persist workflows to disk."""
    data = {wid: w.model_dump() for wid, w in _workflows.items()}
    _WORKFLOWS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2))


def _load_workflows():
    """Load workflows from disk."""
    global _workflows
    if _WORKFLOWS_FILE.exists():
        try:
            data = json.loads(_WORKFLOWS_FILE.read_text())
            _workflows = {wid: WorkflowRecord(**w) for wid, w in data.items()}
        except Exception:
            _workflows = {}


# Load on import
_load_workflows()


@studio_app.post("/workflows")
async def create_workflow(config: WorkflowConfig):
    """Create a new workflow with webhook URL."""
    wf_id = uuid.uuid4().hex[:10]
    webhook_url = f"/studio/workflows/{wf_id}/trigger"
    record = WorkflowRecord(
        id=wf_id,
        config=config,
        webhook_url=webhook_url,
        created_at=time.time(),
    )
    _workflows[wf_id] = record
    _save_workflows()
    return {
        "status": "ok",
        "workflow": record.model_dump(),
        "webhook_url": webhook_url,
        "webhook_curl": f'curl -X POST http://localhost:8001{webhook_url} -H "Content-Type: application/json" -d \'{{"text": "your text here"}}\' --output output.wav',
    }


@studio_app.get("/workflows")
async def list_workflows():
    """List all saved workflows."""
    return {"workflows": [w.model_dump() for w in _workflows.values()]}


@studio_app.get("/workflows/{wf_id}")
async def get_workflow(wf_id: str):
    """Get a specific workflow."""
    wf = _workflows.get(wf_id)
    if not wf:
        raise HTTPException(404, "Workflow not found")
    return wf.model_dump()


@studio_app.put("/workflows/{wf_id}")
async def update_workflow(wf_id: str, config: WorkflowConfig):
    """Update workflow configuration."""
    wf = _workflows.get(wf_id)
    if not wf:
        raise HTTPException(404, "Workflow not found")
    wf.config = config
    _save_workflows()
    return {"status": "ok", "workflow": wf.model_dump()}


@studio_app.delete("/workflows/{wf_id}")
async def delete_workflow(wf_id: str):
    """Delete a workflow."""
    if wf_id not in _workflows:
        raise HTTPException(404, "Workflow not found")
    del _workflows[wf_id]
    _save_workflows()
    return {"status": "ok"}


@studio_app.post("/workflows/{wf_id}/trigger")
async def trigger_workflow(wf_id: str, req: WebhookTriggerRequest):
    """Webhook trigger — send text, get audio back. Uses saved workflow config."""
    wf = _workflows.get(wf_id)
    if not wf:
        raise HTTPException(404, "Workflow not found")
    if not tts_manager.is_loaded:
        raise HTTPException(503, "TTS engine not loaded")
    if llm_generator is None or producer is None:
        raise HTTPException(500, "Studio not initialized")

    cfg = wf.config
    started = time.time()
    run_id = uuid.uuid4().hex[:10]

    # Merge voice overrides (workflow defaults + request overrides)
    overrides = {**cfg.voice_overrides, **req.voice_overrides}

    try:
        # Step 1: Generate script
        script_data = await llm_generator.generate(req.text, cfg.max_characters, cfg.mode, cfg.target_duration_s)
        script = Script(**script_data)

        # Step 2: Auto-assign voices
        available_voices = list(tts_manager.voice_cache.keys())
        if not available_voices:
            raise RuntimeError("No voices cached")

        char_dicts = [{"name": c.name, "gender": c.gender} for c in script.characters]
        voice_map = _auto_assign_voices(char_dicts, available_voices, overrides)
        for c in script.characters:
            if c.name not in voice_map or voice_map[c.name] not in available_voices:
                voice_map[c.name] = available_voices[0]

        # Step 3: Produce
        job_id = await job_manager.create_job()
        produce_req = ProduceRequest(
            script=script, voice_map=voice_map,
            silence_gap=cfg.silence_gap, crossfade=cfg.crossfade,
            output_format=cfg.output_format, normalize=cfg.normalize,
            temperature=cfg.temperature, top_k=cfg.top_k,
            speed=cfg.speed, target_duration_s=cfg.target_duration_s,
        )
        output_path = await producer.produce(job_id, produce_req)
        _output_files[job_id] = output_path

        # Record run
        run = WorkflowRunRecord(
            run_id=run_id, workflow_id=wf_id, status="success",
            input_text=req.text[:100], output_url=f"/studio/download/{job_id}",
            started_at=started, finished_at=time.time(),
        )
        _workflow_runs.append(run)
        wf.run_count += 1
        wf.last_run = time.time()
        _save_workflows()

        # Return audio
        media_type = "audio/mpeg" if output_path.endswith(".mp3") else "audio/wav"
        return FileResponse(output_path, media_type=media_type,
                            filename=f"vietvoice_{wf_id}_{run_id}.{cfg.output_format}")

    except Exception as e:
        run = WorkflowRunRecord(
            run_id=run_id, workflow_id=wf_id, status="error",
            input_text=req.text[:100], error=str(e)[:200],
            started_at=started, finished_at=time.time(),
        )
        _workflow_runs.append(run)
        logger.exception("Workflow trigger failed: %s", wf_id)
        raise HTTPException(500, f"Workflow failed: {str(e)[:200]}")


@studio_app.get("/workflows/{wf_id}/runs")
async def get_workflow_runs(wf_id: str):
    """Get run history for a workflow."""
    if wf_id not in _workflows:
        raise HTTPException(404, "Workflow not found")
    runs = [r.model_dump() for r in _workflow_runs if r.workflow_id == wf_id]
    return {"runs": runs[-20:]}  # last 20 runs


# ---------------------------------------------------------------------------
# Series / Audiobook Endpoints
# ---------------------------------------------------------------------------

@studio_app.post("/series")
async def create_series(req: CreateSeriesRequest):
    series = series_manager.create(req)
    return {"status": "ok", "series": series.model_dump()}


@studio_app.post("/series/batch-generate")
async def batch_generate_series(req: BatchGenerateRequest):
    """Generate N episode scripts for a new series (no audio production)."""
    if llm_generator is None:
        raise HTTPException(500, "LLM generator not initialized")

    # Create empty series
    create_req = CreateSeriesRequest(title=req.title, mode=req.mode)
    series = series_manager.create(create_req)
    available_voices = list(tts_manager.voice_cache.keys()) if tts_manager.is_loaded else []

    chars_dicts = [c.model_dump() for c in req.characters] if req.characters else None

    try:
        for ep_num in range(1, req.num_episodes + 1):
            # Build prompt: ep 1 uses user prompt, ep 2+ uses continuation
            if ep_num == 1:
                script_data = await llm_generator.generate(
                    req.prompt, req.max_characters, req.mode,
                    req.target_duration_s, req.genre, chars_dicts,
                )
            else:
                context = _build_series_context(series)
                continuation = _build_continuation_prompt(series, context)
                script_data = await llm_generator.generate(
                    continuation, req.max_characters, req.mode,
                    req.target_duration_s, req.genre, chars_dicts,
                )

            # Auto-assign voices
            chars = script_data.get("characters", [])
            voice_map = _auto_assign_voices(chars, available_voices, series.voice_map)

            # Update series characters & voice_map
            existing_names = {c.get("name") for c in series.characters}
            for c in chars:
                if c.get("name") not in existing_names:
                    series.characters.append(c)
                    existing_names.add(c.get("name"))
            series.voice_map.update(voice_map)

            # Summarize for next episode context
            summary = await _summarize_episode(script_data)

            # Save episode (script only, no audio)
            ep = Episode(
                episode_num=ep_num,
                title=script_data.get("title", f"Tập {ep_num}"),
                script_data=script_data,
                voice_map=voice_map,
                summary=summary,
            )
            series_manager.add_episode(series.id, ep)

            logger.info(
                "batch_generate ep=%d/%d series=%s",
                ep_num, req.num_episodes, series.id,
            )

    except Exception as e:
        logger.exception("Batch generate failed at ep %d series=%s", ep_num, series.id)
        # Return partial results
        series = series_manager.get(series.id)
        return {
            "status": "partial",
            "error": str(e),
            "series": series.model_dump() if series else None,
        }

    series = series_manager.get(series.id)
    return {"status": "ok", "series": series.model_dump() if series else None}


@studio_app.get("/series")
async def list_series():
    all_series = series_manager.list_all()
    return {"series": [s.model_dump() for s in all_series]}


@studio_app.get("/series/{sid}")
async def get_series(sid: str):
    series = series_manager.get(sid)
    if not series:
        raise HTTPException(404, "Series not found")
    return series.model_dump()


@studio_app.put("/series/{sid}")
async def update_series(sid: str, req: UpdateSeriesRequest):
    series = series_manager.update(sid, req)
    if not series:
        raise HTTPException(404, "Series not found")
    return {"status": "ok", "series": series.model_dump()}


@studio_app.get("/series/{sid}/export")
async def export_series(sid: str):
    """Export series metadata + episode scripts as JSON (no audio binaries)."""
    series = series_manager.get(sid)
    if not series:
        raise HTTPException(404, "Series not found")
    export_data = series.model_dump()
    # Strip audio_path from episodes (not portable)
    for ep in export_data.get("episodes", []):
        ep.pop("audio_path", None)
        ep.pop("job_id", None)
    export_data["_export_version"] = 1
    # Return as downloadable JSON
    content = json.dumps(export_data, ensure_ascii=False, indent=2)
    safe_title = re.sub(r"[^a-zA-Z0-9_-]", "_", series.title)[:50]
    return JSONResponse(
        content=json.loads(content),
        headers={"Content-Disposition": f'attachment; filename="series_{safe_title}.json"'},
    )


@studio_app.post("/series/import")
async def import_series(file: UploadFile = File(...)):
    """Import a previously exported series JSON. Audio must be re-produced."""
    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(413, "File too large (max 5MB)")
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        raise HTTPException(422, "Invalid JSON")

    # Support both formats:
    # 1. Series export: {"title": "...", "mode": "...", "episodes": [...]}
    # 2. Script export: {"script": {...}, "voice_map": {...}}
    if "script" in data and "title" not in data:
        # Script export format — convert to series
        script_data = data["script"]
        voice_map = data.get("voice_map", {})
        characters = [
            {"name": c["name"], "gender": c.get("gender", "M")}
            for c in script_data.get("characters", [])
        ]
        data = {
            "title": script_data.get("title", "Imported Script"),
            "mode": "story" if any(
                l.get("line_type") == "narration"
                for s in script_data.get("scenes", [])
                for l in s.get("dialogue", [])
            ) else "dialogue",
            "voice_map": voice_map,
            "characters": characters,
            "episodes": [{
                "episode_num": 1,
                "title": script_data.get("title", "Episode 1"),
                "script_data": script_data,
                "voice_map": voice_map,
            }],
        }

    if "title" not in data:
        raise HTTPException(422, "Missing required field: title")

    # Create new series with new ID
    sid = uuid.uuid4().hex[:10]
    episodes = []
    for ep_data in data.get("episodes", []):
        ep_data.pop("audio_path", None)
        ep_data.pop("job_id", None)
        episodes.append(Episode(**ep_data))

    series = Series(
        id=sid,
        title=data["title"],
        mode=data.get("mode", "story"),
        voice_map=data.get("voice_map", {}),
        characters=data.get("characters", []),
        episodes=episodes,
        temperature=data.get("temperature", 0.8),
        top_k=data.get("top_k", 50),
        speed=data.get("speed", 1.0),
        target_duration_s=data.get("target_duration_s"),
    )
    series_manager._series[sid] = series
    series_manager._save()

    return {
        "status": "ok",
        "series": series.model_dump(),
        "note": "Audio files not included in export. Use 'Continue Story' to re-produce episodes.",
    }


@studio_app.post("/series/{sid}/continue")
async def continue_series(sid: str, req: ContinueSeriesRequest):
    series = series_manager.get(sid)
    if not series:
        raise HTTPException(404, "Series not found")
    if len(series.episodes) >= Series.MAX_EPISODES:
        raise HTTPException(422, "Max episodes reached")
    if not tts_manager.is_loaded:
        raise HTTPException(503, "TTS not loaded")
    if llm_generator is None or producer is None:
        raise HTTPException(500, "Studio not initialized")

    # Backfill missing summaries before continuing
    for ep in series.episodes:
        if not ep.summary and ep.script_data:
            try:
                ep.summary = await _summarize_episode(ep.script_data)
                if ep.summary:
                    series_manager._save()
            except Exception:
                pass

    async with series_manager._lock:
        return await _continue_series_inner(sid, series, req)


async def _continue_series_inner(sid: str, series: Series, req: ContinueSeriesRequest):
    ep_num = len(series.episodes) + 1
    logger.info(
        "series_continue_started series_id=%s episode=%d existing_episodes=%d request_id=%s",
        sid, ep_num, len(series.episodes), get_request_id(),
    )
    t0 = time.monotonic()

    # 1. Build context from previous summaries
    context = _build_series_context(series)

    # 2. Build continuation prompt
    continuation_prompt = _build_continuation_prompt(series, context, req.prompt)

    # 3. Generate script via LLM
    script_data = await llm_generator.generate(
        continuation_prompt, req.max_characters, series.mode, series.target_duration_s
    )
    script = Script(**script_data)

    # 4. Resolve voice_map (reuse series voice_map, auto-assign new chars)
    available = list(tts_manager.voice_cache.keys())
    char_dicts = [{"name": c.name, "gender": c.gender} for c in script.characters]
    voice_map = _auto_assign_voices(char_dicts, available, series.voice_map)

    # Update series voice_map with any new assignments
    series.voice_map.update(voice_map)

    # Update series characters if new ones appeared
    existing_names = {c.get("name") for c in series.characters}
    for c in script.characters:
        if c.name not in existing_names:
            series.characters.append({"name": c.name, "gender": c.gender})

    # 5. Produce audio
    job_id = await job_manager.create_job()
    produce_req = ProduceRequest(
        script=script, voice_map=voice_map,
        temperature=series.temperature, top_k=series.top_k,
        speed=series.speed,
        target_duration_s=series.target_duration_s,
    )

    try:
        output_path = await producer.produce(job_id, produce_req)
        _output_files[job_id] = output_path
    except Exception as e:
        logger.exception(
            "series_production_failed series_id=%s episode=%d job_id=%s request_id=%s",
            sid, ep_num, job_id, get_request_id(),
        )
        raise HTTPException(500, f"Production failed: {str(e)[:200]}")

    # 6. Get audio duration
    duration_s = _get_audio_duration(output_path)

    # 7. Auto-summarize via LLM
    summary = await _summarize_episode(script_data)

    # 8. Create episode record
    episode = Episode(
        episode_num=ep_num,
        title=script_data.get("title", f"Episode {ep_num}"),
        script_data=script_data,
        voice_map=voice_map,
        job_id=job_id,
        audio_path=output_path,
        summary=summary,
        duration_s=duration_s,
    )
    series_manager.add_episode(sid, episode)

    total_ms = round((time.monotonic() - t0) * 1000)
    logger.info(
        "series_continue_completed series_id=%s episode=%d job_id=%s duration_s=%.1f total_ms=%d request_id=%s",
        sid, ep_num, job_id, duration_s, total_ms, get_request_id(),
    )

    return {
        "status": "ok",
        "episode": episode.model_dump(),
        "download_url": f"/studio/download/{job_id}",
    }


@studio_app.post("/series/{sid}/merge")
async def merge_series(sid: str):
    series = series_manager.get(sid)
    if not series:
        raise HTTPException(404, "Series not found")
    if len(series.episodes) < 2:
        raise HTTPException(422, "Need at least 2 episodes to merge")
    if not has_ffmpeg():
        raise HTTPException(503, "FFmpeg not available")

    # Collect valid audio paths (with path traversal guard)
    safe_dir = (Path(tempfile.gettempdir()) / "studio_voice_output").resolve()
    audio_paths = []
    for ep in sorted(series.episodes, key=lambda e: e.episode_num):
        if ep.audio_path and Path(ep.audio_path).exists():
            if Path(ep.audio_path).resolve().is_relative_to(safe_dir):
                audio_paths.append(ep.audio_path)

    if len(audio_paths) < 2:
        raise HTTPException(422, "Not enough audio files found")

    output_dir = Path(tempfile.gettempdir()) / "studio_voice_output"
    output_dir.mkdir(exist_ok=True)

    concat_file = output_dir / f"concat_{sid}.txt"
    merge_path = str(output_dir / f"series_{sid}_merged.wav")

    with open(concat_file, "w") as f:
        for path in audio_paths:
            safe = path.replace("'", "'\\''")
            f.write(f"file '{safe}'\n")

    try:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, lambda: _run_ffmpeg([
            "-f", "concat", "-safe", "0",
            "-i", str(concat_file),
            "-c", "copy",
            merge_path,
        ]))
    except subprocess.CalledProcessError as e:
        raise HTTPException(500, f"Merge failed: {e.stderr[:200]}")
    finally:
        concat_file.unlink(missing_ok=True)

    merge_job_id = f"merge_{sid}"
    _output_files[merge_job_id] = merge_path

    duration = _get_audio_duration(merge_path)

    return {
        "status": "ok",
        "download_url": f"/studio/download/{merge_job_id}",
        "total_episodes": len(audio_paths),
        "total_duration_s": duration,
    }


@studio_app.delete("/series/{sid}")
async def delete_series(sid: str):
    series = series_manager.get(sid)
    if not series:
        raise HTTPException(404, "Series not found")
    for ep in series.episodes:
        if ep.audio_path:
            Path(ep.audio_path).unlink(missing_ok=True)
    series_manager.delete(sid)
    return {"status": "ok"}


@studio_app.get("/series/{sid}/episodes/{ep_num}/download")
async def download_episode(sid: str, ep_num: int):
    series = series_manager.get(sid)
    if not series:
        raise HTTPException(404, "Series not found")
    episode = next((e for e in series.episodes if e.episode_num == ep_num), None)
    if not episode:
        raise HTTPException(404, "Episode not found")
    if not episode.audio_path or not Path(episode.audio_path).exists():
        raise HTTPException(404, "Audio file not found")
    # Path traversal guard
    safe_dir = Path(tempfile.gettempdir()) / "studio_voice_output"
    if not Path(episode.audio_path).resolve().is_relative_to(safe_dir.resolve()):
        raise HTTPException(403, "Forbidden")
    return FileResponse(episode.audio_path, media_type="audio/wav",
                        filename=f"{series.title}_ep{ep_num}.wav")


class ReproduceEpisodeRequest(BaseModel):
    script_data: dict


@studio_app.post("/series/{sid}/episodes/{ep_num}/reproduce")
async def reproduce_episode(sid: str, ep_num: int, req: ReproduceEpisodeRequest):
    """Re-produce an episode with edited script. Replaces audio only."""
    series = series_manager.get(sid)
    if not series:
        raise HTTPException(404, "Series not found")
    episode = next((e for e in series.episodes if e.episode_num == ep_num), None)
    if not episode:
        raise HTTPException(404, "Episode not found")
    if not tts_manager.is_loaded:
        raise HTTPException(503, "TTS not loaded")
    if producer is None:
        raise HTTPException(500, "Studio not initialized")

    # Validate script
    try:
        script = Script(**req.script_data)
    except Exception as e:
        raise HTTPException(422, f"Invalid script: {str(e)[:200]}")

    # Resolve voice map
    available = list(tts_manager.voice_cache.keys())
    char_dicts = [{"name": c.name, "gender": c.gender} for c in script.characters]
    voice_map = _auto_assign_voices(char_dicts, available, series.voice_map)

    # Produce audio
    job_id = await job_manager.create_job()
    produce_req = ProduceRequest(
        script=script, voice_map=voice_map,
        temperature=series.temperature, top_k=series.top_k,
        speed=series.speed, target_duration_s=series.target_duration_s,
    )

    try:
        output_path = await producer.produce(job_id, produce_req)
        _output_files[job_id] = output_path
    except Exception as e:
        raise HTTPException(500, f"Production failed: {str(e)[:200]}")

    # Delete old audio
    if episode.audio_path and Path(episode.audio_path).exists():
        Path(episode.audio_path).unlink(missing_ok=True)

    # Update episode
    duration_s = _get_audio_duration(output_path)
    series_manager.update_episode(sid, ep_num,
        script_data=req.script_data,
        title=req.script_data.get("title", episode.title),
        audio_path=output_path,
        job_id=job_id,
        duration_s=duration_s,
    )

    return {
        "status": "ok",
        "episode_num": ep_num,
        "duration_s": duration_s,
        "download_url": f"/studio/download/{job_id}",
    }


# ---------------------------------------------------------------------------
# Standalone entrypoint (for testing without web_stream.py)
# ---------------------------------------------------------------------------

def _load_dotenv():
    """Load .env from project root."""
    env_path = Path(__file__).parent.parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip().strip('"').strip("'")
            if key and value and key not in os.environ:
                os.environ[key] = value


def main():
    """Run studio API standalone for development."""
    import yaml

    _load_dotenv()

    config_path = Path(__file__).parent.parent / "config.yaml"
    config = {}
    if config_path.exists():
        with open(config_path, "r") as f:
            config = yaml.safe_load(f) or {}

    studio_config = config.get("studio", {})

    # Default model config
    backbone = studio_config.get("backbone_repo", "pnnbao-ump/VieNeu-TTS-0.3B-q4-gguf")
    codec = studio_config.get("codec_repo", "neuphonic/neucodec-onnx-decoder-int8")
    backbone_device = studio_config.get("backbone_device", "cpu")
    codec_device = studio_config.get("codec_device", "cpu")

    import uvicorn

    # Create wrapper app that mounts studio at /studio (matching client API_URL paths)
    root_app = FastAPI()

    # Register video pipeline endpoints
    try:
        from apps.video.api import register_video_endpoints, init_video_pipeline
        register_video_endpoints(studio_app)
        logger.info("Video pipeline endpoints registered")
    except Exception as e:
        logger.warning("Video pipeline not available: %s", e)

    @root_app.on_event("startup")
    async def startup():
        # Init LLM + producer immediately (fast)
        init_studio(studio_config)
        # Init video pipeline
        try:
            init_video_pipeline(tts_manager, job_manager)
        except Exception as e:
            logger.warning("Video pipeline init failed: %s", e)
        # Load TTS in background so server is available while model loads
        asyncio.create_task(_load_tts(backbone, codec, backbone_device, codec_device))

    async def _load_tts(backbone, codec, backbone_device, codec_device):
        try:
            await tts_manager.init(backbone, codec, backbone_device, codec_device)
        except Exception as e:
            logger.error("TTS engine failed to load: %s", e)

    @root_app.on_event("shutdown")
    async def shutdown():
        tts_manager.close()
    root_app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://localhost:8001", "*"],
        allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )
    # Serve Next.js static export from client/out/
    from fastapi.staticfiles import StaticFiles

    _CLIENT_OUT = Path(__file__).parent.parent / "client" / "out"
    _FE_PAGES = {"studio", "video", "voice", "settings", "workflows"}

    if _CLIENT_OUT.exists():
        # Explicit FE page routes (must be registered BEFORE /studio API mount)
        for _page in _FE_PAGES:
            _html = _CLIENT_OUT / f"{_page}.html"
            if _html.exists():
                _content = _html.read_text(encoding="utf-8")
                # Use default arg to capture current value in closure
                root_app.add_api_route(
                    f"/{_page}",
                    lambda _c=_content: HTMLResponse(_c),
                    methods=["GET", "HEAD"],  # HEAD: Next.js route prefetch
                )

        @root_app.api_route("/", methods=["GET", "HEAD"])
        async def serve_root():
            index = _CLIENT_OUT / "index.html"
            if index.exists():
                return HTMLResponse(index.read_text(encoding="utf-8"))
            return HTMLResponse("<h1>Not found</h1>", status_code=404)

    # Mount API (after FE page routes so /studio page wins over API root)
    root_app.mount("/studio", studio_app)

    if _CLIENT_OUT.exists():
        # Serve _next/ static assets
        root_app.mount("/_next", StaticFiles(directory=_CLIENT_OUT / "_next"), name="next-static")

        @root_app.api_route("/{path:path}", methods=["GET", "HEAD"])
        async def serve_static_files(path: str):
            """Serve static assets + Next export pages; SPA-fallback to index."""
            for candidate in (
                _CLIENT_OUT / path,                 # asset (icon, image, ...)
                _CLIENT_OUT / f"{path}.html",       # next export page (no trailing slash)
                _CLIENT_OUT / path / "index.html",  # next export page (trailing slash)
            ):
                if candidate.is_file():
                    return FileResponse(candidate)
            # Unknown route → SPA shell so client-side routing can handle it.
            index = _CLIENT_OUT / "index.html"
            if index.is_file():
                return FileResponse(index)
            return HTMLResponse("<h1>Not found</h1>", status_code=404)
    else:
        @root_app.get("/")
        async def no_client():
            return HTMLResponse(
                "<h1>Client not built</h1><p>Run <code>cd client && npm run build</code></p>",
                status_code=404,
            )

    port = studio_config.get("port", 8002)
    print(f"Studio Voice API: http://localhost:{port}")
    uvicorn.run(root_app, host="127.0.0.1", port=port)


if __name__ == "__main__":
    main()
