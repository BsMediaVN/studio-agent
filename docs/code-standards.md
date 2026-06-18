# Code Standards & Patterns - VietVoice Studio

**Version:** 1.0
**Updated:** 2026-03-20

---

## 1. Python Conventions

### Module Organization
- **Imports:** Organized in 3 sections (stdlib, third-party, local) with blank lines between
- **Docstrings:** Module-level, class-level, function-level (NumPy style preferred)
- **Type hints:** Full type annotations on public methods (Python 3.10+)
- **Naming:** snake_case for functions/variables, PascalCase for classes, UPPER_SNAKE_CASE for constants

### Pydantic Models (studio_api.py)
All request/response data validated via Pydantic v2.

```python
# Request model pattern
class ProduceRequest(BaseModel):
    script: Script
    voice_map: Dict[str, str]
    temperature: float = Field(default=1.0, ge=0.1, le=1.5)
    # Field validation, defaults, doc strings included

# Response model pattern
class JobStatus(BaseModel):
    job_id: str
    status: Literal["pending", "processing", "completed", "failed"]
    progress: float = Field(ge=0, le=100)
    # Immutable (frozen=True) for responses
```

### Error Handling
- Use `fastapi.HTTPException` for API errors with status codes
- Catch broad exceptions, log details, return user-friendly messages
- Global error handler in web_stream.py catches uncaught exceptions

```python
try:
    result = operation()
except ValueError as e:
    logger.error(f"Validation error: {e}")
    raise HTTPException(status_code=400, detail=str(e))
except Exception as e:
    logger.exception(f"Unexpected error: {e}")
    raise HTTPException(status_code=500, detail="Internal server error")
```

---

## 2. Async/Concurrency Patterns

### FastAPI Async Endpoints
- Use `async def` for all endpoints (non-blocking I/O)
- Keep CPU-heavy operations in thread pool: `await asyncio.to_thread(heavy_fn)`
- Use `asyncio.Lock` for critical sections (TTS synthesis)

### Thread Safety (TTSManager)
```python
class TTSManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
```

### Job Queue Pattern (JobManager)
```python
self._jobs: Dict[str, JobStatus] = {}
self._lock = threading.Lock()

def update(self, job_id: str, **kwargs):
    with self._lock:  # Atomic operation
        job = self._jobs[job_id]
        job.update(**kwargs)
```

### Serial Job Execution (max_concurrent_jobs=1)
Enforced via asyncio.Lock:
```python
async with self._produce_lock:
    # Only one job at a time
    result = await StudioProducer.produce(job_id, request)
```

---

## 3. Logging Standards

### FlushFileHandler Pattern (web_stream.py)
Async-safe logging handler that flushes after each write:

```python
class FlushFileHandler(logging.FileHandler):
    def emit(self, record):
        super().emit(record)
        self.flush()  # Prevent buffering in async context

# Usage
logger = logging.getLogger(__name__)
handler = FlushFileHandler("vietvoice.log")
logger.addHandler(handler)
```

### Request Tracing (RequestLogMiddleware)
Middleware logs all HTTP requests with timing:

```python
@app.middleware("http")
async def log_requests(request, call_next):
    start = time.time()
    response = await call_next(request)
    duration = time.time() - start
    logger.info(f"{request.method} {request.url.path} {response.status_code} {duration:.3f}s")
    return response
```

### Logging Format
```python
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
```

---

## 4. TTS Inference Patterns

### Singleton TTSManager Usage
```python
# Initialization (once at startup)
tts = TTSManager.init(
    backbone_repo="pnnbao-ump/VieNeu-TTS-0.3B-q4-gguf",
    codec_repo="neuphonic/distill-neucodec",
    backbone_device="cpu",
    codec_device="cpu"
)

# Usage (thread-safe, shared across endpoints)
audio = tts.synthesize("Xin chào", voice_name="Binh", temperature=1.0)
voices = tts.get_voice_list()
tts.close()  # Cleanup
```

### Streaming Synthesis Pattern
```python
for chunk_audio in tts.synthesize_stream_sync(text, voice_data):
    # Process chunk in real-time
    yield chunk_audio  # HTTP streaming response
```

### Prompt Formatting
Template for TTS models (reference + input text):
```
user: Convert the text to speech:<|TEXT_PROMPT_START|>
{ref_phonemes} {input_phonemes}
<|TEXT_PROMPT_END|>
assistant:<|SPEECH_GENERATION_START|>
{ref_codes_str}
```

---

## 5. API Endpoint Patterns

### Synchronous Endpoints
```python
@studio_app.post("/produce")
async def produce_endpoint(request: ProduceRequest):
    job_id = JobManager.create_job()
    try:
        result_path = StudioProducer.produce(job_id, request)
        return {"job_id": job_id, "download_url": f"/download/{job_id}"}
    except Exception as e:
        JobManager.update(job_id, status="failed", error=str(e))
        raise HTTPException(status_code=400, detail=str(e))
```

### WebSocket Pattern (Progress Updates)
```python
@studio_app.websocket("/progress/{job_id}")
async def websocket_endpoint(websocket: WebSocket, job_id: str):
    await websocket.accept()
    try:
        while True:
            job = JobManager.get(job_id)
            if job:
                await websocket.send_json(job.dict())
            if job.status in ["completed", "failed"]:
                break
            await asyncio.sleep(0.5)
    finally:
        await websocket.close()
```

### File Download Pattern
```python
@studio_app.get("/download/{job_id}")
async def download_endpoint(job_id: str):
    job = JobManager.get(job_id)
    if not job or job.status != "completed":
        raise HTTPException(status_code=404, detail="Job not found or not completed")
    return FileResponse(job.result_url, filename=f"{job_id}.wav")
```

---

## 6. Frontend Patterns (HTML/React)

### Single-File JSX Pattern (client.html)
All React components in one HTML file with Babel JSX transpilation:

```html
<script type="text/babel">
    function AudioPlayer() {
        const [audio, setAudio] = React.useState(null);
        return (
            <div className="player-card">
                <audio src={audio} controls />
            </div>
        );
    }
</script>
```

### Tailwind CSS + Custom Variables Pattern
```html
<style>
    :root {
        --bg-0: #0f0f1e;
        --accent-1: #14b8a6; /* teal */
        --accent-2: #f59e0b; /* amber */
    }

    .surface-card {
        background: linear-gradient(135deg, var(--surface), var(--surface-2));
        border: 1px solid var(--border);
    }
</style>
```

### Tab Navigation Pattern
```javascript
const [activeTab, setActiveTab] = React.useState("studio");

<div className="tab-buttons">
    {["studio", "workflows", "voice", "settings"].map(tab => (
        <button
            key={tab}
            className={activeTab === tab ? "active" : ""}
            onClick={() => setActiveTab(tab)}
        >
            {tabLabels[tab]}
        </button>
    ))}
</div>

<div className="tab-content">
    {activeTab === "studio" && <StudioTab />}
    {activeTab === "workflows" && <WorkflowsTab />}
    ...
</div>
```

### Streaming Audio Pattern
```javascript
async function streamAudio(text) {
    const response = await fetch("/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, voice_id: selectedVoice })
    });

    const reader = response.body.getReader();
    while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        // Process audio chunk (WAV bytes)
        audioBuffer.push(value);
    }
}
```

---

## 7. Gradio UI Patterns (gradio_main.py)

### Reactive Component Updates
```python
with gr.Blocks() as demo:
    backbone_select = gr.Dropdown(choices=backbones, label="Model")
    device_choice = gr.Radio(["auto", "cpu", "cuda"], label="Device")

    # Reactive update
    backbone_select.change(fn=on_model_change, inputs=[backbone_select])
```

### Async Function Pattern
```python
async def synthesize_speech(text, voice, model):
    try:
        # Load model
        tts = await asyncio.to_thread(load_model, model)

        # Synthesize
        audio = tts.infer(text, voice=voice)

        # Return result
        return gr.Audio(value=(24000, audio))
    except Exception as e:
        return gr.Textbox(value=f"Error: {e}")
```

### Tab Organization
```python
with gr.Blocks() as demo:
    with gr.Tabs() as tabs:
        with gr.TabItem("Preset"):
            voice_select = gr.Dropdown(preset_voices)

        with gr.TabItem("Voice Cloning"):
            audio_input = gr.Audio(label="Reference Audio")
            text_input = gr.Textbox(label="Reference Text")
```

---

## 8. Configuration Management

### Environment Variables (config.yaml + .env)
Load order: .env overrides config.yaml

```python
# In studio_api.py
import os
from dotenv import load_dotenv
import yaml

load_dotenv()

with open("config.yaml") as f:
    config = yaml.safe_load(f)

# Override from env
llm_provider = os.getenv("STUDIO_LLM_PROVIDER", config["studio"]["llm"]["provider"])
```

### Device Detection Pattern
```python
def get_device():
    if torch.cuda.is_available():
        return "cuda"
    elif torch.backends.mps.is_available():
        return "mps"  # macOS
    else:
        return "cpu"
```

---

## 9. Voice Management Patterns

### Voice Cloning (Zero-shot)
```python
# From reference audio
voice_data = {
    "codes": tts.encode_reference("reference.wav"),
    "text": "Tác phẩm dự thi"  # Phonemized via sea-g2p
}

# Use in synthesis
audio = tts.infer("New text", voice=voice_data)
```

### Preset Voice Loading
```python
voices = tts.list_preset_voices()  # [(description, id), ...]
preset = tts.get_preset_voice("voice_id")  # {"codes": ..., "text": ...}
audio = tts.infer("Text", voice=preset)
```

### Voice.json Format
```json
{
  "default_voice": "Binh",
  "presets": {
    "Binh": {
      "codes": [234, 123, 456, ...],
      "text": "Phonemized reference text",
      "description": "Male voice - deep"
    }
  }
}
```

---

## 10. Workflow Automation Pattern

### Webhook-triggered Production
```python
@studio_app.post("/workflows/{workflow_id}/trigger")
async def trigger_workflow(workflow_id: str, payload: dict):
    workflow = get_workflow(workflow_id)

    # Create job from workflow template
    request = ProduceRequest(
        script=workflow.script,
        voice_map=workflow.voice_map,
        **workflow.settings
    )

    # Execute
    job_id = JobManager.create_job()
    result = StudioProducer.produce(job_id, request)

    # Optionally call webhook
    if workflow.callback_url:
        await notify_webhook(workflow.callback_url, result)
```

---

## 11. Performance Considerations

### Memory Management
- Keep TTS singleton (don't reload models)
- Clear CUDA cache after batch: `torch.cuda.empty_cache()`
- Auto-cleanup old jobs (1 hour retention)

### Optimization Flags
- LMDeploy for GPU: `use_lmdeploy=true` in config
- GGUF for CPU: 0.3B-q4-gguf model
- Batch mode for parallel texts: `infer_batch()` vs loop

### Streaming vs Batch
- **Streaming:** Lower latency to first chunk (~500ms)
- **Batch:** Higher throughput (4-16 parallel chunks)
- Choose based on user experience requirements

---

## 12. Video Rendering Patterns

### Frames Mode (HyperFrames)

**Module:** `apps/video/frames/`

#### Renderer Pattern (renderer.py)
```python
from apps.video.frames import FramesRenderer

# Check availability (node ≥22, ffmpeg, local binary)
if FramesRenderer.is_available():
    renderer = FramesRenderer(fps=30, workers="auto")
    mp4_path = await renderer.render(
        job_dir=Path("apps/video/frames/project/jobs/{job_id}"),
        output_dir=Path("output/studio/video"),
        progress_callback=progress_fn
    )
```

#### Composition Builder Pattern (composition.py)
```python
# Dialogue segments → HTML composition
segments = [
    {"speaker": "Alice", "text": "Hello", "start_ms": 0, "duration_ms": 500},
    {"speaker": "Bob", "text": "Hi there", "start_ms": 600, "duration_ms": 400},
]

html, assets = build_composition(
    segments=segments,
    width=1920, height=1080, fps=30,
    audio_path=Path("audio.wav"),
    hyperframes_json=Path("apps/video/frames/project/hyperframes.json")
)
# Write to job_dir; assets are relative paths (offline reference)
```

#### Dialogue Parser Pattern (dialogue.py)
```python
# Parse "Name: line" format → speaker + text segments
lines = ["Alice: Hello there!", "Bob: Good morning"]
segments = parse_dialogue(lines)
# segments = [
#   {"speaker": "Alice", "text": "Hello there!"},
#   {"speaker": "Bob", "text": "Good morning"}
# ]

# Auto-assign voices from cache (rotates over available voices)
with_voices = assign_voices(segments, voice_cache=tts.voice_list())
# with_voices[0] = {..., "voice": "Binh"}  (rotates: Binh, Tuyen, Vinh, Doan, Ly, Ngoc, ...)
```

### Key Authoring Rules (Enforced by `hyperframes lint`)
1. Every timed element needs `class="clip"` + `data-start`, `data-duration`, `data-track-index` attributes
2. `<audio>` elements must have explicit `id` (else `media_missing_id` error)
3. Deterministic only — no `Date.now()`, `Math.random()`, network fetches
4. Reference assets via relative local paths (offline, no CDN)

### Pipeline Integration (pipeline.py)
```python
# PipelineConfig defaults
config = PipelineConfig(
    render_mode="frames",  # default; use "face" for SadTalker mode
    frames_fps=30,
    frames_width=1920, frames_height=1080,
    frames_workers="auto",  # parallelization
    frames_gap_s=0.15,  # inter-line silence
)

# VideoPipeline._produce_frames() flow
if config.render_mode == "frames":
    # 1. Parse dialogue → segments + voice assignment
    segments = parse_dialogue_from_script(...)
    segments = assign_voices(segments, voice_cache)
    
    # 2. Synthesize per-line audio (offset by segment timing)
    audio_path, timings = synthesize_dialogue_segments(segments)
    
    # 3. Build HTML composition (GSAP + speaker cards + captions)
    html, assets = build_composition(
        segments, audio_path, timings,
        width=config.frames_width, height=config.frames_height,
        fps=config.frames_fps, gap_s=config.frames_gap_s
    )
    
    # 4. Render via HyperFrames (headless Chrome → FFmpeg)
    mp4 = await FramesRenderer(workers=config.frames_workers).render(
        job_dir, output_dir, progress_callback
    )
```

### API Endpoint Pattern (api.py)
```python
@router.post("/studio/video/generate")
async def generate_video(
    prompt: str = Form(...),
    render_mode: Literal["frames", "face"] = Form("frames"),
    face_image: UploadFile | None = None,
    ...
):
    # Validation: face_image required only in face mode
    config.render_mode = render_mode
    if config.render_mode == "face" and face_image is None:
        raise HTTPException(422, "face_image required for realistic (face) mode")
    
    # Route to appropriate producer
    if config.render_mode == "frames":
        video_producer = FramesVideoProducer(...)
    else:
        video_producer = FaceVideoProducer(...)
    
    job_id = await video_producer.start_job(config)
    return {"job_id": job_id, "status": "queued"}

# Status includes frames_renderer_ready flag
@router.get("/studio/video/status/{job_id}")
async def video_status(job_id: str):
    return {
        "job_id": job_id,
        "status": "processing",
        "frames_renderer_ready": FramesRenderer.is_available(),
        ...
    }
```

---

## 13. Security & Validation

### Input Validation
All Pydantic models auto-validate:
- Type checking (str, int, float, List, Dict)
- Range validation (Field bounds)
- String length limits (max_chars)
- Enum validation (Literal types)

### Output Sanitization
- Strip sensitive data from logs (no full job request dumps)
- Time-limit file downloads (job cleanup removes old files)
- No direct file path exposure (use job_id indirection)

### Rate Limiting
- max_concurrent_jobs=1 (serial execution)
- No explicit API key auth (assumes trusted network)
- Future: Consider adding rate limiter middleware

---

**Document Version:** 1.1
**Audience:** Backend developers, code reviewers
**Updated:** 2026-06-18
