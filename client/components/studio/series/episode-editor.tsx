'use client';

import { useState } from 'react';
import { Spinner } from '@/components/ui/Spinner';
import type { Episode } from '@/lib/types';
import { api } from '@/lib/api-client';

interface EpisodeEditorProps {
  seriesId: string;
  episode: Episode;
  editScript: string;
  onEditScriptChange: (v: string) => void;
  onReproduced: () => void;
}

export function EpisodeEditor({
  seriesId,
  episode,
  editScript,
  onEditScriptChange,
  onReproduced,
}: EpisodeEditorProps) {
  const [reproducing, setReproducing] = useState(false);

  const handleReproduce = async () => {
    setReproducing(true);
    const lines = editScript.split('\n').filter((l) => l.trim());
    const dialogue = lines.map((line) => {
      const match = line.match(/^\[([^\]]+)\]\s*(.+)/);
      if (match) {
        const charName = match[1];
        const text = match[2];
        const isNarrator = charName.toLowerCase() === 'narrator';
        return {
          character: charName,
          text,
          emotion: 'neutral' as const,
          pause_after_ms: isNarrator ? 500 : 300,
          line_type: isNarrator ? ('narration' as const) : ('dialogue' as const),
        };
      }
      return {
        character: 'Narrator',
        text: line,
        emotion: 'neutral' as const,
        pause_after_ms: 500,
        line_type: 'narration' as const,
      };
    });

    const newScriptData = {
      ...(episode.script_data as Record<string, unknown>),
      scenes: [{ scene_num: 1, setting: '', dialogue }],
    };

    try {
      await api.reproduceEpisode(seriesId, episode.episode_num, {
        script_data: newScriptData,
      });
      onReproduced();
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Re-produce failed');
    } finally {
      setReproducing(false);
    }
  };

  return (
    <div
      className="px-3 pb-3 space-y-2"
      style={{ borderTop: '1px solid var(--border)' }}
    >
      <textarea
        value={editScript}
        onChange={(e) => onEditScriptChange(e.target.value)}
        className="input-area w-full font-mono"
        style={{ minHeight: '250px', fontSize: '0.78rem', lineHeight: '1.6', marginTop: '0.5rem' }}
        placeholder="[Character] Dialogue text..."
      />
      <div className="flex gap-2 items-center">
        <button
          className="btn-primary text-sm flex-1"
          onClick={handleReproduce}
          disabled={reproducing}
        >
          {reproducing ? (
            <>
              <Spinner size={14} />
              Re-producing...
            </>
          ) : (
            'Re-produce Audio'
          )}
        </button>
        <span className="text-xs" style={{ color: 'var(--text-2)' }}>
          Format: [Character] text
        </span>
      </div>
    </div>
  );
}
