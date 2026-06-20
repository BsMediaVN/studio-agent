# VietVoice Studio - Development Roadmap

**Version:** 1.0 | **Last Updated:** 2026-06-20 | **Status:** In Progress

---

## Current Phase: v1.3.x Frames Refinements (95% Complete)

### Phase Objectives
Deliver a CPU-first video render pipeline (HyperFrames) as default with optional content-driven background imagery. Enable motion-graphic video production without GPUs or face images, with cinematic background support.

### Completed Milestones (95%)
- ✅ **M1: Frames Renderer Architecture** — `FramesRenderer` subprocess wrapper + project layout
- ✅ **M2: Composition Builder** — HTML/GSAP animation system + dialogue parsing
- ✅ **M3: API Integration** — `render_mode` field, conditional `face_image` validation
- ✅ **M4: Frontend UI** — Video mode toggle (Animated/Realistic), conditional upload
- ✅ **M5: Provisioning** — `make setup-frames`, Docker integration, offline asset packaging
- ✅ **M6: Documentation** — System architecture, API docs, frames module README
- ✅ **M7: B-roll Imagery** — Pexels API integration, keyword extraction, caching, graceful fallback (2026-06-20)

### Release Status
- **v1.3.0** (2026-06-18): Core frames pipeline shipped
- **v1.3.1** (2026-06-20): B-roll background imagery (optional, Pexels)
- **Default behavior:** `render_mode="frames"` (animated video, CPU-only); B-roll opt-in via UI checkbox

---

## Next Phase: v1.4.0 Multi-Language (Planned Q4 2026)

### Phase Objectives
Extend Vietnamese TTS pipeline to support Tamil, Khmer, Thai, and Lao with language-aware phonemization and preset voice libraries.

### Planned Milestones
- **M1: Language Detection** — Auto-detect input script language; prompt LLM if ambiguous
- **M2: Phonemization** — Multi-language G2P modules (sea-g2p + language-specific)
- **M3: Voice Library Expansion** — Preset voice catalog per language (3-5 voices each)
- **M4: Script Generation** — LLM prompt tuning for each language (dialogue style guides)

### Success Criteria
- 4+ language variants supported end-to-end (TTS → video)
- <5% phonemization error rate per language (validated against phoneticians)
- Zero network dependency for language detection (offline LLM fallback)

---

## Future Phases (Roadmap)

### v1.5.0: Real-Time Streaming (Estimated Q1 2027)
- TikTok/YouTube Live direct-to-platform streaming
- WebRTC ingestion for live input (audio/video merge)
- Job queueing for concurrent render jobs (lift serial constraint)

### v2.0.0: Face Mode Deprecation (Post-Validation)
- Production validation of frames mode against real VieNeu-TTS (3+ months live usage)
- Sunset `apps/video/body/` and `apps/video/composer/` modules
- Consolidate to frames-only video pipeline

### vX.0: Advanced Features (Backlog)
- Emotion/prosody control (pitch, speed, emphasis per line)
- Premium voice marketplace (community voice sharing)
- Batch job orchestration + scheduling (DAG-based workflows)
- Cloud deployment templates (AWS ECS, GCP Run, Azure Container Instances)

---

## Key Dependencies & Risks

| Dependency | Impact | Mitigation |
|---|---|---|
| HyperFrames stability (0.6.110) | Medium — render determinism | Pin version, test on each update, maintain fallback to face mode |
| Node ≥22 + FFmpeg availability | Low — standard tools | Provide Docker base image, installation docs |
| Pexels API availability + rate limit | Medium — B-roll feature | Graceful fallback to flat bg, local disk cache, rate-limit resilience |
| B-roll determinism | Low — offline after cache | Document non-determinism caveat; disclose to users when B-roll enabled |
| Frames mode production validation | High — sunset decision | Monitor v1.3.x in production for 3+ months before v2.0 |
| Multi-language phonemization quality | Medium — TTS quality | Validate with native speakers, maintain error budget |

---

## Success Metrics

- **Adoption:** 100+ frames-mode deployments by EOY 2026
- **Stability:** <0.5% render failure rate (frames + face combined)
- **Performance:** P95 render time <30s for 2-minute scripts
- **Quality:** User satisfaction 4.5+/5 on video output quality

---

## Archive

### Completed Phases
- **v1.0–v1.2.9** — Core TTS, voice cloning, script generation, basic Gradio UI
- **v1.3.0** — Frames video render mode (shipped 2026-06-18)
- **v1.3.1** — B-roll background imagery (shipped 2026-06-20)

---

**Maintained by:** BsMediaVN Engineering | **Reviews:** Monthly alignment sync
