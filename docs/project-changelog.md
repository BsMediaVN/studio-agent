# VietVoice Studio - Project Changelog

**Format:** [Semantic Versioning](https://semver.org/) | **Updated:** 2026-06-20

---

## [1.3.1] — 2026-06-20 (Current)

### Added
- **B-roll background imagery for frames mode** — optional Pexels API integration + local cache
  - Per-dialogue-segment keyword extraction (via LLM) → Pexels photo search → cached download
  - Graceful fallback to flat background on any network/rate-limit/API failure (never breaks jobs)
  - GSAP Ken Burns animation (scale + subtle pan) over background image with dark scrim
  - Deterministic offline rendering after first fetch (disk cache by slug)
  - Per-job toggle from UI; requires `PEXELS_API_KEY` environment variable
  - Config: `config.yaml` → `studio.video.broll` (enable, orientation, cache_dir, deduplication)
  - Consecutive identical keywords reuse same image (avoids jarring transitions)

### Technical Details
- **New module:** `apps/video/frames/broll.py` (fetch, cache, keyword extraction)
- **Modified:** `apps/video/frames/composition.py` (track 3: background image clip + Ken Burns)
- **Config keys:** `frames_broll` (PipelineConfig + form field), `broll_available` (status response)
- **Determinism caveat:** Pexels results may drift over time; cross-time/cross-machine byte-identical output NOT guaranteed for jobs with B-roll enabled
- **Attribution:** Pexels license requires credit when published; self-hosted internal use documented in module README

---

## [1.3.0] — 2026-06-18 (Previous)

### Added
- **Frames video render mode** (default) — Motion-graphic MP4 output via HyperFrames CLI
  - Deterministic: same input → byte-identical video + audio stream hash verification
  - CPU-only, offline rendering (local pinned HyperFrames @0.6.110 binary + vendored GSAP)
  - No face image required; supports multi-character dialogue with auto voice rotation
  - ~realtime encode on Mac (short clips), fully parallelizable render jobs

- **Dialogue parser & voice assignment** (`apps/video/frames/dialogue.py`)
  - Parse "Name: line" dialogue format → segments with per-line voice rotation
  - Auto-assign voices from cache across character speakers

- **HTML composition builder** (`apps/video/frames/composition.py`)
  - GSAP animations (speaker cards, line-level captions, audio sync)
  - Offline assets (fonts, GSAP library vendored in HyperFrames project)

- **FramesRenderer subprocess wrapper** (`apps/video/frames/renderer.py`)
  - `is_available()` check (Node ≥22, FFmpeg, local binary)
  - Async `render()` with progress callback, process timeout, worker pool

- **API integration** (`apps/video/api.py`)
  - `render_mode` form field (Literal["frames", "face"], default "frames")
  - `face_image` optional (required only for face mode → HTTP 422 if missing & face mode)
  - `/studio/video/status` includes `frames_renderer_ready` flag

- **Frontend mode toggle** (`client/components/video/video-page.tsx`)
  - Animated/Realistic video render mode selector
  - Conditional face upload UI (only in face mode)

- **Provisioning support** (`make setup-frames`, `Makefile`)
  - One-time Node + FFmpeg + HyperFrames Chromium install
  - Integrated into `make setup` (prod-static build flow)
  - Docker image provisioning (deps baked at build, no runtime network)

### Changed
- **PipelineConfig defaults:** `render_mode="frames"` (was undefined, face path implicit)
- **Import optimization:** SadTalker/body imports moved under `TYPE_CHECKING` in `pipeline.py` → frames mode is lightweight (no cv2/torch at import time)
- **Frontend:** Video page now shows animated/realistic toggle (frames is default, animated)

### Deprecated
- `apps/video/body/` (Three.js body capture) — kept for face mode until production validation complete
- `apps/video/composer/` (FFmpeg stitch) — kept for face mode until production validation complete
- **Sunset trigger:** Once frames mode validated end-to-end with real VieNeu-TTS in production

### Technical Details
- **New dependencies:** `hyperframes@0.6.110` (npm), Node ≥22, FFmpeg ≥4.4
- **New runtime requirement:** Chromium (installed once in `apps/video/frames/project/node_modules/`)
- **Breaking change:** Video endpoint now requires `render_mode` form field (default: "frames"); omitting it selects frames mode
- **Breaking change:** `face_image` is optional in frames mode; required only in face mode → HTTP 422 if omitted in face mode

---

## [1.2.9] — 2026-03-20 (Previous release)

### Added
- Multi-character TTS with auto voice assignment
- Zero-shot voice cloning from reference audio
- LLM-powered script generation (Claude/OpenAI)
- REST API (24 Studio endpoints + 7 Web Stream endpoints)
- WebSocket real-time job progress tracking
- Gradio web interface + standalone Next.js client
- Docker GPU/CPU variants
- Python SDK with 4 inference backends (standard, fast, remote, xpu)

### Features
- SadTalker-based realistic talking-head video (face mode)
- Three.js body animation (optional, with placeholder pending Mixamo assets)
- FFmpeg video composition (audio mux, overlay, subtitles)
- Workflow automation (webhook-triggered pipelines)
- LoRA fine-tuning for custom voices

---

## Roadmap (Future)

- **v1.4.0:** Multi-language support (beyond Vietnamese)
- **v1.5.0:** Real-time streaming to platforms (TikTok, YouTube Live)
- **v2.0.0:** Deprecate face mode `body/` + `composer/` (after production validation)
- **TBD:** Advanced emotion/prosody control, Premium voice marketplace, Batch job queuing

---

**Maintained by:** BsMediaVN | **License:** (as per CLAUDE.md)
