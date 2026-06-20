# Frames render mode (HyperFrames)

`render_mode="frames"` turns a script + voice into an **animated / motion-graphic**
MP4 by rendering an HTML composition through [HyperFrames](https://github.com/heygen-com/hyperframes)
(headless-Chrome frame capture → FFmpeg encode). It is the productized replacement
for the bespoke `apps/video/body/` capture + `apps/video/composer/` stitch.

- **Deterministic** — same input → byte-identical video+audio (verified by stream hash).
- **CPU-only**, no GPU. ~realtime for short clips on this Mac.
- **Offline** — local *pinned* binary + vendored GSAP/fonts; rendering does **zero network**.

## Requirements

- **Node ≥ 22** and **FFmpeg/FFprobe** on `PATH`.
- A one-time `npm install` in `project/` that installs the pinned `hyperframes`
  binary **and** its Puppeteer Chromium (~150 MB). After that, no `npx`, no CDN.

## Install once (provisioning)

```bash
make setup-frames        # or: cd apps/video/frames/project && npm install
```

`make setup` runs this automatically. In Docker/CI, run it at image-build time so
Chromium is baked in, never fetched per render.

## Layout

```
project/                 # ONE persistent HyperFrames project (committed scaffold)
├── package.json         # pins hyperframes@0.6.110; scripts use the LOCAL binary
├── hyperframes.json     # project config
├── meta.json
├── index.html           # blank scaffold composition
├── assets/lib/gsap.min.js   # vendored GSAP (no CDN, offline)
├── node_modules/        # installed once (gitignored)
└── jobs/<job_id>/       # ephemeral per-render composition + assets (gitignored)
    ├── index.html, meta.json, hyperframes.json
    └── assets/...
renderer.py              # FramesRenderer — Python subprocess wrapper
```

Each job is a self-contained mini-project under `jobs/` so both `lint` and
`render` accept it as a project dir, while the heavy installed deps (Chromium)
live once in `project/node_modules` and are never copied per job (R4).

## Usage

```python
from apps.video.frames import FramesRenderer

if FramesRenderer.is_available():          # node>=22 + ffmpeg + local binary
    renderer = FramesRenderer(fps=30, workers="auto")
    mp4 = await renderer.render(job_dir, output_dir, progress_cb=cb)
```

`job_dir` must live under `project/jobs/`. The composition builder (Phase 02)
writes `index.html` + `assets/` there before calling `render`.

## B-roll background imagery (optional)

Frames mode can fetch content-matched background images per dialogue segment for a cinematic effect. This is **opt-in** and **gracefully degrades to flat backgrounds** on any failure (network, rate limit, missing key, no result).

**How it works:**
1. Each dialogue line is converted to an English visual keyword (via LLM).
2. Keyword → Pexels photo search → download + local disk cache (keyed by slug).
3. Background `<img>` clip behind a dark scrim, animated with GSAP Ken Burns (scale 1.0→1.08 + subtle pan).
4. Consecutive identical keywords reuse the same image (avoids jarring swaps).

**Config** (`config.yaml`):
```yaml
studio:
  video:
    broll:
      enable: false                              # per-job UI checkbox overrides
      orientation: landscape                     # landscape | portrait | square
      cache_dir: ./output/studio/video/broll-cache
      per_scene: turn                            # dedupe consecutive speakers
```

**Required environment:**
- `PEXELS_API_KEY` (free key from [pexels.com/api](https://www.pexels.com/api))
  - Rate limit: ~200 requests/hour
  - When key is missing or invalid, B-roll is automatically disabled (flat bg used instead)

**UI toggle:** Frames mode shows a "Background visuals (B-roll)" checkbox.
- Enabled only if `PEXELS_API_KEY` is present (`/video/status` returns `broll_available`).
- Disabled with hint "needs PEXELS_API_KEY" when key is missing.

**Fallback behavior (critical):**
- Any failure (offline, rate limit, invalid image, LLM error) → logs warning → uses flat background.
- B-roll problems **never break a video job**.

**Determinism caveat:**
- Results are deterministic + offline **after** the first fetch (disk cache).
- Pexels results may drift over time, so cross-time/cross-machine byte-identical output is **not guaranteed** (unlike the rest of frames mode).

**Attribution:**
- Pexels license requires attribution when images are published.
- For self-hosted internal use, document the credit obligation (no in-video burn required in v1).
- Review attribution requirements before deploying to public/commercial audiences.

## Authoring rules (enforced by `hyperframes lint`)

1. Every timed element needs `class="clip"` + `data-start` / `data-duration` / `data-track-index`.
2. `<audio>` **must** have an `id` or it renders silent (`media_missing_id`).
3. Deterministic only — no `Date.now()`, no `Math.random()`, no network fetches.
4. Reference GSAP/fonts/audio via **relative** local paths (offline).
