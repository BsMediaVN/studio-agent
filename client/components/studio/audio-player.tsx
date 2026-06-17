'use client';

interface AudioPlayerProps {
  audioUrl: string;
  filename?: string;
}

export function AudioPlayer({ audioUrl, filename = 'audio' }: AudioPlayerProps) {
  return (
    <div className="panel-card space-y-4">
      <div className="flex items-center justify-between">
        <label className="label-text">Output</label>
        <div className="status-chip status-completed">
          <span className="status-dot" />
          <span className="font-mono">Complete</span>
        </div>
      </div>

      <audio controls preload="auto" className="w-full" style={{ borderRadius: '8px' }}>
        <source src={audioUrl} />
        Your browser does not support the audio element.
      </audio>

      <div className="flex gap-3">
        <a
          href={audioUrl}
          download={filename}
          className="btn-secondary flex-1 text-center no-underline"
          style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px' }}
        >
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
          >
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
            <polyline points="7 10 12 15 17 10" />
            <line x1="12" y1="15" x2="12" y2="3" />
          </svg>
          Download
        </a>
      </div>
    </div>
  );
}
