'use client';

import { Spinner } from '@/components/ui/Spinner';
import type { JobStatus, Script } from '@/lib/types';

interface ProducePanelProps {
  script: Script | null;
  voiceMap: Record<string, string>;
  isProducing: boolean;
  progress: JobStatus | null;
  onProduce: () => void;
  onExportScript: () => void;
}

export function ProducePanel({
  script,
  isProducing,
  progress,
  onProduce,
  onExportScript,
}: ProducePanelProps) {
  const showProgress = isProducing || progress?.status === 'complete';

  return (
    <div className="panel-card space-y-4">
      <button
        onClick={onProduce}
        disabled={isProducing || !script}
        className="btn-primary"
      >
        {isProducing ? (
          <>
            <Spinner size={16} />
            Producing...
          </>
        ) : (
          'Produce Audio'
        )}
      </button>

      {script && (
        <div className="flex gap-2">
          <button className="btn-secondary flex-1 text-sm" onClick={onExportScript}>
            Export Script
          </button>
        </div>
      )}

      {showProgress && progress && (
        <div className="space-y-2">
          <div className="progress-bar-bg">
            <div className="progress-bar-fill" style={{ width: `${progress.progress ?? 0}%` }} />
          </div>
          <div className="flex items-center justify-between text-xs">
            <span className="text-muted">{progress.current_step ?? ''}</span>
            <span className="font-mono" style={{ color: 'var(--accent-1)' }}>
              {progress.progress ?? 0}%
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
