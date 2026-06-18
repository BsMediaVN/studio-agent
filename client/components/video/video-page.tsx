'use client';

import { useState, useRef, useCallback, useEffect } from 'react';
import { API_URL, WS_URL } from '@/lib/constants';

type VideoJobStatus = {
  job_id: string;
  status: 'queued' | 'processing' | 'complete' | 'error';
  progress: number;
  current_step: string;
  result_url?: string;
  error?: string;
};

type VoiceOption = { id: string; name: string };

const VOICE_OPTIONS: VoiceOption[] = [
  { id: 'Binh', name: 'Binh (nam)' },
  { id: 'Tuyen', name: 'Tuyen (nam)' },
  { id: 'Vinh', name: 'Vinh (nam)' },
  { id: 'Doan', name: 'Doan (nu)' },
  { id: 'Ly', name: 'Ly (nu)' },
  { id: 'Ngoc', name: 'Ngoc (nu)' },
];

const DURATION_PRESETS = [
  { label: '15s', value: 15 },
  { label: '30s', value: 30 },
  { label: '1m', value: 60 },
  { label: '2m', value: 120 },
];

type RenderMode = 'frames' | 'face';

const PIPELINE_STAGES: Record<RenderMode, { label: string; range: string; icon: string }[]> = {
  frames: [
    { label: 'Script parsing', range: '0%', icon: 'M4 7h16M4 12h16M4 17h10' },
    { label: 'Voice synthesis', range: '0-55%', icon: 'M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z' },
    { label: 'Composition', range: '60%', icon: 'M3 3h7v7H3zM14 3h7v7h-7zM14 14h7v7h-7zM3 14h7v7H3z' },
    { label: 'Frames render', range: '60-100%', icon: 'M10 8l6 4-6 4V8z' },
  ],
  face: [
    { label: 'Voice synthesis', range: '0-30%', icon: 'M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z' },
    { label: 'Face animation', range: '30-55%', icon: 'M9 9h.01M15 9h.01M8 13a4 4 0 0 0 8 0' },
    { label: 'Body animation', range: '55-80%', icon: 'M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2' },
    { label: 'Video composition', range: '80-95%', icon: 'M3 3h7v7H3zM14 3h7v7h-7z' },
  ],
};

export function VideoPage() {
  const [prompt, setPrompt] = useState('');
  const [renderMode, setRenderMode] = useState<RenderMode>('frames');
  const [faceAvailable, setFaceAvailable] = useState(true);
  const [voiceId, setVoiceId] = useState('Binh');
  const [duration, setDuration] = useState<number | null>(null);  // null = Auto (from content)
  const [burnSubs, setBurnSubs] = useState(true);
  const [faceImage, setFaceImage] = useState<File | null>(null);
  const [facePreview, setFacePreview] = useState<string | null>(null);
  const [jobStatus, setJobStatus] = useState<VideoJobStatus | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const wsRef = useRef<WebSocket | null>(null);

  // Detect whether the server supports Realistic (face) mode; if not, disable it.
  useEffect(() => {
    fetch(`${API_URL}/studio/video/status`)
      .then((r) => r.json())
      .then((s) => {
        const ok = !!s.face_engine_available;
        setFaceAvailable(ok);
        if (!ok) setRenderMode('frames');
      })
      .catch(() => setFaceAvailable(false));
  }, []);

  const handleFileChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > 10 * 1024 * 1024) {
      setError('Image must be under 10MB');
      return;
    }
    setFaceImage(file);
    setFacePreview(URL.createObjectURL(file));
    setError(null);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    const file = e.dataTransfer.files[0];
    if (!file || !file.type.startsWith('image/')) return;
    if (file.size > 10 * 1024 * 1024) {
      setError('Image must be under 10MB');
      return;
    }
    setFaceImage(file);
    setFacePreview(URL.createObjectURL(file));
    setError(null);
  }, []);

  const startGeneration = useCallback(async () => {
    if (!prompt.trim()) return;
    if (renderMode === 'face' && !faceImage) return;
    setIsGenerating(true);
    setError(null);
    setVideoUrl(null);
    setJobStatus(null);

    try {
      const formData = new FormData();
      if (renderMode === 'face' && faceImage) {
        formData.append('face_image', faceImage);
      }
      formData.append('prompt', prompt);
      formData.append('voice_id', voiceId);
      formData.append('render_mode', renderMode);
      if (duration != null) formData.append('target_duration_s', String(duration));
      formData.append('burn_subtitles', String(burnSubs));
      formData.append('body_test_mode', 'true');

      const res = await fetch(`${API_URL}/studio/video/generate`, {
        method: 'POST',
        body: formData,
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({ detail: res.statusText }));
        const detail = Array.isArray(data.detail)
          ? data.detail.map((d: { msg?: string }) => d.msg).filter(Boolean).join('; ')
          : data.detail;
        throw new Error(detail || `HTTP ${res.status}`);
      }

      const { job_id } = await res.json();
      setJobStatus({ job_id, status: 'queued', progress: 0, current_step: 'Queued...' });

      // Connect WebSocket for progress
      const ws = new WebSocket(`${WS_URL}/studio/progress/${job_id}`);
      wsRef.current = ws;

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data) as VideoJobStatus;
          setJobStatus(data);

          if (data.status === 'complete' && data.result_url) {
            setVideoUrl(`${API_URL}${data.result_url}`);
            setIsGenerating(false);
            ws.close();
          } else if (data.status === 'error') {
            setError(data.error || 'Video generation failed');
            setIsGenerating(false);
            ws.close();
          }
        } catch {}
      };

      ws.onerror = () => {
        setError('WebSocket connection lost');
        setIsGenerating(false);
      };

      ws.onclose = () => {
        wsRef.current = null;
      };
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start video generation');
      setIsGenerating(false);
    }
  }, [faceImage, prompt, renderMode, voiceId, duration, burnSubs]);

  const canGenerate =
    prompt.trim().length > 0 &&
    (renderMode === 'frames' || !!faceImage) &&
    !isGenerating;

  return (
    <div style={{ maxWidth: 1280, margin: '0 auto', padding: '24px' }}>
      {/* Header */}
      <div style={{ marginBottom: 24 }}>
        <h1 className="title-text" style={{ fontSize: 22, color: 'var(--text-1)', marginBottom: 4 }}>
          Video Generator
        </h1>
        <p style={{ fontSize: 13, color: 'var(--text-2)' }}>
          {renderMode === 'frames'
            ? 'Paste your script/content — it is read aloud verbatim with synced captions (no face image). Multi-speaker: use "Name: line" per turn.'
            : 'Upload a face image + write a prompt to generate a realistic talking-head video with lip-sync.'}
        </p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24, alignItems: 'start' }}>
        {/* Left Column — Input */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* Render mode toggle */}
          <div
            style={{
              background: 'var(--surface)',
              border: '1px solid var(--border)',
              borderRadius: 12,
              padding: 6,
              display: 'grid',
              gridTemplateColumns: '1fr 1fr',
              gap: 6,
            }}
          >
            {([
              { mode: 'frames' as RenderMode, title: 'Animated', sub: 'Motion graphic · no face' },
              { mode: 'face' as RenderMode, title: 'Realistic',
                sub: faceAvailable ? 'SadTalker face' : 'Unavailable on this server' },
            ]).map((opt) => {
              const active = renderMode === opt.mode;
              const disabled = isGenerating || (opt.mode === 'face' && !faceAvailable);
              return (
                <button
                  key={opt.mode}
                  onClick={() => !disabled && setRenderMode(opt.mode)}
                  disabled={disabled}
                  title={opt.mode === 'face' && !faceAvailable
                    ? 'Realistic mode needs SadTalker/OpenCV, not installed on this server'
                    : undefined}
                  style={{
                    padding: '10px 12px',
                    borderRadius: 8,
                    border: `1px solid ${active ? 'var(--accent-1)' : 'transparent'}`,
                    background: active ? 'rgba(45,212,191,0.15)' : 'transparent',
                    color: active ? 'var(--accent-1)' : 'var(--text-2)',
                    cursor: disabled ? 'not-allowed' : 'pointer',
                    opacity: disabled && !active ? 0.45 : 1,
                    textAlign: 'left',
                    transition: 'all 0.15s',
                  }}
                >
                  <div style={{ fontSize: 14, fontWeight: 600 }}>{opt.title}</div>
                  <div style={{ fontSize: 11, opacity: 0.8 }}>{opt.sub}</div>
                </button>
              );
            })}
          </div>

          {/* Face Image Upload — realistic mode only */}
          {renderMode === 'face' ? (
          <div
            className="surface-card"
            style={{
              background: 'var(--surface)',
              border: '1px solid var(--border)',
              borderRadius: 12,
              padding: 20,
            }}
          >
            <label style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-1)', display: 'block', marginBottom: 10 }}>
              Face Image
            </label>
            <div
              onClick={() => fileInputRef.current?.click()}
              onDrop={handleDrop}
              onDragOver={(e) => e.preventDefault()}
              style={{
                border: `2px dashed ${facePreview ? 'var(--accent-1)' : 'var(--border)'}`,
                borderRadius: 10,
                padding: facePreview ? 0 : 32,
                textAlign: 'center',
                cursor: 'pointer',
                transition: 'border-color 0.2s',
                overflow: 'hidden',
                minHeight: 180,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                background: 'var(--surface-2)',
              }}
            >
              {facePreview ? (
                <img
                  src={facePreview}
                  alt="Face preview"
                  style={{ maxWidth: '100%', maxHeight: 280, objectFit: 'contain', borderRadius: 8 }}
                />
              ) : (
                <div>
                  <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="var(--text-2)" strokeWidth="1.5" style={{ margin: '0 auto 8px' }}>
                    <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M17 8l-5-5-5 5M12 3v12" />
                  </svg>
                  <p style={{ fontSize: 13, color: 'var(--text-2)' }}>
                    Click or drag & drop face image
                  </p>
                  <p style={{ fontSize: 11, color: 'var(--placeholder)' }}>PNG, JPG up to 10MB</p>
                </div>
              )}
            </div>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/png,image/jpeg"
              onChange={handleFileChange}
              style={{ display: 'none' }}
            />
          </div>
          ) : (
          <div
            style={{
              background: 'var(--surface-2)',
              border: '1px dashed var(--border)',
              borderRadius: 12,
              padding: '14px 16px',
              display: 'flex',
              alignItems: 'center',
              gap: 10,
              fontSize: 12,
              color: 'var(--text-2)',
            }}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--accent-1)" strokeWidth="2">
              <path d="M9 12l2 2 4-4M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0z" />
            </svg>
            Animated mode renders an on-brand scene with captions — no face image needed.
          </div>
          )}

          {/* Prompt */}
          <div
            style={{
              background: 'var(--surface)',
              border: '1px solid var(--border)',
              borderRadius: 12,
              padding: 20,
            }}
          >
            <label style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-1)', display: 'block', marginBottom: 10 }}>
              {renderMode === 'frames' ? 'Script / Content' : 'Script / Prompt'}
            </label>
            <textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder={renderMode === 'frames'
                ? 'Dán nội dung cần đọc thành video... (nhiều nhân vật: mỗi dòng "Tên: lời thoại")'
                : 'Write what the character should say...'}
              rows={5}
              maxLength={20000}
              style={{
                width: '100%',
                background: 'var(--surface-2)',
                border: '1px solid var(--border)',
                borderRadius: 8,
                padding: '10px 12px',
                color: 'var(--text-1)',
                fontSize: 14,
                resize: 'vertical',
                outline: 'none',
                fontFamily: 'inherit',
              }}
            />
            <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 4 }}>
              <span style={{ fontSize: 11, color: 'var(--text-2)' }}>{prompt.length}/20000</span>
            </div>
          </div>

          {/* Settings Row */}
          <div
            style={{
              background: 'var(--surface)',
              border: '1px solid var(--border)',
              borderRadius: 12,
              padding: 20,
              display: 'grid',
              gridTemplateColumns: '1fr 1fr',
              gap: 16,
            }}
          >
            {/* Voice */}
            <div>
              <label style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-2)', display: 'block', marginBottom: 6 }}>
                Voice
              </label>
              <select
                value={voiceId}
                onChange={(e) => setVoiceId(e.target.value)}
                style={{
                  width: '100%',
                  background: 'var(--surface-2)',
                  border: '1px solid var(--border)',
                  borderRadius: 6,
                  padding: '8px 10px',
                  color: 'var(--text-1)',
                  fontSize: 13,
                  outline: 'none',
                  cursor: 'pointer',
                }}
              >
                {VOICE_OPTIONS.map((v) => (
                  <option key={v.id} value={v.id}>{v.name}</option>
                ))}
              </select>
            </div>

            {/* Duration — Auto (length follows content) or fit to a fixed time */}
            <div>
              <label style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-2)', display: 'block', marginBottom: 6 }}>
                Duration {duration == null && <span style={{ color: 'var(--accent-1)' }}>· Auto (theo nội dung)</span>}
              </label>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
                {([{ label: 'Auto', value: null }, ...DURATION_PRESETS] as { label: string; value: number | null }[]).map((d) => {
                  const active = duration === d.value;
                  return (
                    <button
                      key={d.label}
                      onClick={() => setDuration(d.value)}
                      style={{
                        padding: '7px 12px',
                        borderRadius: 6,
                        border: `1px solid ${active ? 'var(--accent-1)' : 'var(--border)'}`,
                        background: active ? 'rgba(45,212,191,0.15)' : 'var(--surface-2)',
                        color: active ? 'var(--accent-1)' : 'var(--text-2)',
                        fontSize: 12,
                        fontWeight: 500,
                        cursor: 'pointer',
                        transition: 'all 0.15s',
                      }}
                    >
                      {d.label}
                    </button>
                  );
                })}
                <input
                  type="number"
                  min={3}
                  max={600}
                  placeholder="giây"
                  value={duration != null && !DURATION_PRESETS.some((p) => p.value === duration) ? duration : ''}
                  onChange={(e) => {
                    const v = parseInt(e.target.value, 10);
                    setDuration(Number.isFinite(v) && v >= 3 ? Math.min(v, 600) : null);
                  }}
                  style={{
                    width: 72,
                    padding: '7px 8px',
                    borderRadius: 6,
                    border: '1px solid var(--border)',
                    background: 'var(--surface-2)',
                    color: 'var(--text-1)',
                    fontSize: 12,
                    outline: 'none',
                  }}
                />
              </div>
            </div>

            {/* Subtitles toggle */}
            <div style={{ gridColumn: '1 / -1', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span style={{ fontSize: 12, color: 'var(--text-2)' }}>Burn subtitles</span>
              <button
                onClick={() => setBurnSubs(!burnSubs)}
                style={{
                  width: 40,
                  height: 22,
                  borderRadius: 11,
                  border: 'none',
                  background: burnSubs ? 'var(--accent-1)' : 'var(--border)',
                  cursor: 'pointer',
                  position: 'relative',
                  transition: 'background 0.2s',
                }}
              >
                <span
                  style={{
                    position: 'absolute',
                    top: 2,
                    left: burnSubs ? 20 : 2,
                    width: 18,
                    height: 18,
                    borderRadius: '50%',
                    background: '#fff',
                    transition: 'left 0.2s',
                  }}
                />
              </button>
            </div>
          </div>

          {/* Generate Button */}
          <button
            onClick={startGeneration}
            disabled={!canGenerate}
            style={{
              width: '100%',
              padding: '14px',
              borderRadius: 10,
              border: 'none',
              background: canGenerate
                ? 'linear-gradient(135deg, var(--accent-1), var(--accent-2))'
                : 'var(--surface-2)',
              color: canGenerate ? '#fff' : 'var(--text-2)',
              fontSize: 15,
              fontWeight: 600,
              cursor: canGenerate ? 'pointer' : 'not-allowed',
              transition: 'opacity 0.2s',
              opacity: canGenerate ? 1 : 0.5,
            }}
          >
            {isGenerating ? 'Generating...' : 'Generate Video'}
          </button>
        </div>

        {/* Right Column — Preview + Progress */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* Video Preview / Progress */}
          <div
            style={{
              background: 'var(--surface)',
              border: '1px solid var(--border)',
              borderRadius: 12,
              overflow: 'hidden',
              minHeight: 400,
              display: 'flex',
              flexDirection: 'column',
            }}
          >
            {videoUrl ? (
              <div style={{ flex: 1 }}>
                <video
                  src={videoUrl}
                  controls
                  autoPlay
                  style={{ width: '100%', maxHeight: 500, background: '#000', display: 'block' }}
                />
                <div style={{ padding: '12px 16px', display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
                  <a
                    href={videoUrl}
                    download
                    style={{
                      padding: '8px 16px',
                      borderRadius: 6,
                      background: 'var(--accent-1)',
                      color: '#fff',
                      fontSize: 13,
                      fontWeight: 500,
                      textDecoration: 'none',
                      cursor: 'pointer',
                    }}
                  >
                    Download MP4
                  </a>
                </div>
              </div>
            ) : isGenerating && jobStatus ? (
              <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: 40 }}>
                {/* Animated spinner */}
                <div style={{
                  width: 64, height: 64, borderRadius: '50%',
                  border: '3px solid var(--border)',
                  borderTopColor: 'var(--accent-1)',
                  animation: 'spin 1s linear infinite',
                  marginBottom: 20,
                }} />
                <p style={{ fontSize: 14, color: 'var(--text-1)', fontWeight: 500, marginBottom: 8 }}>
                  {jobStatus.current_step || 'Processing...'}
                </p>
                {/* Progress bar */}
                <div style={{
                  width: '80%', height: 6, borderRadius: 3,
                  background: 'var(--surface-2)', overflow: 'hidden',
                }}>
                  <div style={{
                    height: '100%', borderRadius: 3,
                    background: 'linear-gradient(90deg, var(--accent-1), var(--accent-2))',
                    width: `${jobStatus.progress}%`,
                    transition: 'width 0.5s ease',
                  }} />
                </div>
                <p style={{ fontSize: 12, color: 'var(--text-2)', marginTop: 8 }}>
                  {jobStatus.progress}%
                </p>
              </div>
            ) : (
              <div style={{
                flex: 1, display: 'flex', flexDirection: 'column',
                alignItems: 'center', justifyContent: 'center', padding: 40,
                color: 'var(--text-2)',
              }}>
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" style={{ marginBottom: 12, opacity: 0.5 }}>
                  <rect x="2" y="2" width="20" height="20" rx="2.18" ry="2.18" />
                  <path d="M10 8l6 4-6 4V8z" />
                </svg>
                <p style={{ fontSize: 14, opacity: 0.7 }}>Video preview will appear here</p>
              </div>
            )}
          </div>

          {/* Error display */}
          {error && (
            <div style={{
              background: 'rgba(251,113,133,0.12)',
              border: '1px solid rgba(251,113,133,0.3)',
              borderRadius: 8,
              padding: '10px 14px',
              fontSize: 13,
              color: 'var(--accent-3)',
            }}>
              {error}
            </div>
          )}

          {/* Pipeline info */}
          <div style={{
            background: 'var(--surface)',
            border: '1px solid var(--border)',
            borderRadius: 12,
            padding: 16,
          }}>
            <p style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-2)', marginBottom: 8 }}>
              Pipeline Stages
            </p>
            {PIPELINE_STAGES[renderMode].map((stage, i) => {
              const active = jobStatus && jobStatus.progress >= parseInt(stage.range);
              return (
                <div
                  key={i}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 10,
                    padding: '6px 0',
                    opacity: active ? 1 : 0.4,
                    transition: 'opacity 0.3s',
                  }}
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
                    stroke={active ? 'var(--accent-1)' : 'var(--text-2)'} strokeWidth="2">
                    <path d={stage.icon} />
                  </svg>
                  <span style={{ fontSize: 12, color: 'var(--text-1)', flex: 1 }}>{stage.label}</span>
                  <span style={{ fontSize: 11, color: 'var(--text-2)', fontFamily: 'var(--font-jetbrains-mono)' }}>
                    {stage.range}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Spinner keyframe */}
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}
