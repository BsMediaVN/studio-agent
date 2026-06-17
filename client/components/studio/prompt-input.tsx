'use client';

import { useState, useEffect } from 'react';
import { Spinner } from '@/components/ui/Spinner';
import type { ScriptMode } from '@/lib/types';

interface PromptInputProps {
  value: string;
  onChange: (v: string) => void;
  onGenerate: () => void;
  isGenerating: boolean;
  isDisabled: boolean;
  mode: ScriptMode;
}

const PLACEHOLDERS: Record<ScriptMode, string> = {
  story:
    "Describe your story... e.g. 'Cau chuyen ve mot chang trai gap lai ban cu sau 10 nam xa cach'",
  dialogue:
    "Describe your dialogue scene... e.g. 'Cuoc hoi thoai giua hai ban ve ke hoach cuoi tuan'",
};

const STEPS = [
  'Connecting to LLM...',
  'Analyzing prompt...',
  'Generating characters...',
  'Writing dialogue...',
  'Building scenes...',
  'Formatting script...',
];

export function PromptInput({
  value,
  onChange,
  onGenerate,
  isGenerating,
  isDisabled,
  mode,
}: PromptInputProps) {
  const [progress, setProgress] = useState(0);
  const [stepIdx, setStepIdx] = useState(0);

  useEffect(() => {
    if (!isGenerating) { setProgress(0); setStepIdx(0); return; }
    const interval = setInterval(() => {
      setProgress(p => Math.min(p + Math.random() * 8 + 2, 92));
      setStepIdx(s => Math.min(s + 1, STEPS.length - 1));
    }, 2000);
    return () => clearInterval(interval);
  }, [isGenerating]);

  return (
    <div className="panel-card space-y-4">
      <label className="label-text">Production Prompt</label>
      <div className="input-frame">
        <textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={PLACEHOLDERS[mode]}
          className="input-area"
          style={{ minHeight: '120px', height: '120px' }}
          spellCheck={false}
        />
      </div>
      <button
        onClick={onGenerate}
        disabled={isGenerating || !value.trim() || isDisabled}
        className="btn-primary"
      >
        {isGenerating ? (
          <>
            <Spinner size={16} />
            Generating Script...
          </>
        ) : (
          'Generate Script'
        )}
      </button>

      {isGenerating && (
        <div className="space-y-2">
          <div style={{
            height: '6px', borderRadius: '3px',
            background: 'var(--surface-2)', overflow: 'hidden',
          }}>
            <div style={{
              height: '100%', borderRadius: '3px',
              width: `${progress}%`,
              background: 'linear-gradient(90deg, var(--accent-1), var(--accent-2))',
              transition: 'width 0.5s ease',
            }} />
          </div>
          <div className="flex items-center justify-between">
            <span className="text-xs" style={{ color: 'var(--text-2)' }}>
              {STEPS[stepIdx]}
            </span>
            <span className="text-xs font-mono" style={{ color: 'var(--accent-1)' }}>
              {Math.round(progress)}%
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
