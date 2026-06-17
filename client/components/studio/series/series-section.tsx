'use client';

import { useState, useEffect, useRef } from 'react';
import { SeriesCard } from './series-card';
import { api } from '@/lib/api-client';
import { API_URL } from '@/lib/constants';
import type { Series, Script, VoiceInfo, ScriptMode } from '@/lib/types';

interface SeriesSectionProps {
  lastScript: Script | null;
  lastVoiceMap: Record<string, string>;
  voices: VoiceInfo[];
  autoExpandId?: string | null;
}

export function SeriesSection({ lastScript, lastVoiceMap, voices, autoExpandId }: SeriesSectionProps) {
  const [seriesList, setSeriesList] = useState<Series[]>([]);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [continuing, setContinuing] = useState<string | null>(null);
  const [merging, setMerging] = useState<string | null>(null);
  const [newTitle, setNewTitle] = useState('');
  const [newMode, setNewMode] = useState<ScriptMode>('story');
  const [hints, setHints] = useState<Record<string, string>>({});
  const importRef = useRef<HTMLInputElement>(null);

  const loadSeries = async () => {
    try {
      const data = await api.listSeries();
      setSeriesList(data.series ?? []);
    } catch {
      // silent
    }
  };

  useEffect(() => {
    loadSeries();
  }, []);

  // Auto-expand series when autoExpandId changes (e.g. after batch generate)
  useEffect(() => {
    if (autoExpandId) {
      loadSeries().then(() => setExpandedId(autoExpandId));
    }
  }, [autoExpandId]);

  const handleCreate = async () => {
    if (!newTitle.trim()) return;
    try {
      await api.createSeries({
        title: newTitle,
        mode: newMode,
        ...(lastScript
          ? { script_data: lastScript as unknown as Record<string, unknown>, voice_map: lastVoiceMap }
          : {}),
      });
      await loadSeries();
      setCreating(false);
      setNewTitle('');
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Create failed');
    }
  };

  const handleUpdate = async (sid: string, updates: Record<string, unknown>) => {
    try {
      await api.updateSeries(sid, updates);
      await loadSeries();
    } catch {
      // silent
    }
  };

  const handleContinue = async (sid: string) => {
    setContinuing(sid);
    try {
      await api.continueSeries(sid, { prompt: hints[sid] ?? '' });
      await loadSeries();
      setHints((h) => ({ ...h, [sid]: '' }));
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Continue failed');
    }
    setContinuing(null);
  };

  const handleMerge = async (sid: string) => {
    setMerging(sid);
    try {
      const data = await api.mergeSeries(sid);
      const url = data.download_url.startsWith('http') ? data.download_url : `${API_URL}${data.download_url}`;
      window.open(url, '_blank');
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Merge failed');
    }
    setMerging(null);
  };

  const handleExport = (sid: string) => {
    window.open(`${API_URL}/studio/series/${sid}/export`, '_blank');
  };

  const handleDelete = async (sid: string) => {
    if (!confirm('Delete this series and all episodes?')) return;
    try {
      await api.deleteSeries(sid);
      await loadSeries();
    } catch {
      // silent
    }
  };

  const handleImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      await api.importSeries(file);
      await loadSeries();
      alert('Series imported successfully! Audio files need to be re-produced.');
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Import failed');
    }
    e.target.value = '';
  };

  return (
    <div className="mt-8 space-y-4">
      <div className="flex items-center justify-between">
        <h3
          className="text-lg font-semibold flex items-center gap-2"
          style={{ color: 'var(--text-1)' }}
        >
          <svg
            width="22"
            height="22"
            viewBox="0 0 24 24"
            fill="none"
            stroke="var(--accent-1)"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
            <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
          </svg>
          Series / Audiobook
        </h3>
        <div className="flex gap-2">
          <input
            type="file"
            accept=".json"
            ref={importRef}
            onChange={handleImport}
            style={{ display: 'none' }}
          />
          <button
            className="btn-secondary text-sm px-3 py-2"
            onClick={() => importRef.current?.click()}
            title="Import series from backup"
          >
            Import
          </button>
          <button
            className="btn-secondary text-sm px-4 py-2"
            onClick={() => setCreating(!creating)}
          >
            {creating ? 'Cancel' : '+ New Series'}
          </button>
        </div>
      </div>

      {creating && (
        <div className="panel-card space-y-3">
          <input
            placeholder="Series title"
            value={newTitle}
            onChange={(e) => setNewTitle(e.target.value)}
            className="input-area"
            style={{ minHeight: '40px', height: '40px' }}
          />
          <select
            value={newMode}
            onChange={(e) => setNewMode(e.target.value as ScriptMode)}
            style={{
              width: '100%',
              padding: '0.5rem 0.75rem',
              borderRadius: '0.75rem',
              background: 'var(--surface-2)',
              border: '1px solid var(--border)',
              color: 'var(--text-1)',
              fontSize: '0.875rem',
            }}
          >
            <option value="story">Story / Audiobook</option>
            <option value="dialogue">Dialogue</option>
          </select>
          {lastScript && (
            <p className="text-xs" style={{ color: 'var(--accent-1)' }}>
              Will include current script as Episode 1
            </p>
          )}
          <button
            className="btn-primary w-full"
            onClick={handleCreate}
            disabled={!newTitle.trim()}
          >
            Create Series
          </button>
        </div>
      )}

      {seriesList.length === 0 ? (
        <div className="panel-card text-center py-8">
          <p style={{ color: 'var(--text-2)' }}>
            No series yet. Create one to start multi-episode production.
          </p>
        </div>
      ) : (
        seriesList.map((s) => (
          <SeriesCard
            key={s.id}
            series={s}
            expanded={expandedId === s.id}
            onToggle={() => setExpandedId(expandedId === s.id ? null : s.id)}
            continuing={continuing === s.id}
            merging={merging === s.id}
            continueHint={hints[s.id] ?? ''}
            setContinueHint={(v) => setHints((h) => ({ ...h, [s.id]: v }))}
            voices={voices}
            onContinue={() => handleContinue(s.id)}
            onMerge={() => handleMerge(s.id)}
            onDelete={() => handleDelete(s.id)}
            onExport={() => handleExport(s.id)}
            onUpdate={handleUpdate}
          />
        ))
      )}
    </div>
  );
}
