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

## Authoring rules (enforced by `hyperframes lint`)

1. Every timed element needs `class="clip"` + `data-start` / `data-duration` / `data-track-index`.
2. `<audio>` **must** have an `id` or it renders silent (`media_missing_id`).
3. Deterministic only — no `Date.now()`, no `Math.random()`, no network fetches.
4. Reference GSAP/fonts/audio via **relative** local paths (offline).
