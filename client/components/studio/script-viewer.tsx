'use client';

import { CHAR_COLORS } from '@/lib/constants';
import type { Script } from '@/lib/types';

interface ScriptViewerProps {
  script: Script;
}

const NARRATOR_COLOR = {
  bg: 'rgba(148,163,184,0.1)',
  border: 'rgba(148,163,184,0.3)',
  text: '#94a3b8',
};

export function ScriptViewer({ script }: ScriptViewerProps) {
  const totalLines = script.scenes.reduce((acc, s) => acc + s.dialogue.length, 0);

  return (
    <div className="panel-card space-y-3">
      <div className="flex items-center justify-between">
        <label className="label-text">Script: {script.title}</label>
        <span className="chip">{totalLines} lines</span>
      </div>

      <div className="script-editor">
        {script.scenes.map((scene, si) => (
          <div key={si}>
            {scene.setting && (
              <div className="text-muted text-xs mb-2 italic">[{scene.setting}]</div>
            )}
            {scene.dialogue.map((line, li) => {
              const isNarration =
                line.line_type === 'narration' || line.character === 'Narrator';
              const charIdx = script.characters.findIndex((c) => c.name === line.character);
              const color = isNarration
                ? NARRATOR_COLOR
                : CHAR_COLORS[Math.max(0, charIdx) % CHAR_COLORS.length];

              return (
                <div
                  key={`${si}-${li}`}
                  className={`mb-2 ${isNarration ? 'pl-0 italic' : 'pl-4'}`}
                >
                  <span
                    className="char-badge"
                    style={{
                      background: color.bg,
                      border: `1px solid ${color.border}`,
                      color: color.text,
                    }}
                  >
                    {isNarration ? 'Narrator' : line.character}
                  </span>{' '}
                  <span className={isNarration ? 'text-muted' : 'text-main'}>{line.text}</span>
                  {!isNarration && line.emotion && line.emotion !== 'neutral' && (
                    <span className="text-xs text-muted ml-2">({line.emotion})</span>
                  )}
                </div>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}
