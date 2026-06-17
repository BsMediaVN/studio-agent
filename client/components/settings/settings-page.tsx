'use client';

import { useState, useEffect, useRef } from 'react';
import { useSettings } from '@/providers/settings-provider';
import { api } from '@/lib/api-client';
import type { ClonedVoice, StatusResponse } from '@/lib/types';

export function SettingsPage() {
  const { settings, updateSetting, resetSettings } = useSettings();

  // Voice cloning state
  const [cloneName, setCloneName] = useState('');
  const [cloneText, setCloneText] = useState('');
  const [cloneFile, setCloneFile] = useState<File | null>(null);
  const [cloning, setCloning] = useState(false);
  const [cloneMsg, setCloneMsg] = useState<{ type: 'ok' | 'err'; text: string } | null>(null);
  const [customVoices, setCustomVoices] = useState<ClonedVoice[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Engine info state
  const [engineInfo, setEngineInfo] = useState<StatusResponse | null>(null);

  useEffect(() => {
    api.listClonedVoices()
      .then((d) => setCustomVoices(d.custom_voices ?? []))
      .catch(() => {});

    api.getStatus()
      .then(setEngineInfo)
      .catch(() => {});
  }, []);

  const handleClone = async () => {
    if (!cloneFile || !cloneName.trim()) return;
    setCloning(true);
    setCloneMsg(null);
    try {
      const data = await api.cloneVoice(cloneFile, cloneName.trim(), cloneText);
      setCloneMsg({ type: 'ok', text: data.message });
      setCloneName('');
      setCloneText('');
      setCloneFile(null);
      if (fileInputRef.current) fileInputRef.current.value = '';
      const lr = await api.listClonedVoices();
      setCustomVoices(lr.custom_voices ?? []);
    } catch (e) {
      setCloneMsg({ type: 'err', text: (e as Error).message });
    } finally {
      setCloning(false);
    }
  };

  const handleDeleteVoice = async (id: string) => {
    try {
      await api.deleteClonedVoice(id);
      setCustomVoices((prev) => prev.filter((v) => v.id !== id));
    } catch {
      // ignore
    }
  };

  return (
    <div className="space-y-6">
      <div className="grid gap-6 lg:grid-cols-2">
        {/* Voice Quality */}
        <div className="panel-card space-y-5">
          <label className="label-text">Voice Quality</label>

          <SliderField
            label="Temperature"
            value={settings.temperature}
            min={0.1}
            max={1.5}
            step={0.1}
            display={(v) => v.toFixed(1)}
            onChange={(v) => updateSetting('temperature', v)}
            hint="Lower = stable, consistent. Higher = expressive, varied."
          />

          <SliderField
            label="Top-K"
            value={settings.topK}
            min={10}
            max={100}
            step={5}
            display={(v) => String(v)}
            onChange={(v) => updateSetting('topK', v)}
            hint="Controls token diversity. Lower = more focused pronunciation."
          />
        </div>

        {/* LLM Configuration */}
        <div className="panel-card space-y-5">
          <label className="label-text">LLM Configuration</label>

          <div className="space-y-3">
            <label className="text-sm text-muted">Provider</label>
            <div className="flex gap-3">
              {(['claude', 'openai'] as const).map((p) => (
                <button
                  key={p}
                  onClick={() => updateSetting('llmProvider', p)}
                  className={`px-4 py-2 rounded-xl text-sm font-semibold transition-all ${
                    settings.llmProvider === p
                      ? 'bg-primary-500/20 text-primary-400 border border-primary-500/30'
                      : 'text-muted border border-transparent hover:text-main hover:border-[var(--border)]'
                  }`}
                >
                  {p === 'claude' ? 'Claude' : 'OpenAI'}
                </button>
              ))}
            </div>
          </div>

          <div className="space-y-2">
            <label className="text-sm text-muted">Model Name</label>
            <input
              type="text"
              value={settings.llmModel}
              onChange={(e) => updateSetting('llmModel', e.target.value)}
              className="select-control"
              placeholder="claude-sonnet-4-20250514"
            />
          </div>

          <div className="space-y-2">
            <label className="text-sm text-muted">Max Characters per Script</label>
            <div className="flex items-center gap-3">
              {[2, 3, 4, 5, 6, 7, 8, 9, 10].map((n) => (
                <button
                  key={n}
                  onClick={() => updateSetting('maxCharacters', n)}
                  className={`w-10 h-10 rounded-xl text-sm font-bold transition-all ${
                    settings.maxCharacters === n
                      ? 'bg-primary-500/20 text-primary-400 border border-primary-500/30'
                      : 'text-muted border border-[var(--border)] hover:text-main'
                  }`}
                >
                  {n}
                </button>
              ))}
            </div>
            <p className="text-xs text-muted">Max number of speaking characters in generated scripts.</p>
          </div>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Audio Output */}
        <div className="panel-card space-y-5">
          <label className="label-text">Audio Output</label>

          <div className="space-y-3">
            <label className="text-sm text-muted">Format</label>
            <div className="flex gap-3">
              {(['wav', 'mp3'] as const).map((f) => (
                <button
                  key={f}
                  onClick={() => updateSetting('outputFormat', f)}
                  className={`px-4 py-2 rounded-xl text-sm font-semibold uppercase transition-all ${
                    settings.outputFormat === f
                      ? 'bg-primary-500/20 text-primary-400 border border-primary-500/30'
                      : 'text-muted border border-transparent hover:text-main hover:border-[var(--border)]'
                  }`}
                >
                  {f}
                </button>
              ))}
            </div>
          </div>

          <div className="flex items-center justify-between">
            <label className="text-sm text-muted">Normalize Audio</label>
            <button
              onClick={() => updateSetting('normalize', !settings.normalize)}
              className={`w-12 h-6 rounded-full transition-all ${settings.normalize ? 'bg-primary-500' : 'bg-slate-700'}`}
            >
              <div
                className={`w-5 h-5 rounded-full bg-white shadow transition-transform ${
                  settings.normalize ? 'translate-x-6' : 'translate-x-0.5'
                }`}
              />
            </button>
          </div>

          <SliderField
            label="Silence Gap"
            value={settings.silenceGap}
            min={0}
            max={2}
            step={0.1}
            display={(v) => v.toFixed(1) + 's'}
            onChange={(v) => updateSetting('silenceGap', v)}
          />

          <SliderField
            label="Crossfade"
            value={settings.crossfade}
            min={0}
            max={1}
            step={0.05}
            display={(v) => v.toFixed(1) + 's'}
            onChange={(v) => updateSetting('crossfade', v)}
          />

          <div className={`space-y-2 ${settings.targetDuration ? 'opacity-50' : ''}`}>
            <SliderField
              label="Speed"
              value={settings.speed}
              min={0.5}
              max={2.0}
              step={0.1}
              display={(v) => v.toFixed(1) + 'x'}
              onChange={(v) => updateSetting('speed', v)}
              disabled={!!settings.targetDuration}
            />
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label className="text-sm text-muted">Target Duration</label>
              <span className="font-mono text-xs text-primary-400">
                {settings.targetDuration ? `${settings.targetDuration}s` : 'Auto'}
              </span>
            </div>
            <div className="flex gap-2">
              <input
                type="number"
                min={0.5}
                max={600}
                step={0.5}
                value={settings.targetDuration ?? ''}
                placeholder="Auto"
                onChange={(e) =>
                  updateSetting('targetDuration', e.target.value ? parseFloat(e.target.value) : null)
                }
                className="flex-1 select-control"
              />
              <button
                onClick={() => updateSetting('targetDuration', null)}
                className="px-3 py-1 text-xs btn-secondary"
                style={{ width: 'auto' }}
              >
                Clear
              </button>
            </div>
            <p className="text-xs text-muted">Set desired output length in seconds. Overrides speed when active.</p>
          </div>
        </div>

        {/* Voice Cloning */}
        <div className="panel-card space-y-5">
          <label className="label-text">Voice Cloning</label>
          <p className="text-xs text-muted">
            Upload 3-5 second WAV recording + exact transcript to clone a voice.
          </p>

          <div className="space-y-3">
            <input
              type="text"
              value={cloneName}
              onChange={(e) => setCloneName(e.target.value)}
              className="select-control"
              placeholder="Voice name (e.g. my_voice)"
            />
            <input
              ref={fileInputRef}
              type="file"
              accept=".wav,.mp3,.flac,.ogg"
              onChange={(e) => setCloneFile(e.target.files?.[0] ?? null)}
              className="select-control"
            />
            <textarea
              value={cloneText}
              onChange={(e) => setCloneText(e.target.value)}
              className="select-control"
              placeholder="Exact text spoken in the audio..."
              style={{ minHeight: '60px', resize: 'vertical' }}
            />
            <button
              onClick={handleClone}
              disabled={cloning || !cloneFile || !cloneName.trim()}
              className="btn-primary"
            >
              {cloning ? 'Cloning...' : 'Clone Voice'}
            </button>
            {cloneMsg && (
              <p className={`text-xs ${cloneMsg.type === 'ok' ? 'text-green-400' : 'text-red-400'}`}>
                {cloneMsg.text}
              </p>
            )}
          </div>

          {customVoices.length > 0 && (
            <div className="space-y-2">
              <label className="text-xs text-muted uppercase tracking-wider">Custom Voices</label>
              {customVoices.map((v) => (
                <div
                  key={v.id}
                  className="flex items-center justify-between py-2 border-b border-[var(--border)]"
                >
                  <span className="text-sm text-main">{v.id}</span>
                  <button
                    onClick={() => handleDeleteVoice(v.id)}
                    className="px-2 py-1 text-xs text-red-400 border border-red-500/30 rounded-lg hover:bg-red-500/10"
                  >
                    Delete
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Engine Info + Reset */}
      <div className="grid gap-6 lg:grid-cols-2">
        {engineInfo && (
          <div className="panel-card space-y-3">
            <label className="label-text">Engine Status</label>
            <div className="space-y-2 text-sm">
              <InfoRow label="Engine Loaded" value={engineInfo.engine_loaded ? 'Yes' : 'No'} />
              <InfoRow label="Voices Cached" value={String(engineInfo.voices_cached)} />
              <InfoRow label="Sample Rate" value={`${engineInfo.sample_rate} Hz`} />
              <InfoRow label="FFmpeg" value={engineInfo.ffmpeg_available ? 'Available' : 'Not found'} />
            </div>
          </div>
        )}

        <div className="panel-card space-y-3 flex flex-col justify-between">
          <div>
            <label className="label-text">Reset</label>
            <p className="text-xs text-muted mt-1">Restore all settings to their default values.</p>
          </div>
          <button onClick={resetSettings} className="btn-secondary" style={{ width: 'auto', alignSelf: 'flex-start' }}>
            Reset to Defaults
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Helper sub-components
// ---------------------------------------------------------------------------

interface SliderFieldProps {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  display: (v: number) => string;
  onChange: (v: number) => void;
  hint?: string;
  disabled?: boolean;
}

function SliderField({ label, value, min, max, step, display, onChange, hint, disabled }: SliderFieldProps) {
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <label className="text-sm text-muted">{label}</label>
        <span className="font-mono text-xs text-primary-400">{display(value)}</span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        className="w-full accent-primary-400"
      />
      {hint && <p className="text-xs text-muted">{hint}</p>}
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-muted">{label}</span>
      <span className="font-mono text-primary-400">{value}</span>
    </div>
  );
}
