'use client';

interface TargetDurationProps {
  value: number | null;
  onChange: (v: number | null) => void;
}

const PRESETS: { label: string; value: number | null }[] = [
  { label: 'Auto', value: null },
  { label: '30s', value: 30 },
  { label: '1m', value: 60 },
  { label: '2m', value: 120 },
  { label: '5m', value: 300 },
];

function fmtDuration(s: number): string {
  const m = Math.floor(s / 60);
  const sec = String(Math.round(s % 60)).padStart(2, '0');
  return `${m}:${sec}`;
}

export function TargetDuration({ value, onChange }: TargetDurationProps) {
  const isActive = value !== null;

  return (
    <div className="panel-card space-y-3">
      <div className="flex items-center justify-between">
        <label className="label-text" style={{ marginBottom: 0 }}>
          Target Duration
        </label>
        <span
          className="font-mono text-xs px-2 py-0.5 rounded-full"
          style={{
            background: isActive
              ? 'linear-gradient(135deg, rgba(45,212,191,0.15), rgba(245,158,11,0.15))'
              : 'rgba(255,255,255,0.05)',
            color: isActive ? '#2dd4bf' : '#64748b',
            border: '1px solid ' + (isActive ? 'rgba(45,212,191,0.3)' : 'rgba(255,255,255,0.08)'),
          }}
        >
          {isActive ? fmtDuration(value!) : 'Auto'}
        </span>
      </div>

      <div className="flex items-center gap-2 flex-wrap">
        {PRESETS.map((p) => {
          const selected = value === p.value || (!value && p.value === null);
          return (
            <button
              key={p.label}
              onClick={() => onChange(p.value)}
              className="px-3 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer"
              style={{
                background: selected
                  ? 'linear-gradient(135deg, rgba(45,212,191,0.2), rgba(45,212,191,0.1))'
                  : 'rgba(255,255,255,0.04)',
                border: '1px solid ' + (selected ? 'rgba(45,212,191,0.4)' : 'rgba(255,255,255,0.08)'),
                color: selected ? '#2dd4bf' : '#94a3b8',
                boxShadow: selected ? '0 0 12px rgba(45,212,191,0.1)' : 'none',
              }}
            >
              {p.label}
            </button>
          );
        })}

        <div className="flex items-center gap-1 ml-auto">
          <input
            type="number"
            min="1"
            max="600"
            step="1"
            value={value ?? ''}
            placeholder="Custom"
            onChange={(e) =>
              onChange(
                e.target.value
                  ? Math.max(1, Math.min(600, parseFloat(e.target.value)))
                  : null,
              )
            }
            className="w-20 px-2 py-1.5 rounded-lg text-xs font-mono text-center transition-all"
            style={{
              background: 'rgba(255,255,255,0.04)',
              border: '1px solid rgba(255,255,255,0.1)',
              color: '#e2e8f0',
              outline: 'none',
            }}
            onFocus={(e) => (e.target.style.borderColor = 'rgba(45,212,191,0.4)')}
            onBlur={(e) => (e.target.style.borderColor = 'rgba(255,255,255,0.1)')}
          />
          <span className="text-xs text-muted">sec</span>
        </div>
      </div>

      {isActive && (
        <div className="flex items-center gap-2 mt-1">
          <div className="flex-1 h-1 rounded-full overflow-hidden" style={{ background: 'rgba(255,255,255,0.06)' }}>
            <div
              className="h-full rounded-full transition-all duration-500"
              style={{
                width: `${Math.min(100, (value! / 300) * 100)}%`,
                background: 'linear-gradient(90deg, #2dd4bf, #f59e0b)',
              }}
            />
          </div>
          <span className="text-xs text-muted whitespace-nowrap">
            {value! >= 60
              ? `${Math.floor(value! / 60)}m ${Math.round(value! % 60)}s`
              : `${value}s`}
          </span>
        </div>
      )}

      <p className="text-xs" style={{ color: '#475569' }}>
        Audio output will be adjusted to match the target length. Speed is auto-calculated.
      </p>
    </div>
  );
}
