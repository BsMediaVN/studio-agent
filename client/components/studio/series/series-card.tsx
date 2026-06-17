'use client';

import { useState } from 'react';
import { EpisodeEditor } from './episode-editor';
import { api } from '@/lib/api-client';
import type { Series, Episode, VoiceInfo } from '@/lib/types';

interface SeriesCardProps {
  series: Series;
  expanded: boolean;
  onToggle: () => void;
  continuing: boolean;
  merging: boolean;
  continueHint: string;
  setContinueHint: (v: string) => void;
  voices: VoiceInfo[];
  onContinue: () => void;
  onMerge: () => void;
  onDelete: () => void;
  onExport: () => void;
  onUpdate: (sid: string, updates: Record<string, unknown>) => void;
}

function fmtDur(s: number): string {
  return `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
}

function parseEpisodeLines(ep: Episode): string {
  const lines: string[] = [];
  const data = ep.script_data as { scenes?: { dialogue?: { character: string; text: string }[] }[] };
  if (data?.scenes) {
    data.scenes.forEach((scene) => {
      scene.dialogue?.forEach((d) => {
        lines.push(`[${d.character}] ${d.text}`);
      });
    });
  }
  return lines.join('\n');
}

export function SeriesCard({
  series,
  expanded,
  onToggle,
  continuing,
  merging,
  continueHint,
  setContinueHint,
  voices,
  onContinue,
  onMerge,
  onDelete,
  onExport,
  onUpdate,
}: SeriesCardProps) {
  const [showSettings, setShowSettings] = useState(false);
  const [editingEp, setEditingEp] = useState<number | null>(null);
  const [editScript, setEditScript] = useState('');
  const [producingEp, setProducingEp] = useState<number | null>(null);

  const totalDuration = series.episodes.reduce((sum, e) => sum + (e.duration_s ?? 0), 0);

  const startEdit = (ep: Episode) => {
    if (editingEp === ep.episode_num) {
      setEditingEp(null);
      return;
    }
    setEditScript(parseEpisodeLines(ep));
    setEditingEp(ep.episode_num);
  };

  const handleReproduced = () => {
    setEditingEp(null);
    onUpdate(series.id, {});
  };

  const handleVoiceChange = (charName: string, voiceId: string) => {
    const newMap = { ...series.voice_map, [charName]: voiceId };
    onUpdate(series.id, { voice_map: newMap });
  };

  const downloadEpisodeUrl = (ep: Episode) =>
    api.downloadEpisodeUrl(series.id, ep.episode_num);

  return (
    <div
      className="panel-card"
      style={{
        borderLeft: '3px solid var(--accent-1)',
        background: 'rgba(12,19,33,0.6)',
        backdropFilter: 'blur(12px)',
      }}
    >
      {/* Header */}
      <div
        className="flex items-center justify-between cursor-pointer"
        onClick={onToggle}
      >
        <div>
          <h4 className="font-semibold" style={{ color: 'var(--text-1)' }}>
            {series.title}
          </h4>
          <div className="flex gap-2 mt-1 flex-wrap">
            <span className="chip">{series.episodes.length} eps</span>
            <span className="chip">{fmtDur(totalDuration)}</span>
            <span className="chip">{series.mode}</span>
            {series.speed !== 1.0 && <span className="chip">{series.speed}x</span>}
          </div>
        </div>
        <svg
          width="20"
          height="20"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          className={`transition-transform ${expanded ? 'rotate-180' : ''}`}
          style={{ color: 'var(--text-2)' }}
        >
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </div>

      {expanded && (
        <div className="mt-4 space-y-3">
          {/* Voice Assignment */}
          {series.characters && series.characters.length > 0 && (
            <div
              className="p-3 rounded-xl space-y-2"
              style={{ background: 'var(--surface-2)', border: '1px solid var(--border)' }}
            >
              <span
                className="text-xs font-semibold"
                style={{
                  color: 'var(--text-2)',
                  textTransform: 'uppercase',
                  letterSpacing: '0.05em',
                  display: 'block',
                }}
              >
                Voice Assignment
              </span>
              {series.characters.map((c) => (
                <div key={c.name} className="flex items-center gap-2">
                  <span
                    className="text-sm flex-shrink-0 w-24 truncate"
                    style={{ color: 'var(--text-1)' }}
                  >
                    {c.name}{' '}
                    <span style={{ color: 'var(--text-2)', fontSize: '0.7rem' }}>
                      ({c.gender ?? '?'})
                    </span>
                  </span>
                  <select
                    value={series.voice_map[c.name] ?? ''}
                    onChange={(e) => handleVoiceChange(c.name, e.target.value)}
                    style={{
                      flex: 1,
                      padding: '0.35rem 0.5rem',
                      borderRadius: '0.5rem',
                      background: 'var(--bg-1)',
                      border: '1px solid var(--border)',
                      color: 'var(--text-1)',
                      fontSize: '0.8rem',
                    }}
                  >
                    <option value="">Auto</option>
                    {voices.map((v) => (
                      <option key={v.id} value={v.id}>
                        {v.id} ({v.name || v.id})
                      </option>
                    ))}
                  </select>
                </div>
              ))}
            </div>
          )}

          {/* Settings toggle */}
          <button
            className="text-xs flex items-center gap-1"
            onClick={() => setShowSettings(!showSettings)}
            style={{
              color: 'var(--text-2)',
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              padding: 0,
            }}
          >
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <circle cx="12" cy="12" r="3" />
              <path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42" />
            </svg>
            {showSettings ? 'Hide Settings' : 'Settings'}
          </button>

          {showSettings && (
            <div
              className="p-3 rounded-xl space-y-3"
              style={{ background: 'var(--surface-2)', border: '1px solid var(--border)' }}
            >
              <div className="space-y-1">
                <div className="flex items-center justify-between">
                  <label className="text-xs" style={{ color: 'var(--text-2)' }}>
                    Speed
                  </label>
                  <span
                    className="font-mono text-xs"
                    style={{ color: 'var(--accent-1)' }}
                  >
                    {(series.speed ?? 1.0).toFixed(1)}x
                  </span>
                </div>
                <input
                  type="range"
                  min="0.5"
                  max="2.0"
                  step="0.1"
                  value={series.speed ?? 1.0}
                  onChange={(e) =>
                    onUpdate(series.id, { speed: parseFloat(e.target.value) })
                  }
                  className="w-full"
                  style={{ height: '4px', accentColor: 'var(--accent-1)' }}
                />
              </div>
              <div className="space-y-1">
                <div className="flex items-center justify-between">
                  <label className="text-xs" style={{ color: 'var(--text-2)' }}>
                    Temperature
                  </label>
                  <span
                    className="font-mono text-xs"
                    style={{ color: 'var(--accent-1)' }}
                  >
                    {(series.temperature ?? 0.8).toFixed(1)}
                  </span>
                </div>
                <input
                  type="range"
                  min="0.1"
                  max="1.5"
                  step="0.1"
                  value={series.temperature ?? 0.8}
                  onChange={(e) =>
                    onUpdate(series.id, { temperature: parseFloat(e.target.value) })
                  }
                  className="w-full"
                  style={{ height: '4px', accentColor: 'var(--accent-1)' }}
                />
              </div>
            </div>
          )}

          {/* Episode List */}
          <div className="space-y-2 max-h-72 overflow-y-auto">
            {series.episodes.length === 0 ? (
              <p
                className="text-xs text-center py-4"
                style={{ color: 'var(--text-2)' }}
              >
                No episodes yet. Click &quot;Continue Story&quot; to generate the first one.
              </p>
            ) : (
              series.episodes.map((ep) => (
                <div
                  key={ep.episode_num}
                  className="rounded-xl overflow-hidden"
                  style={{ background: 'var(--surface-2)', border: '1px solid var(--border)' }}
                >
                  {/* Episode header */}
                  <div
                    className="flex items-center justify-between p-3 cursor-pointer"
                    onClick={() => startEdit(ep)}
                  >
                    <div className="flex items-center gap-2">
                      <span
                        className="text-sm font-semibold"
                        style={{ color: 'var(--text-1)' }}
                      >
                        Ep {ep.episode_num}
                      </span>
                      <span className="text-sm" style={{ color: 'var(--text-2)' }}>
                        {ep.title ?? 'Untitled'}
                      </span>
                    </div>
                    <div className="flex items-center gap-3">
                      <span
                        className="text-xs font-mono"
                        style={{ color: 'var(--text-2)' }}
                      >
                        {fmtDur(ep.duration_s ?? 0)}
                      </span>
                      <span
                        className="text-xs font-medium"
                        style={{ color: 'var(--accent-1)' }}
                      >
                        {editingEp === ep.episode_num ? 'Close' : 'Edit'}
                      </span>
                    </div>
                  </div>

                  {/* Summary */}
                  {editingEp !== ep.episode_num && ep.summary && (
                    <div className="px-3 pb-2">
                      <p
                        className="text-xs"
                        style={{
                          color: 'var(--text-2)',
                          overflow: 'hidden',
                          display: '-webkit-box',
                          WebkitLineClamp: 2,
                          WebkitBoxOrient: 'vertical',
                        }}
                      >
                        {ep.summary}
                      </p>
                    </div>
                  )}

                  {/* Audio player or Produce button */}
                  {ep.audio_path ? (
                    <div className="px-3 pb-3">
                      <audio
                        controls
                        preload="none"
                        className="w-full"
                        style={{ height: '36px', borderRadius: '8px' }}
                        src={downloadEpisodeUrl(ep)}
                      />
                    </div>
                  ) : ep.script_data && (
                    <div className="px-3 pb-3">
                      <button
                        className="btn-primary w-full text-sm"
                        disabled={producingEp === ep.episode_num}
                        onClick={async (e) => {
                          e.stopPropagation();
                          setProducingEp(ep.episode_num);
                          try {
                            await api.reproduceEpisode(series.id, ep.episode_num, { script_data: ep.script_data });
                            onUpdate(series.id, {});
                          } catch (err) {
                            alert(err instanceof Error ? err.message : 'Produce failed');
                          }
                          setProducingEp(null);
                        }}
                      >
                        {producingEp === ep.episode_num ? 'Producing...' : 'Produce Audio'}
                      </button>
                    </div>
                  )}

                  {/* Script editor */}
                  {editingEp === ep.episode_num && (
                    <EpisodeEditor
                      seriesId={series.id}
                      episode={ep}
                      editScript={editScript}
                      onEditScriptChange={setEditScript}
                      onReproduced={handleReproduced}
                    />
                  )}
                </div>
              ))
            )}
          </div>

          {/* Continue hint */}
          <input
            placeholder="Optional hint for next episode... e.g. 'Lan discovers the secret'"
            value={continueHint}
            onChange={(e) => setContinueHint(e.target.value)}
            className="input-area w-full"
            style={{ minHeight: '36px', height: '36px', fontSize: '0.8rem' }}
          />

          {/* Action buttons */}
          <div className="flex gap-2 flex-wrap">
            <button
              className="btn-primary flex-1"
              onClick={onContinue}
              disabled={continuing}
            >
              {continuing ? 'Generating...' : 'Continue Story'}
            </button>
            <button
              className="btn-secondary flex-1"
              onClick={onMerge}
              disabled={merging || series.episodes.length < 2}
            >
              {merging ? 'Merging...' : 'Merge All'}
            </button>
            <button
              className="btn-secondary"
              onClick={onExport}
              style={{ flex: 'none', padding: '0.5rem 0.75rem' }}
              title="Export series backup"
            >
              <svg
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
              >
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                <polyline points="7 10 12 15 17 10" />
                <line x1="12" y1="15" x2="12" y2="3" />
              </svg>
            </button>
            <button
              className="btn-stop"
              onClick={onDelete}
              style={{ width: 'auto', flex: 'none', padding: '0.5rem 0.75rem' }}
            >
              Delete
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
