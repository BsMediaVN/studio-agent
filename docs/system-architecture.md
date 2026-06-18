# System Architecture — VietVoice Studio

**Audience:** developers, integrators. **Scope:** current implemented system (Studio TTS + Video pipeline + Next.js client over the vendored VieNeu-TTS engine).

---

## 1. Two-tier design

VietVoice Studio is a **product layer** built on top of a **vendored third-party engine**.

| Tier | Path | Responsibility | Source |
|---|---|---|---|
| **Product** | `apps/studio_api.py`, `apps/video/`, `client/` | Studio API, video pipeline, web UI | this project (BsMediaVN) |
| **Engine** | `src/vieneu/`, `src/vieneu_utils/` | Vietnamese TTS inference, phonemization, audio utils | [VieNeu-TTS](https://github.com/pnnbao97/VieNeu-TTS), Apache-2.0 |

The product layer imports the engine (`from vieneu import Vieneu`). The engine is vendored (not a pip dependency) so local behavior is reproducible. **Treat `src/` as upstream** — change it only when intentionally patching the engine.

---

## 2. High-level component map

```
┌──────────────────────────────────────────────────────────────┐
│  Browser — Next.js UI (client/)                              │
│  pages: studio · video · workflows · voice · settings        │
└───────────────┬──────────────────────────────────────────────┘
                │  HTTP / WebSocket
                ▼
┌──────────────────────────────────────────────────────────────┐
│  FastAPI backend  (apps/studio_api.py, port 8001)            │
│  - serves the built front-end (client/out) as static files   │
│  - mounts the Studio + Video API under /studio               │
│                                                              │
│  TTSManager (singleton)   LLMScriptGenerator   JobManager    │
│  StudioProducer           VideoProducer/VideoPipeline        │
└───────────────┬───────────────────────────────┬──────────────┘
                │                                 │
                ▼                                 ▼
   ┌──────────────────────────┐      ┌──────────────────────────┐
   │  VieNeu-TTS engine        │      │  Video pipeline           │
   │  src/vieneu/              │      │  apps/video/              │
   │  - backends: standard /   │      │  - face/   (SadTalker)    │
   │    fast / remote / xpu    │      │  - body/   (Three.js)     │
   │  - NeuCodec decode        │      │  - voice/  (uses TTS)     │
   │  - sea-g2p phonemize      │      │  - composer/ (FFmpeg)     │
   └──────────────────────────┘      └──────────────────────────┘
                │                                 │
                ▼                                 ▼
        Hugging Face models               output/studio/*.{wav,mp4}
        (downloaded at runtime)
```

External services: an LLM (Claude or OpenAI) for script generation; Hugging Face Hub for model/voice downloads. No third-party media APIs.

---

## 3. Studio (audio) data flow

```
prompt ──(optional)──► LLM script generation ──► Script {characters, scenes, dialogue}
                                                      │
                                                      ▼
                                         voice assignment (auto / manual)
                                                      │
                                                      ▼
                       split text into chunks (max ~256 chars, config.yaml)
                                                      │
                                                      ▼
            per chunk:  sea-g2p phonemize → resolve voice → VieNeu-TTS infer → NeuCodec decode
                                                      │
                                                      ▼
                          join chunks (silence gap / crossfade) → normalize
                                                      │
                                                      ▼
                       store output/studio/{job_id}.wav  +  WebSocket progress
```

Concurrency: jobs are serialized (`max_concurrent_jobs = 1`, `asyncio.Lock`) so a single shared TTS engine instance is never overloaded. `TTSManager` loads models once and caches voices.

---

## 4. Video pipeline (`apps/video/`)

Orchestrated by `VideoPipeline` (`pipeline.py`); exposed via `apps/video/api.py` (registered on the Studio router, same JobManager + WebSocket-progress patterns).

Two render modes are available; selected via `PipelineConfig.render_mode`:

### 4a. Frames mode (default: `render_mode="frames"`)

Fast, CPU-only, deterministic motion-graphic output via **HyperFrames** (headless-Chrome frame capture + FFmpeg):

```
prompt (no image required)
        │
        ▼
1. Script        LLM → dialogue (name: line pairs) + optional timeline
        │
        ▼
2. Voice         apps/video/voice/  → VieNeu-TTS per-line → audio.wav (+ timing, voice rotation)
        │
        ▼
3. Composition   apps/video/frames/composition.py → HTML + GSAP animations (speaker cards, captions, etc.)
        │
        ▼
4. Render        apps/video/frames/renderer.py → HyperFrames binary (local pinned @0.6.110)
                 headless Chromium → frame capture → FFmpeg encode
        │
        ▼
   output/studio/video/{job_id}.mp4
```

Key config (`PipelineConfig`): `render_mode="frames"`, `frames_fps`, `frames_width/height`, `frames_workers`, `frames_gap_s` (inter-line silence). Runs on CPU; no GPU, no face image required, deterministic (same input → byte-identical output). Voices rotate over the TTS `voice_cache`.

Required at provisioning: Node ≥22, FFmpeg/FFprobe on `PATH`, `make setup-frames` (installs HyperFrames + Chromium to `apps/video/frames/project/node_modules/` once). Offline after install.

### 4b. Face mode: `render_mode="face"`

Realistic talking-head output via **SadTalker** + bespoke Three.js body capture (legacy path, kept for production validation):

```
prompt + face image (required)
        │
        ▼
1. Script        LLM → dialogue + timeline
        │
        ▼
2. Voice         apps/video/voice/  → VieNeu-TTS → audio.wav (+ per-line timing)
        │
        ▼
3. Face anim     apps/video/face/   → SadTalker → lip-synced face video
        │
        ▼
4. Body anim     apps/video/body/   → Three.js render (headless) → captured frames
        │
        ▼
5. Compose       apps/video/composer/ → FFmpeg overlay + audio mux (+ burned subtitles)
        │
        ▼
   output/studio/video/{job_id}.mp4
```

Key config: `voice_id`, `target_duration_s`, `body_fps/width/height`, `burn_subtitles`. Runs on CPU or GPU; on Apple Silicon SadTalker uses shared memory. **Deprecation note:** The face path remains for production validation; once frames mode is proven end-to-end with real VieNeu-TTS in production, `body/` and `composer/` will be sunset.

See [`video-pipeline-architecture.md`](video-pipeline-architecture.md) for design rationale and risks.

---

## 5. Engine backends (`src/vieneu/`)

`Vieneu(mode=...)` factory selects a backend sharing one interface (`infer` / `infer_batch` / `infer_stream`):

| Backend | Mode | Use |
|---|---|---|
| `VieNeuTTS` | `standard` | PyTorch or GGUF (Q4/Q8) — CPU/GPU local. Default for the Studio. |
| `FastVieNeuTTS` | `fast` | LMDeploy TurbomindEngine, NVIDIA GPU batching. |
| `RemoteVieNeuTTS` | `remote` | HTTP client to a remote LMDeploy serve endpoint. |
| `XPUVieNeuTTS` | `xpu` | Intel Arc GPU (bfloat16). |

Model = transformer producing `<|speech_N|>` token streams; **NeuCodec** decodes tokens → 24 kHz waveform; **sea-g2p** handles Vietnamese normalization + grapheme-to-phoneme.

---

## 6. Deployment modes

- **Single-port (production-static):** `./start.sh` builds the FE into `client/out`; the backend serves it on `:8001`. Rebuild FE after changes (backend reads from disk, no restart). Frames mode requires `make setup-frames` once at provisioning.
- **Dev (two processes):** backend on `:8001` + `next dev` on `:3000` for hot reload. Frames mode requires `make setup-frames` once.
- **Docker:** see `docker/` (GPU and CPU/GGUF compose files) and [`Deploy.md`](Deploy.md). Frames provisioning (Node + HyperFrames install) baked into image build for offline rendering.

---

## 7. Configuration (`config.yaml`)

- `text_settings` — chunk sizes.
- `backbone_configs` / `codec_configs` — selectable model + codec variants (Hugging Face repos).
- `studio` — active backbone/codec, device (`cpu`/`cuda`/`mps`/`xpu`), `port` (8001), `llm` provider, audio output settings, voice presets (male/female), limits (concurrency, timeout, cleanup).
