# Self-hosted Video Pipeline Architecture

## Overview

Hệ thống tạo video nhân vật hoàn chỉnh chạy local trên Mac 24GB RAM. Không phụ thuộc API bên thứ 3, chi phí = $0 (ngoài Claude subscription hiện tại). Hỗ trợ thêm background B-roll imagery (Pexels API, tùy chọn).

**Input**: Prompt mô tả scene (+ ảnh mặt nếu dùng face mode)
**Output**: Video MP4 nhân vật nói chuyện (motion-graphic hoặc face-animated)

---

## Hardware Requirements

| Yêu cầu | Thông số | Máy hiện tại |
|---|---|---|
| RAM | 16 GB+ | 24 GB (OK) |
| GPU VRAM | 4-6 GB | Shared memory Apple Silicon (OK) |
| Python | 3.9+ | Đã cài |
| Node.js | 18+ | Đã cài |
| OS | macOS | macOS (OK) |

---

## System Architecture

```
┌─────────────────────────────────────────────────────┐
│                   USER INPUT                         │
│         Ảnh mặt + Prompt mô tả scene                │
└──────────────┬──────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────┐
│     1. SCRIPT GENERATOR      │
│     (Claude API / Manual)    │
│                              │
│  Input: prompt               │
│  Output:                     │
│    - dialogue text           │
│    - animation timeline JSON │
│    - scene description       │
└──────┬────────────┬──────────┘
       │            │
       ▼            ▼
┌──────────┐  ┌─────────────────┐
│ 2. VOICE │  │ 3. BODY ANIMATION│
│ VieNeu-TTS│  │ Three.js+Mixamo │
│          │  │                 │
│ text →   │  │ timeline JSON → │
│ audio.wav│  │ body_video.webm │
└────┬─────┘  └───────┬─────────┘
     │                │
     ▼                │
┌──────────────┐      │
│ 4. FACE ANIM │      │
│  SadTalker   │      │
│              │      │
│ face.png +   │      │
│ audio.wav →  │      │
│ face_video.mp4      │
└────┬─────────┘      │
     │                │
     ▼                ▼
┌─────────────────────────────┐
│      5. VIDEO COMPOSER       │
│          FFmpeg              │
│                              │
│  face_video + body_video    │
│  + audio → final_video.mp4  │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│        OUTPUT                │
│    final_video.mp4           │
│    Nhân vật nói + cử động   │
└─────────────────────────────┘
```

---

## Module Details

### Module 1: Script Generator (Claude)

- **Tool**: Claude (subscription hiện tại, qua chat hoặc API)
- **Input**: Prompt mô tả scene, ví dụ: "Nhân vật giới thiệu về AI trong 30 giây"
- **Output**:
  - Dialogue text cho TTS
  - Animation timeline JSON (body movements tương ứng với lời nói)
  - Camera instructions (zoom, pan)

**Ví dụ animation timeline JSON output:**

```json
{
  "scene": "character introduces AI topic",
  "duration": 30000,
  "dialogue": "Xin chào, hôm nay tôi sẽ giới thiệu về trí tuệ nhân tạo...",
  "keyframes": {
    "head": [
      { "t": 0, "rotate": 0 },
      { "t": 500, "rotate": -5 },
      { "t": 1000, "rotate": 5 }
    ],
    "rightArm": [
      { "t": 0, "rotate": 0 },
      { "t": 300, "rotate": -45 },
      { "t": 600, "rotate": 0 }
    ],
    "body": [
      { "t": 0, "translateY": 0 },
      { "t": 1500, "translateY": -5 },
      { "t": 3000, "translateY": 0 }
    ]
  },
  "camera": [
    { "t": 0, "zoom": 1, "panX": 0 },
    { "t": 15000, "zoom": 1.2, "panX": 50 }
  ]
}
```

### Module 2: Voice — VieNeu-TTS

- **Status**: Đã có sẵn, đã self-host
- **Input**: Dialogue text từ Module 1
- **Output**: `audio.wav` + timestamp từng câu (để sync lip-sync)
- **Chi phí**: $0

### Module 3: Body Animation — Three.js + Mixamo

- **Mixamo** (Adobe, free): Download sẵn 3D model + animation clips
  - Các animation có sẵn: walk, wave, idle, talk gesture, point, nod...
  - Format: FBX/GLTF
  - Download 1 lần, dùng mãi
- **Three.js**: Render 3D model trong browser, điều khiển bằng timeline JSON từ Module 1
- **MediaRecorder API**: Capture canvas → `body_video.webm`
- **Chi phí**: $0, chạy trong browser

**Tech stack:**
- Three.js (3D rendering)
- GSAP hoặc Anime.js (easing/timing)
- Web Animations API
- MediaRecorder API (export)

### Module 4: Face Animation — SadTalker

- **Repo**: https://github.com/OpenTalker/SadTalker
- **License**: Open-source
- **Input**: 1 ảnh mặt (face.png) + audio file (audio.wav từ Module 2)
- **Output**: Video mặt nói chuyện, lip-sync khớp audio (face_video.mp4)
- **VRAM**: ~4-6 GB → Mac 24GB dư sức
- **Chất lượng**:
  - Mặt động tự nhiên
  - Miệng khớp lời nói
  - Đầu lắc nhẹ tự nhiên
  - Mắt chớp
- **Thời gian gen**: ~30s-2 phút per video clip trên Mac

### Module 5: Video Composer — FFmpeg

- **Tool**: FFmpeg (free, command line)
- **Chức năng**:
  - Ghép face_video overlay lên body animation
  - Mix audio track
  - Resize, crop, adjust timing
  - Add background, subtitle nếu cần
- **Output**: `final_video.mp4`
- **Chi phí**: $0

**Ví dụ FFmpeg command:**

```bash
# Ghép face video lên body video
ffmpeg -i body_video.webm -i face_video.mp4 \
  -filter_complex "[0:v][1:v]overlay=x=FACE_X:y=FACE_Y" \
  -i audio.wav -map 2:a \
  -c:v libx264 -c:a aac \
  final_video.mp4
```

---

## Style Options

Cần chọn 1 trong 2 style trước khi build:

### Style A: 2D Illustrated (Khuyến nghị bắt đầu)

```
Body = SVG/CSS animated (kiểu motion graphic)
Face = SadTalker video overlay
Kết quả = Kiểu animated explainer video
```

**Pros:**
- Dễ build hơn
- Face blend tự nhiên hơn với illustrated body
- Không cần kiến thức 3D
- Nhẹ, nhanh

**Cons:**
- Ít ấn tượng hơn 3D
- Giới hạn góc nhìn

### Style B: 3D Character (Advanced)

```
Body = Three.js + Mixamo 3D model
Face = SadTalker texture map lên model head
Kết quả = Kiểu game character / VTuber
```

**Pros:**
- Ấn tượng hơn
- Xoay 360 được
- Nhiều animation clips có sẵn từ Mixamo

**Cons:**
- Khó hơn nhiều
- Face-to-3D mapping phức tạp
- Cần hiểu Three.js

---

## Risks & Limitations

| Rủi ro | Mức độ | Giải pháp |
|---|---|---|
| Face + Body ghép không tự nhiên | Cao | Dùng style cartoon/illustrated cho body, face blend tốt hơn |
| SadTalker chạy chậm trên Mac | Trung bình | ~30s-2 phút per clip, chấp nhận được |
| Mixamo model style khác face | Trung bình | Chọn model style phù hợp, hoặc dùng 2D body |
| Video dài bị lặp animation | Thấp | Xây library nhiều animation clips, chain lại |
| SadTalker output resolution thấp | Trung bình | Upscale bằng Real-ESRGAN (free, chạy local) |

---

## Implementation Phases

### Phase 0: Validation (Quan trọng nhất)
- Cài SadTalker trên Mac
- Test thử: 1 ảnh mặt + 1 audio file ngắn
- Đánh giá chất lượng output
- Nếu không chạy được → cần plan B (dùng lightweight alternative)
- **Mục tiêu**: Xác nhận pipeline khả thi trên hardware hiện tại

### Phase 1: Voice + Face Pipeline
- Kết nối VieNeu-TTS output → SadTalker input
- Build script: text → audio → face video (automated)
- **Output**: Video mặt nhân vật nói chuyện có lip-sync

### Phase 2: Body Animation
- Setup Three.js project hoặc SVG animation system
- Download Mixamo animations (idle, talk gesture, wave...)
- Build animation engine đọc timeline JSON → render animation
- Implement MediaRecorder export → webm/mp4
- **Output**: Body animation video

### Phase 3: Video Composition
- FFmpeg ghép face video + body animation
- Audio sync
- Background, subtitle support
- **Output**: Video hoàn chỉnh

### Phase 4: Automation
- Claude auto-generate script + timeline JSON từ prompt
- One-command pipeline: prompt → final video
- Web UI (optional) để upload ảnh + nhập prompt
- **Output**: Fully automated pipeline

---

## Tech Stack Summary

| Component | Technology | Chi phí |
|---|---|---|
| AI Script/Timeline | Claude (subscription) | Đang trả |
| Voice/TTS | VieNeu-TTS | $0 (đã có) |
| Face Animation | SadTalker | $0 (open-source) |
| Body Animation | Three.js + Mixamo | $0 (free) |
| Animation Engine | GSAP / Anime.js | $0 (free) |
| Video Composition | FFmpeg | $0 (free) |
| Optional Upscale | Real-ESRGAN | $0 (open-source) |
| **Total additional cost** | | **$0** |

---

## Directory Structure (Proposed)

```
studio-agent/
├── video-pipeline/
│   ├── scripts/
│   │   ├── generate_script.py      # Claude → script + timeline JSON
│   │   ├── generate_voice.py       # VieNeu-TTS wrapper
│   │   ├── generate_face.py        # SadTalker wrapper
│   │   ├── generate_body.py        # Three.js render trigger
│   │   ├── compose_video.py        # FFmpeg composition
│   │   └── pipeline.py             # Full pipeline orchestrator
│   ├── models/
│   │   ├── sadtalker/              # SadTalker model weights
│   │   └── mixamo/                 # Downloaded Mixamo animations
│   ├── templates/
│   │   ├── body_2d/                # SVG body templates
│   │   └── body_3d/                # 3D model files
│   ├── web/
│   │   ├── animation-engine/       # Three.js animation renderer
│   │   └── ui/                     # Optional web UI
│   ├── output/                     # Generated videos
│   └── README.md
```

---

## Notes

- Toàn bộ pipeline chạy offline trên Mac 24GB RAM
- Không phụ thuộc API bên thứ 3 (trừ Claude cho script generation)
- Video thời lượng không giới hạn (chain nhiều clips)
- Kết quả là animated character style, không phải photorealistic video
- Phase 0 (SadTalker validation) quyết định toàn bộ hướng đi
