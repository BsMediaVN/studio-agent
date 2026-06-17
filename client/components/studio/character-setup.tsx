'use client';

import { CHAR_COLORS } from '@/lib/constants';
import type { CharacterPreset, VoiceInfo, Gender } from '@/lib/types';

type CharacterMode = 'auto' | 'manual';

interface CharacterSetupProps {
  mode: CharacterMode;
  onModeChange: (mode: CharacterMode) => void;
  characters: CharacterPreset[];
  onCharactersChange: (chars: CharacterPreset[]) => void;
  voiceMap: Record<string, string>;
  onVoiceMapChange: (map: Record<string, string>) => void;
  voices: VoiceInfo[];
  maxCharacters: number;
}

const chipStyle = (active: boolean) => ({
  background: active
    ? 'linear-gradient(135deg, rgba(45,212,191,0.15), rgba(45,212,191,0.08))'
    : 'rgba(255,255,255,0.03)',
  border: `1px solid ${active ? 'rgba(45,212,191,0.4)' : 'rgba(255,255,255,0.08)'}`,
  color: active ? '#2dd4bf' : '#94a3b8',
  boxShadow: active ? '0 0 12px rgba(45,212,191,0.08)' : 'none',
});

export function CharacterSetup({
  mode,
  onModeChange,
  characters,
  onCharactersChange,
  voiceMap,
  onVoiceMapChange,
  voices,
  maxCharacters,
}: CharacterSetupProps) {
  const addCharacter = () => {
    if (characters.length >= maxCharacters) return;
    const newChar: CharacterPreset = { name: '', gender: 'M' };
    onCharactersChange([...characters, newChar]);
  };

  const removeCharacter = (index: number) => {
    const oldName = characters[index].name;
    const updated = characters.filter((_, i) => i !== index);
    onCharactersChange(updated);
    if (oldName) {
      const newMap = { ...voiceMap };
      delete newMap[oldName];
      onVoiceMapChange(newMap);
    }
  };

  const updateCharacter = (index: number, field: keyof CharacterPreset, value: string) => {
    const updated = [...characters];
    const oldName = updated[index].name;

    if (field === 'name') {
      updated[index] = { ...updated[index], name: value };
      // Update voiceMap key if name changed
      if (oldName && voiceMap[oldName]) {
        const newMap = { ...voiceMap };
        newMap[value] = newMap[oldName];
        delete newMap[oldName];
        onVoiceMapChange(newMap);
      }
    } else {
      updated[index] = { ...updated[index], [field]: value as Gender };
    }
    onCharactersChange(updated);
  };

  const updateVoice = (charName: string, voiceId: string) => {
    onVoiceMapChange({ ...voiceMap, [charName]: voiceId });
  };

  return (
    <div className="panel-card space-y-3">
      <label className="label-text mb-0 block">Nhân vật</label>

      {/* Mode toggle */}
      <div className="flex gap-2">
        <button
          onClick={() => onModeChange('auto')}
          className="flex-1 px-3 py-2 rounded-lg text-xs font-semibold transition-all cursor-pointer"
          style={chipStyle(mode === 'auto')}
        >
          Tự động
        </button>
        <button
          onClick={() => onModeChange('manual')}
          className="flex-1 px-3 py-2 rounded-lg text-xs font-semibold transition-all cursor-pointer"
          style={chipStyle(mode === 'manual')}
        >
          Tuỳ chỉnh
        </button>
      </div>

      {mode === 'auto' && (
        <p className="text-xs" style={{ color: '#64748b' }}>
          AI sẽ tự tạo nhân vật phù hợp với nội dung (tối đa {maxCharacters}).
        </p>
      )}

      {/* Manual mode: character list */}
      {mode === 'manual' && (
        <div className="space-y-3">
          {characters.map((char, ci) => {
            const color = CHAR_COLORS[ci % CHAR_COLORS.length];
            return (
              <div
                key={ci}
                className="rounded-lg p-2.5 space-y-2"
                style={{
                  background: 'rgba(255,255,255,0.02)',
                  border: `1px solid ${color.border}`,
                }}
              >
                <div className="flex items-center gap-2">
                  {/* Name input */}
                  <input
                    type="text"
                    value={char.name}
                    onChange={(e) => updateCharacter(ci, 'name', e.target.value)}
                    placeholder={`Nhân vật ${ci + 1}`}
                    className="flex-1 px-2 py-1.5 rounded-lg text-xs"
                    style={{
                      background: 'rgba(255,255,255,0.04)',
                      border: '1px solid rgba(255,255,255,0.08)',
                      color: color.text,
                      outline: 'none',
                    }}
                  />
                  {/* Gender toggle */}
                  <button
                    onClick={() => updateCharacter(ci, 'gender', char.gender === 'M' ? 'F' : 'M')}
                    className="px-2 py-1.5 rounded-lg text-xs font-semibold cursor-pointer transition-all"
                    style={{
                      background: char.gender === 'M'
                        ? 'rgba(96,165,250,0.15)'
                        : 'rgba(251,113,133,0.15)',
                      border: `1px solid ${char.gender === 'M' ? 'rgba(96,165,250,0.4)' : 'rgba(251,113,133,0.4)'}`,
                      color: char.gender === 'M' ? '#93c5fd' : '#fda4af',
                      minWidth: '36px',
                    }}
                  >
                    {char.gender === 'M' ? 'Nam' : 'Nữ'}
                  </button>
                  {/* Remove button */}
                  <button
                    onClick={() => removeCharacter(ci)}
                    className="px-1.5 py-1 rounded text-xs cursor-pointer transition-all"
                    style={{
                      color: '#64748b',
                      background: 'transparent',
                      border: 'none',
                    }}
                    title="Xoá"
                  >
                    ✕
                  </button>
                </div>

                {/* Voice selector */}
                {char.name && voices.length > 0 && (
                  <select
                    className="select-control"
                    style={{ padding: '6px 10px', fontSize: '11px' }}
                    value={voiceMap[char.name] ?? ''}
                    onChange={(e) => updateVoice(char.name, e.target.value)}
                  >
                    <option value="">-- Giọng tự động --</option>
                    {voices.map((v) => (
                      <option key={v.id} value={v.id}>
                        {v.name || v.id}
                      </option>
                    ))}
                  </select>
                )}
              </div>
            );
          })}

          {/* Add button */}
          {characters.length < maxCharacters && (
            <button
              onClick={addCharacter}
              className="w-full px-3 py-2 rounded-lg text-xs font-medium cursor-pointer transition-all"
              style={{
                background: 'rgba(255,255,255,0.02)',
                border: '1px dashed rgba(255,255,255,0.12)',
                color: '#64748b',
              }}
            >
              + Thêm nhân vật
            </button>
          )}

          {characters.length === 0 && (
            <p className="text-xs" style={{ color: '#64748b' }}>
              Thêm nhân vật để AI viết kịch bản theo đúng yêu cầu.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
