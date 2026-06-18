# VietVoice Studio - Project Overview & Product Development Requirements

**Project Name:** VietVoice Studio (formerly VieNeu-TTS)
**Version:** 1.2.9
**Owner:** BsMediaVN
**Last Updated:** 2026-03-20

---

## 1. Product Overview

VietVoice Studio is a production-ready Vietnamese Text-to-Speech (TTS) platform with advanced multi-character audio production, instant voice cloning, and LLM-powered script generation. It enables automated creation of engaging video content for TikTok, YouTube, and other platforms without manual voice recording.

### Target Users
- **Content creators** - Auto-generate voiceovers for video shorts
- **Video production studios** - Batch production of multilingual audio content
- **Marketing teams** - Dynamic ad copy localization with natural speech
- **Developers** - Integrate TTS into applications via REST API or Python SDK

### Business Goals
1. **Enable one-click video content generation** - From text to publishable audio in seconds
2. **Reduce production bottlenecks** - Replace manual voice recording workflows
3. **Support multiple voices and characters** - Multi-speaker audio in single production
4. **Provide flexible deployment** - Local, cloud, or hybrid architectures

---

## 2. Key Features

### Core TTS Capabilities
- **Vietnamese text-to-speech** - 0.3B and 0.5B transformer models
- **24 kHz high-fidelity audio** - Professional studio quality
- **Zero-shot voice cloning** - Instant custom voices from 3-5 seconds of reference audio
- **Multi-character production** - Automatic voice assignment across dialogue scenes
- **Real-time streaming** - WAV chunk delivery for low-latency applications

### Advanced Features
- **LLM-powered script generation** - Auto-create dialogue from prompts (Claude/OpenAI)
- **Video production (two modes)**:
  - **Frames mode** (default) — Motion-graphic videos from text prompts, CPU-only, deterministic, offline (HyperFrames + local Chromium)
  - **Face mode** — Realistic talking-head videos with SadTalker + optional body animation
- **Workflow automation** - Webhook-triggered production pipelines
- **LoRA fine-tuning** - Custom voice personalization via gradient-based training
- **GPU acceleration** - LMDeploy optimization for NVIDIA GPUs
- **CPU inference** - GGUF quantized models (Q4/Q8) for edge deployment
- **Audio post-processing** - Normalization, crossfading, silence adjustment

### Integration Points
- FastAPI REST API (28 endpoints)
- WebSocket real-time progress tracking
- Gradio web interface with dark/light themes
- Standalone web client (React + Tailwind, animated/realistic video mode toggle)
- Python SDK with 4 inference backends
- HyperFrames video render pipeline (motion-graphic output)

---

## 3. Technical Architecture

### Model Stack
| Component | Technology | Purpose |
|-----------|-----------|---------|
| TTS Backbone | VieNeu-TTS (Transformers) | Speech token generation |
| Audio Codec | NeuCodec + DistillNeuCodec | Waveform decoding |
| Quantization | GGUF (Q4/Q8) | CPU-optimized inference |
| GPU Optimization | LMDeploy TurbomindEngine | Batched GPU inference |

### Deployment Options
1. **Local** - CLI with Gradio UI, full API access
2. **Docker GPU** - Multi-stage build with CUDA support
3. **Docker CPU** - GGUF-optimized container
4. **Remote Server** - LMDeploy serve mode with HTTP API

### Tech Stack Summary
- **Backend:** FastAPI + Uvicorn (async request handling)
- **TTS Engine:** PyTorch + HuggingFace Transformers
- **Frontend:** Gradio 5.49.1+ + HTML/Tailwind web client
- **LLM Integration:** Claude CLI / Anthropic SDK / OpenAI SDK
- **Containerization:** Docker + docker-compose
- **Package Manager:** uv (Astral) with multi-index support
- **Python Version:** 3.10+ required

---

## 4. System Limits & Constraints

| Constraint | Value | Rationale |
|-----------|-------|-----------|
| Max script length | 10,000 chars | LLM context management |
| Max concurrent jobs | 1 (serial) | GPU memory, single TTS instance |
| Job timeout | 10 minutes | Prevent hanging resources |
| Auto-cleanup interval | 1 hour | Disk space management |
| Max characters per scene | 4 | UI/workflow complexity |
| Max batch size (GPU) | 16 | Memory constraints |
| Chunk size (streaming) | 256 chars default | Latency/quality tradeoff |
| Sample rate | 24 kHz (fixed) | Model training requirement |

---

## 5. API Endpoints Summary

### Studio API (24 endpoints)
**Script generation:** `POST /studio/generate-script`
**Production:** `POST /studio/produce`, `/studio/pipeline`, `/studio/pipeline-json`
**Voice management:** `POST /studio/clone-voice`, `GET /studio/list-cloned-voices`, `DELETE /studio/cloned-voices/{name}`
**Job tracking:** `GET /studio/job-status/{job_id}`, `GET /studio/download/{job_id}`, `WS /studio/progress/{job_id}`
**Workflows:** `POST/GET/PUT/DELETE /studio/workflows`, `POST /studio/workflows/{id}/trigger`, `GET /studio/workflows/{id}/runs`
**Utilities:** `GET /studio/voices`, `GET /studio/status`

### Web Stream API (7 endpoints)
**Models:** `GET /models`, `POST /set_model`
**Streaming:** `GET /stream`, `POST /stream`
**Utilities:** `POST /extract_url`, `GET /voices`
**UI:** `GET /`

---

## 6. Configuration & Environment

### Model Selection
- **Backbone:** 6 variants (GPU PyTorch + GGUF Q4/Q8 CPU)
- **Codec:** 3 options (Standard, Distill, ONNX)
- **Device:** Auto-detect (CPU/MPS/CUDA) or manual override

### LLM Provider Configuration
```
Default: claude_cli (local Claude subscription, no API key needed)
Fallback: claude (Anthropic SDK, requires ANTHROPIC_API_KEY)
Alternative: openai (OpenAI SDK, requires OPENAI_API_KEY)
```

### Voice Management
- **Preset voices:** 6 (3 male: Binh, Tuyen, Vinh; 3 female: Doan, Ly, Ngoc)
- **Voice cloning:** Zero-shot from reference audio
- **Custom voices:** Via LoRA fine-tuning with custom voices.json

---

## 7. Non-Functional Requirements

### Performance
- Single chunk inference: < 2 seconds (0.3B model on GPU)
- Streaming latency: < 500ms to first chunk
- Batch processing: 4-16 samples in parallel on NVIDIA GPU
- Memory footprint: ~2GB (0.3B model + codec on GPU)

### Reliability
- Auto-cleanup of stale jobs (hourly)
- Graceful error handling with detailed error messages
- Fallback to CPU if GPU unavailable
- Network cache for offline model loading

### Monitoring
- Request-level logging with timing
- Job status tracking (created, processing, completed, failed)
- WebSocket real-time progress updates
- Comprehensive error reporting

### Security
- Assumes trusted network (no authentication layer)
- Audio files time-limited (job cleanup)
- Optional Perth audio watermarking
- No PII logging in production

---

## 8. Success Metrics

- **Adoption:** 50+ end-user deployments in 6 months
- **Stability:** 99.5% uptime, < 1% error rate on production jobs
- **Performance:** 95th percentile latency < 5 seconds for 10K char script
- **User satisfaction:** 4.5+ star rating (if public)
- **Community:** 500+ GitHub stars, 100+ Discord members

---

## 9. Roadmap (Future)

**Completed (v1.2.9)**
- Multi-character TTS with auto voice assignment
- Zero-shot voice cloning
- LLM script generation
- REST API + WebSocket streaming
- Gradio UI + web client
- Docker GPU/CPU variants
- Python SDK with 4 backends

**Completed (v1.3.0)**
- Frames video render mode (HyperFrames, motion-graphic, CPU-only, deterministic)
- Dialogue parsing with auto voice rotation
- HTML composition builder (GSAP animations, speaker cards, captions)

**Planned**
- Multi-language support (beyond Vietnamese)
- Real-time streaming to platforms (TikTok, YouTube Live)
- Advanced emotion/prosody control
- Premium voice marketplace
- Batch job queuing and scheduling
- Deprecation of face mode `body/` and `composer/` modules (after production validation)

---

## 10. Dependencies & Installation

### Minimum Requirements
- Python 3.10+
- Node.js ≥ 22 (for HyperFrames frames render mode)
- FFmpeg + FFprobe (for frames & face mode video composition)
- 4GB RAM (CPU mode), 8GB VRAM (GPU mode)
- 20GB disk space (models + output)
- ~500 MB (HyperFrames Chromium + dependencies, installed once via `make setup-frames`)

### Core Dependencies
- torch + torchaudio (with PyPI indexes for platform-specific builds)
- transformers, datasets, librosa
- neucodec (audio codec)
- fastapi, uvicorn (API server)
- gradio >= 5.49.1 (UI framework)
- sea-g2p (Vietnamese phonemization)
- llama-cpp-python (GGUF support)
- lmdeploy (GPU optimization)
- peft (LoRA support)
- anthropic, openai (LLM SDKs)
- **Video rendering:** hyperframes @0.6.110 (NPM, frames mode), opencv + imageio (face mode)

---

**Document Version:** 1.0
**Next Review:** 2026-06-20
