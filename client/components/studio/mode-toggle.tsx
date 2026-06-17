'use client';

import type { ScriptMode } from '@/lib/types';

interface ModeToggleProps {
  mode: ScriptMode;
  onChange: (mode: ScriptMode) => void;
}

const MODES: { id: ScriptMode; label: string; desc: string }[] = [
  { id: 'dialogue', label: 'Video Dialogue', desc: 'Pure character conversations' },
  { id: 'story', label: 'Story / Audiobook', desc: 'Narrator + character dialogue' },
];

export function ModeToggle({ mode, onChange }: ModeToggleProps) {
  return (
    <div className="flex items-center gap-3">
      {MODES.map((m) => (
        <button
          key={m.id}
          onClick={() => onChange(m.id)}
          className={`flex-1 panel-card text-left transition-all ${
            mode === m.id ? '' : 'opacity-60 hover:opacity-80'
          }`}
          style={
            mode === m.id
              ? { borderColor: 'rgba(45,212,191,0.4)', boxShadow: '0 8px 32px rgba(45,212,191,0.1)' }
              : {}
          }
        >
          <div className="font-semibold text-sm text-main">{m.label}</div>
          <div className="text-xs text-muted mt-1">{m.desc}</div>
        </button>
      ))}
    </div>
  );
}
