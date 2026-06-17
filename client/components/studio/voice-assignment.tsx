'use client';

import { CHAR_COLORS } from '@/lib/constants';
import type { Script, VoiceInfo } from '@/lib/types';

interface VoiceAssignmentProps {
  script: Script;
  voiceMap: Record<string, string>;
  voices: VoiceInfo[];
  onChange: (map: Record<string, string>) => void;
}

export function VoiceAssignment({ script, voiceMap, voices, onChange }: VoiceAssignmentProps) {
  const handleChange = (charName: string, voiceId: string) => {
    onChange({ ...voiceMap, [charName]: voiceId });
  };

  return (
    <div className="panel-card space-y-4">
      <label className="label-text">Voice Assignment</label>
      {script.characters.map((char, ci) => {
        const color = CHAR_COLORS[ci % CHAR_COLORS.length];
        return (
          <div key={char.name} className="space-y-1">
            <div className="flex items-center gap-2">
              <span
                className="char-badge"
                style={{
                  background: color.bg,
                  border: `1px solid ${color.border}`,
                  color: color.text,
                }}
              >
                {char.name}
              </span>
              <span className="chip">{char.gender === 'M' ? 'Nam' : 'Nu'}</span>
            </div>
            <select
              className="select-control"
              style={{ padding: '10px 14px', fontSize: '13px' }}
              value={voiceMap[char.name] ?? ''}
              onChange={(e) => handleChange(char.name, e.target.value)}
            >
              {voices.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.name || v.id}
                </option>
              ))}
            </select>
          </div>
        );
      })}
    </div>
  );
}
