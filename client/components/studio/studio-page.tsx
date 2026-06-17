'use client';

import { useState, useEffect, useCallback } from 'react';
import { ModeToggle } from './mode-toggle';
import { PromptInput } from './prompt-input';
import { ScriptViewer } from './script-viewer';
import { VoiceAssignment } from './voice-assignment';
import { ProducePanel } from './produce-panel';
import { AudioPlayer } from './audio-player';
import { SeriesSection } from './series/series-section';
import { CharacterSetup } from './character-setup';
import { api } from '@/lib/api-client';
import { useJobProgress } from '@/lib/hooks/use-websocket';
import type { Script, ScriptMode, StoryGenre, StoryType, VoiceInfo, ScriptCharacter, CharacterPreset } from '@/lib/types';

type CharacterMode = 'auto' | 'manual';

interface Settings {
  maxCharacters: number;
  outputFormat: 'wav' | 'mp3';
  normalize: boolean;
  silenceGap: number;
  crossfade: number;
  speed: number;
  temperature: number;
  topK: number;
  targetDuration: number | null;
}

const DEFAULT_SETTINGS: Settings = {
  maxCharacters: 4,
  outputFormat: 'wav',
  normalize: true,
  silenceGap: 0.3,
  crossfade: 0.0,
  speed: 1.0,
  temperature: 0.8,
  topK: 50,
  targetDuration: null,
};

const DURATION_PRESETS: { label: string; value: number | null }[] = [
  { label: 'Auto', value: null },
  { label: '30s', value: 30 },
  { label: '1m', value: 60 },
  { label: '2m', value: 120 },
  { label: '5m', value: 300 },
];

const GENRE_OPTIONS: { value: StoryGenre; label: string }[] = [
  { value: '', label: 'Tự do' },
  { value: 'tâm lý', label: 'Tâm lý' },
  { value: 'lãng mạn', label: 'Lãng mạn' },
  { value: 'hài hước', label: 'Hài hước' },
  { value: 'kinh dị', label: 'Kinh dị' },
  { value: 'hành động', label: 'Hành động' },
  { value: 'trinh thám', label: 'Trinh thám' },
];

export function StudioPage() {
  const [mode, setMode] = useState<ScriptMode>('story');
  const [genre, setGenre] = useState<StoryGenre>('');
  const [storyType, setStoryType] = useState<StoryType>('oneshot');
  const [episodeCount, setEpisodeCount] = useState(3);
  const [prompt, setPrompt] = useState('');
  const [script, setScript] = useState<Script | null>(null);
  const [voiceMap, setVoiceMap] = useState<Record<string, string>>({});
  const [voices, setVoices] = useState<VoiceInfo[]>([]);
  const [isGenerating, setIsGenerating] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [settings, setSettings] = useState<Settings>(DEFAULT_SETTINGS);
  const [autoExpandSeriesId, setAutoExpandSeriesId] = useState<string | null>(null);
  const [characterMode, setCharacterMode] = useState<CharacterMode>('auto');
  const [presetCharacters, setPresetCharacters] = useState<CharacterPreset[]>([]);
  const [presetVoiceMap, setPresetVoiceMap] = useState<Record<string, string>>({});

  const { progress, error: wsError } = useJobProgress(jobId);

  useEffect(() => {
    api.getVoices().then((res) => setVoices(res.voices ?? [])).catch(() => {});
  }, []);

  useEffect(() => {
    if (!progress) return;
    if (progress.status === 'complete' && jobId) setAudioUrl(api.downloadUrl(jobId));
    if (progress.status === 'error') { setError(progress.error ?? 'Production failed'); setJobId(null); }
  }, [progress, jobId]);

  useEffect(() => { if (wsError) setError(wsError); }, [wsError]);

  const autoAssignVoices = useCallback(
    (characters: ScriptCharacter[]) => {
      if (!Array.isArray(characters) || characters.length === 0) return;
      const malePools = voices.filter((v) => ['Binh', 'Tuyen', 'Vinh'].includes(v.id));
      const femalePools = voices.filter((v) => ['Doan', 'Ly', 'Ngoc'].includes(v.id));
      let mi = 0, fi = 0;
      const map: Record<string, string> = {};
      characters.forEach((c) => {
        if (c.voice_id && voices.find((v) => v.id === c.voice_id)) { map[c.name] = c.voice_id; }
        else if (c.gender === 'M' && malePools.length > 0) { map[c.name] = malePools[mi++ % malePools.length].id; }
        else if (c.gender === 'F' && femalePools.length > 0) { map[c.name] = femalePools[fi++ % femalePools.length].id; }
        else if (voices.length > 0) { map[c.name] = voices[0].id; }
      });
      setVoiceMap(map);
    },
    [voices],
  );

  const handleGenerateScript = async () => {
    if (!prompt.trim()) return;
    setIsGenerating(true);
    setError(null);
    setScript(null);
    setAudioUrl(null);
    setJobId(null);
    setAutoExpandSeriesId(null);

    // Build characters param for manual mode (only valid entries with names)
    const validChars = characterMode === 'manual'
      ? presetCharacters.filter((c) => c.name.trim())
      : undefined;
    const charsParam = validChars && validChars.length > 0 ? validChars : undefined;

    try {
      if (storyType === 'multi') {
        const res = await api.batchGenerate({
          title: prompt.slice(0, 50),
          prompt,
          num_episodes: episodeCount,
          mode,
          ...(genre ? { genre } : {}),
          max_characters: settings.maxCharacters,
          ...(settings.targetDuration ? { target_duration_s: settings.targetDuration } : {}),
          ...(charsParam ? { characters: charsParam } : {}),
        });
        if (res.series) setAutoExpandSeriesId(res.series.id);
        if (res.status === 'partial' && res.error) {
          setError(`Tạo được ${res.series?.episodes?.length ?? 0}/${episodeCount} tập. Lỗi: ${res.error}`);
        }
      } else {
        const res = await api.generateScript({
          prompt,
          max_characters: settings.maxCharacters,
          language: 'vi',
          mode,
          ...(genre ? { genre } : {}),
          ...(settings.targetDuration ? { target_duration_s: settings.targetDuration } : {}),
          ...(charsParam ? { characters: charsParam } : {}),
        });
        if (res.script) {
          setScript(res.script);
          // Use preset voice map for manual characters, then auto-assign remaining
          if (charsParam && Object.keys(presetVoiceMap).length > 0) {
            // Start with preset map, auto-fill any missing characters
            const mergedMap = { ...presetVoiceMap };
            const malePools = voices.filter((v) => ['Binh', 'Tuyen', 'Vinh'].includes(v.id));
            const femalePools = voices.filter((v) => ['Doan', 'Ly', 'Ngoc'].includes(v.id));
            let mi = 0, fi = 0;
            res.script.characters.forEach((c) => {
              if (mergedMap[c.name]) return; // already assigned
              if (c.gender === 'M' && malePools.length > 0) { mergedMap[c.name] = malePools[mi++ % malePools.length].id; }
              else if (c.gender === 'F' && femalePools.length > 0) { mergedMap[c.name] = femalePools[fi++ % femalePools.length].id; }
              else if (voices.length > 0) { mergedMap[c.name] = voices[0].id; }
            });
            setVoiceMap(mergedMap);
          } else {
            autoAssignVoices(res.script.characters);
          }
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to generate script');
    } finally {
      setIsGenerating(false);
    }
  };

  const handleProduce = async () => {
    if (!script) return;
    setError(null);
    setAudioUrl(null);
    try {
      const res = await api.produce({
        script, voice_map: voiceMap,
        silence_gap: settings.silenceGap, crossfade: settings.crossfade,
        output_format: settings.outputFormat, normalize: settings.normalize,
        temperature: settings.temperature, top_k: settings.topK, speed: settings.speed,
      });
      setJobId(res.job_id);
    } catch (e) { setError(e instanceof Error ? e.message : 'Failed to start production'); }
  };

  const handleExportScript = () => {
    if (!script) return;
    const blob = new Blob([JSON.stringify({ script, voice_map: voiceMap }, null, 2)], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `script_${(script.title ?? 'untitled').replace(/[^a-zA-Z0-9]/g, '_').slice(0, 30)}.json`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  const isProducing = progress?.status === 'processing' || progress?.status === 'queued';

  const chipStyle = (active: boolean) => ({
    background: active
      ? 'linear-gradient(135deg, rgba(45,212,191,0.15), rgba(45,212,191,0.08))'
      : 'rgba(255,255,255,0.03)',
    border: `1px solid ${active ? 'rgba(45,212,191,0.4)' : 'rgba(255,255,255,0.08)'}`,
    color: active ? '#2dd4bf' : '#94a3b8',
    boxShadow: active ? '0 0 12px rgba(45,212,191,0.08)' : 'none',
  });

  return (
    <div className="space-y-5">
      {/* Mode Toggle */}
      <ModeToggle mode={mode} onChange={setMode} />

      {/* === Main Layout: Content (3/4) + Sidebar (1/4) === */}
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-5 items-start">
        {/* Left: Prompt + Results */}
        <div className="space-y-5 min-w-0">
          {/* Prompt Input */}
          <PromptInput
            value={prompt}
            onChange={setPrompt}
            onGenerate={handleGenerateScript}
            isGenerating={isGenerating}
            isDisabled={isProducing}
            mode={mode}
          />

          {/* Series Section (only for multi-episode or story mode) */}
          {(storyType === 'multi' || mode === 'story') && (
            <SeriesSection lastScript={script} lastVoiceMap={voiceMap} voices={voices} autoExpandId={autoExpandSeriesId} />
          )}

          {/* Error */}
          {error && (
            <div className="panel-card" style={{ borderColor: 'rgba(248,113,133,0.4)' }}>
              <p className="text-sm" style={{ color: '#fda4af' }}>{error}</p>
            </div>
          )}

          {/* Script + Voice + Produce */}
          {script && (
            <div className="grid gap-5 xl:grid-cols-[1fr_0.4fr]">
              <ScriptViewer script={script} />
              <div className="space-y-4">
                <VoiceAssignment script={script} voiceMap={voiceMap} voices={voices} onChange={setVoiceMap} />
                <ProducePanel
                  script={script} voiceMap={voiceMap} isProducing={isProducing} progress={progress}
                  onProduce={handleProduce} onExportScript={handleExportScript}
                />
              </div>
            </div>
          )}

          {/* Audio Player */}
          {audioUrl && (
            <AudioPlayer audioUrl={audioUrl} filename={`${script?.title ?? 'audio'}.${settings.outputFormat}`} />
          )}
        </div>

        {/* Right Sidebar: Options */}
        <div className="lg:sticky lg:top-20 space-y-4">
          {/* Story/Video Type */}
          <div className="panel-card space-y-3">
            <label className="label-text mb-0 block">Loại {mode === 'story' ? 'truyện' : 'video'}</label>
            <div className="flex gap-2">
              <button
                onClick={() => setStoryType('oneshot')}
                className="flex-1 px-3 py-2 rounded-lg text-xs font-semibold transition-all cursor-pointer"
                style={chipStyle(storyType === 'oneshot')}
              >
                1 tập
              </button>
              <button
                onClick={() => setStoryType('multi')}
                className="flex-1 px-3 py-2 rounded-lg text-xs font-semibold transition-all cursor-pointer"
                style={chipStyle(storyType === 'multi')}
              >
                Dài tập
              </button>
            </div>
            {storyType === 'multi' && (
              <div className="flex items-center gap-2">
                <label className="text-xs text-muted">Số tập</label>
                <input
                  type="number"
                  min={2}
                  max={20}
                  value={episodeCount}
                  onChange={(e) => setEpisodeCount(Math.max(2, Math.min(20, parseInt(e.target.value) || 3)))}
                  className="w-14 rounded-lg px-2 py-1.5 text-xs font-mono text-center"
                  style={{
                    background: 'rgba(255,255,255,0.04)',
                    border: '1px solid rgba(45,212,191,0.3)',
                    color: '#2dd4bf',
                    outline: 'none',
                  }}
                />
                <span className="text-xs text-muted">tập</span>
              </div>
            )}
          </div>

          {/* Character Setup */}
          <CharacterSetup
            mode={characterMode}
            onModeChange={setCharacterMode}
            characters={presetCharacters}
            onCharactersChange={setPresetCharacters}
            voiceMap={presetVoiceMap}
            onVoiceMapChange={setPresetVoiceMap}
            voices={voices}
            maxCharacters={settings.maxCharacters}
          />

          {/* Genre (story mode only) */}
          {mode === 'story' && (
            <div className="panel-card space-y-3">
              <label className="label-text mb-0 block">Thể loại</label>
              <div className="flex gap-1.5 flex-wrap">
                {GENRE_OPTIONS.map((g) => (
                  <button
                    key={g.value}
                    onClick={() => setGenre(g.value)}
                    className="px-2.5 py-1.5 rounded-lg text-xs font-medium transition-all cursor-pointer"
                    style={chipStyle(genre === g.value)}
                  >
                    {g.label}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Duration */}
          <div className="panel-card space-y-3">
            <div className="flex items-center justify-between">
              <label className="label-text mb-0">Thời lượng</label>
              {settings.targetDuration !== null && (
                <span
                  className="font-mono text-xs px-2 py-0.5 rounded-full"
                  style={{
                    background: 'linear-gradient(135deg, rgba(45,212,191,0.15), rgba(245,158,11,0.15))',
                    color: '#2dd4bf',
                    border: '1px solid rgba(45,212,191,0.3)',
                  }}
                >
                  {settings.targetDuration >= 60
                    ? `${Math.floor(settings.targetDuration / 60)}m ${Math.round(settings.targetDuration % 60)}s`
                    : `${settings.targetDuration}s`}
                </span>
              )}
            </div>
            <div className="flex gap-1.5 flex-wrap">
              {DURATION_PRESETS.map((p) => {
                const selected = settings.targetDuration === p.value || (!settings.targetDuration && p.value === null);
                return (
                  <button
                    key={p.label}
                    onClick={() => setSettings((s) => ({ ...s, targetDuration: p.value }))}
                    className="px-2.5 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer"
                    style={chipStyle(selected)}
                  >
                    {p.label}
                  </button>
                );
              })}
            </div>
            <div className="flex items-center gap-1.5">
              <input
                type="number"
                min="1"
                max="600"
                value={settings.targetDuration ?? ''}
                placeholder="Custom"
                onChange={(e) =>
                  setSettings((s) => ({
                    ...s,
                    targetDuration: e.target.value ? Math.max(1, Math.min(600, parseFloat(e.target.value))) : null,
                  }))
                }
                className="flex-1 px-2 py-1.5 rounded-lg text-xs font-mono text-center"
                style={{
                  background: 'rgba(255,255,255,0.04)',
                  border: '1px solid rgba(45,212,191,0.4)',
                  color: '#e2e8f0',
                  outline: 'none',
                }}
              />
              <span className="text-xs text-muted">sec</span>
            </div>
          </div>
        </div>
      </div>

    </div>
  );
}
