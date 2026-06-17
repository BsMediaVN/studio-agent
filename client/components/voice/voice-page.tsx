'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import dynamic from 'next/dynamic';
import { API_URL, SAMPLE_RATE, SEGMENT_CHAR_SIZE } from '@/lib/constants';

const Visualizer = dynamic(
  () => import('@/components/audio/visualizer').then((m) => m.Visualizer),
  { ssr: false },
);

type StreamStatus = 'idle' | 'connecting' | 'playing' | 'completed' | 'error';

interface VoiceOption {
  id: string;
  name: string;
}

interface ModelOption {
  key: string;
  name: string;
  active?: boolean;
}

const STATUS_LABEL: Record<StreamStatus, string> = {
  idle: 'READY',
  connecting: 'BUFFERING',
  playing: 'STREAMING',
  completed: 'COMPLETED',
  error: 'ERROR',
};

const STATUS_CLASS: Record<StreamStatus, string> = {
  idle: '',
  connecting: 'status-connecting',
  playing: 'status-playing',
  completed: 'status-completed',
  error: 'status-error',
};

export function VoicePage() {
  const [text, setText] = useState('');
  const [urlInput, setUrlInput] = useState('');
  const [inputMode, setInputMode] = useState<'text' | 'url'>('text');
  const [voices, setVoices] = useState<VoiceOption[]>([]);
  const [selectedVoice, setSelectedVoice] = useState('');
  const [models, setModels] = useState<ModelOption[]>([]);
  const [currentModel, setCurrentModel] = useState<string | null>(null);
  const [isModelLoading, setIsModelLoading] = useState(false);
  const [status, setStatus] = useState<StreamStatus>('idle');
  const [latencyMs, setLatencyMs] = useState<number | null>(null);
  const [audioBlob, setAudioBlob] = useState<Blob | null>(null);
  const [analyserNode, setAnalyserNode] = useState<AnalyserNode | null>(null);
  const [isExtracting, setIsExtracting] = useState(false);
  const [extractionMeta, setExtractionMeta] = useState<{
    title?: string;
    charCount: number;
    truncated: boolean;
  } | null>(null);

  const ctxRef = useRef<AudioContext | null>(null);
  const isPlayingRef = useRef(false);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const chunksRef = useRef<Uint8Array[]>([]);

  const fetchVoices = useCallback(async (currentSelected?: string) => {
    try {
      const res = await fetch(`${API_URL}/voices`);
      const data: VoiceOption[] = await res.json();
      setVoices(data);
      if (data.length > 0 && !data.find((v) => v.id === currentSelected)) {
        setSelectedVoice(data[0].id);
      }
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    fetchVoices();
    fetch(`${API_URL}/models`)
      .then((r) => r.json())
      .then((data: ModelOption[]) => {
        setModels(data);
        const active = data.find((m) => m.active);
        if (active) setCurrentModel(active.key);
      })
      .catch(() => {});
  }, [fetchVoices]);

  const handleModelChange = async (key: string) => {
    if (key === currentModel) return;
    setIsModelLoading(true);
    try {
      const res = await fetch(`${API_URL}/set_model`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model_key: key }),
      });
      const data = await res.json();
      if (data.status === 'ok') {
        setCurrentModel(key);
        await fetchVoices(selectedVoice);
      } else {
        alert('Error switching model: ' + data.message);
      }
    } catch {
      alert('Network error switching model');
    } finally {
      setIsModelLoading(false);
    }
  };

  const buildWav = (): Blob => {
    let totalLength = 0;
    for (const chunk of chunksRef.current) totalLength += chunk.length;
    const buffer = new ArrayBuffer(44 + totalLength);
    const view = new DataView(buffer);
    const writeStr = (off: number, s: string) => {
      for (let i = 0; i < s.length; i++) view.setUint8(off + i, s.charCodeAt(i));
    };
    writeStr(0, 'RIFF');
    view.setUint32(4, 36 + totalLength, true);
    writeStr(8, 'WAVE');
    writeStr(12, 'fmt ');
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true);
    view.setUint16(22, 1, true);
    view.setUint32(24, SAMPLE_RATE, true);
    view.setUint32(28, SAMPLE_RATE * 2, true);
    view.setUint16(32, 2, true);
    view.setUint16(34, 16, true);
    writeStr(36, 'data');
    view.setUint32(40, totalLength, true);
    let offset = 44;
    const bytes = new Uint8Array(buffer);
    for (const chunk of chunksRef.current) {
      bytes.set(chunk, offset);
      offset += chunk.length;
    }
    return new Blob([buffer], { type: 'audio/wav' });
  };

  const handleStop = useCallback(() => {
    isPlayingRef.current = false;
    abortRef.current?.abort();
    abortRef.current = null;
    ctxRef.current?.close();
    ctxRef.current = null;
    analyserRef.current = null;
    setAnalyserNode(null);
    setStatus('idle');
  }, []);

  const handleGenerate = async () => {
    if (!text.trim()) return;
    handleStop();
    setStatus('connecting');
    const startTime = Date.now();
    setLatencyMs(null);
    setAudioBlob(null);
    chunksRef.current = [];
    isPlayingRef.current = true;
    abortRef.current = new AbortController();
    const signal = abortRef.current.signal;

    const AudioContextClass =
      (window as unknown as { AudioContext: typeof AudioContext; webkitAudioContext?: typeof AudioContext })
        .AudioContext ??
      (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    const ctx = new AudioContextClass({ sampleRate: SAMPLE_RATE });
    ctxRef.current = ctx;
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 256;
    analyserRef.current = analyser;
    setAnalyserNode(analyser);
    analyser.connect(ctx.destination);

    try {
      let response: Response;
      if (text.length > 2000) {
        response = await fetch(`${API_URL}/stream`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text, voice_id: selectedVoice || undefined }),
          signal,
        });
      } else {
        const encoded = encodeURIComponent(text);
        const voiceParam = selectedVoice ? `&voice_id=${selectedVoice}` : '';
        response = await fetch(`${API_URL}/stream?text=${encoded}${voiceParam}`, { signal });
      }

      if (!response.body) return;
      const reader = response.body.getReader();
      let nextTime = ctx.currentTime + 0.1;
      let headerSkipped = false;
      let firstChunkPlayed = false;

      try {
        while (isPlayingRef.current) {
          const { done, value } = await reader.read();
          if (done || !isPlayingRef.current || !ctxRef.current) break;

          let audioData = value;
          if (!headerSkipped) {
            if (audioData.length > 44) {
              audioData = audioData.slice(44);
              headerSkipped = true;
            } else {
              continue;
            }
          }

          chunksRef.current.push(audioData);
          const int16 = new Int16Array(audioData.buffer, audioData.byteOffset, audioData.byteLength / 2);
          const float32 = new Float32Array(int16.length);
          for (let i = 0; i < int16.length; i++) float32[i] = int16[i] / 32768.0;

          const buf = ctx.createBuffer(1, float32.length, SAMPLE_RATE);
          buf.getChannelData(0).set(float32);
          const source = ctx.createBufferSource();
          source.buffer = buf;
          source.connect(analyser);
          if (nextTime < ctx.currentTime) nextTime = ctx.currentTime;
          source.start(nextTime);
          nextTime += buf.duration;

          if (!firstChunkPlayed) {
            setLatencyMs(Date.now() - startTime);
            setStatus('playing');
            firstChunkPlayed = true;
          }
        }
      } catch (err) {
        if ((err as Error).name !== 'AbortError') throw err;
      }

      if (isPlayingRef.current) {
        const remaining = nextTime - ctx.currentTime;
        if (remaining > 0) await new Promise((r) => setTimeout(r, remaining * 1000));
        if (isPlayingRef.current) {
          setStatus('completed');
          setAudioBlob(buildWav());
          setTimeout(() => setStatus('idle'), 2000);
        }
      }
    } catch (e) {
      if ((e as Error).name !== 'AbortError') {
        console.error('Stream error', e);
        setStatus('error');
      }
    }
  };

  const handleExtractUrl = async () => {
    if (!urlInput.trim()) return;
    setIsExtracting(true);
    setExtractionMeta(null);
    try {
      const res = await fetch(`${API_URL}/extract_url`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: urlInput.trim(), max_chars: 5000 }),
      });
      const data = await res.json();
      if (data.status === 'ok') {
        setText(data.text);
        setExtractionMeta({ title: data.title, charCount: data.char_count, truncated: data.truncated });
        setInputMode('text');
      } else {
        alert('Extraction failed: ' + data.message);
      }
    } catch {
      alert('Network error extracting URL');
    } finally {
      setIsExtracting(false);
    }
  };

  const handleDownload = () => {
    if (!audioBlob) return;
    const url = URL.createObjectURL(audioBlob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `vieneu_tts_${Date.now()}.wav`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const charCount = text.length;
  const segmentEstimate = Math.max(1, Math.ceil(charCount / SEGMENT_CHAR_SIZE));
  const isActive = status === 'connecting' || status === 'playing';

  return (
    <div className="space-y-4">
      {isModelLoading && (
        <div className="fixed inset-0 bg-slate-900/80 z-50 flex flex-col items-center justify-center space-y-3 backdrop-blur-sm">
          <div className="h-10 w-10 rounded-full border-4 border-primary-400 border-t-transparent animate-spin" />
          <span className="text-primary-400 font-semibold animate-pulse">Switching Model...</span>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[1.35fr_0.65fr]">
        {/* Left: text input */}
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              {(['text', 'url'] as const).map((mode) => (
                <button
                  key={mode}
                  onClick={() => setInputMode(mode)}
                  className={`px-3 py-1 rounded-lg text-sm font-medium transition-all ${
                    inputMode === mode
                      ? 'bg-primary-500/20 text-primary-400 border border-primary-500/30'
                      : 'text-muted hover:text-main'
                  }`}
                >
                  {mode === 'text' ? 'Text' : 'URL'}
                </button>
              ))}
            </div>
            <span className="text-xs text-muted">{charCount} chars</span>
          </div>

          {inputMode === 'url' && (
            <div className="space-y-3">
              <div className="input-frame">
                <input
                  type="url"
                  value={urlInput}
                  onChange={(e) => setUrlInput(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleExtractUrl()}
                  placeholder="https://example.com/article..."
                  className="input-area"
                  style={{ minHeight: 'auto', height: '48px', resize: 'none' }}
                  disabled={isExtracting}
                />
              </div>
              <button
                onClick={handleExtractUrl}
                disabled={isExtracting || !urlInput.trim()}
                className="btn-primary"
              >
                {isExtracting ? 'Extracting...' : 'Extract Text'}
              </button>
            </div>
          )}

          {inputMode === 'text' && (
            <div className="space-y-2">
              {extractionMeta && (
                <div className="flex flex-wrap items-center gap-2 text-xs">
                  {extractionMeta.title && (
                    <span className="chip">
                      {extractionMeta.title.length > 50
                        ? extractionMeta.title.slice(0, 50) + '...'
                        : extractionMeta.title}
                    </span>
                  )}
                  <span className="chip">{extractionMeta.charCount} chars</span>
                  {extractionMeta.truncated && <span className="chip chip-warn">Truncated</span>}
                </div>
              )}
              <div className="input-frame">
                <textarea
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  placeholder="Enter text to synthesize..."
                  className="input-area"
                  spellCheck={false}
                />
              </div>
            </div>
          )}

          <div className="flex items-center justify-between text-xs text-muted">
            <span>
              {inputMode === 'url'
                ? 'Paste an article URL to extract text for TTS.'
                : 'Tip: punctuation helps natural pauses.'}
            </span>
            <span className="font-mono">~{segmentEstimate} segments</span>
          </div>
        </div>

        {/* Right: controls */}
        <div className="space-y-4">
          {/* Model selector */}
          <div className="panel-card space-y-3">
            <div className="flex items-center justify-between">
              <label className="label-text">Model</label>
              <span className="chip chip-warn">CPU Demo</span>
            </div>
            <select
              className="select-control"
              value={currentModel || ''}
              onChange={(e) => handleModelChange(e.target.value)}
              disabled={isActive}
            >
              {models.map((m) => (
                <option key={m.key} value={m.key}>
                  {m.name}
                </option>
              ))}
            </select>
            <p className="text-xs text-muted">Streaming demo optimized for CPU GGUF models.</p>
          </div>

          {/* Voice selector */}
          <div className="panel-card space-y-3">
            <label className="label-text">Voice</label>
            <select
              className="select-control"
              value={selectedVoice}
              onChange={(e) => setSelectedVoice(e.target.value)}
              disabled={isActive}
            >
              {voices.length === 0 && <option>Loading voices...</option>}
              {voices.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.name}
                </option>
              ))}
            </select>
          </div>

          {/* Visualizer */}
          <Visualizer isPlaying={status === 'playing'} analyserNode={analyserNode} />

          {/* Controls */}
          <div className="panel-card space-y-4">
            {isActive ? (
              <button onClick={handleStop} className="btn-stop">
                Stop Stream
              </button>
            ) : (
              <button
                onClick={handleGenerate}
                disabled={status !== 'idle' && status !== 'completed'}
                className="btn-primary"
              >
                Generate Stream
              </button>
            )}

            <div className="flex items-center justify-between">
              <div className={`status-chip ${STATUS_CLASS[status]}`}>
                <span className="status-dot" />
                <span className="font-mono">{STATUS_LABEL[status]}</span>
              </div>
              {latencyMs !== null && (
                <span className="text-[11px] font-mono text-muted">
                  Head Latency:{' '}
                  <span className="text-emerald-300">{latencyMs}ms</span>
                </span>
              )}
            </div>

            {audioBlob && !isActive && (
              <button onClick={handleDownload} className="btn-secondary">
                Download WAV
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
