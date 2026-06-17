'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import dynamic from 'next/dynamic';
import { api } from '@/lib/api-client';
import type { WorkflowRecord, WorkflowRunRecord, ScriptMode, OutputFormat } from '@/lib/types';
import { API_URL } from '@/lib/constants';

// Drawflow requires DOM — dynamic import with ssr: false
const WorkflowCanvas = dynamic(
  () => import('./workflow-canvas').then((m) => m.WorkflowCanvas),
  { ssr: false, loading: () => <div style={{ height: 400 }} className="panel-card flex items-center justify-center text-muted">Loading canvas...</div> },
);

interface EditorRef {
  export: () => Record<string, unknown>;
  import: (data: Record<string, unknown>) => void;
}

export function WorkflowsPage() {
  const [workflows, setWorkflows] = useState<WorkflowRecord[]>([]);
  const [editingWf, setEditingWf] = useState<WorkflowRecord | null>(null);
  const [showEditor, setShowEditor] = useState(false);

  // Editor form state
  const [wfName, setWfName] = useState('');
  const [wfMode, setWfMode] = useState<ScriptMode>('dialogue');
  const [wfFormat, setWfFormat] = useState<OutputFormat>('wav');
  const [wfNormalize, setWfNormalize] = useState(true);
  const [wfSilence, setWfSilence] = useState(0.3);
  const [wfCrossfade, setWfCrossfade] = useState(0.0);

  // Per-workflow runs cache: { [wfId]: runs[] }
  const [runsCache, setRunsCache] = useState<Record<string, WorkflowRunRecord[]>>({});
  // Per-workflow test state
  const [testTexts, setTestTexts] = useState<Record<string, string>>({});
  const [testLoading, setTestLoading] = useState<string | null>(null);
  const [testResults, setTestResults] = useState<Record<string, { url?: string; error?: string; format?: string }>>({});

  const canvasRef = useRef<EditorRef | null>(null);

  const loadWorkflows = useCallback(async () => {
    try {
      const data = await api.listWorkflows();
      setWorkflows(data.workflows ?? []);
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    loadWorkflows();
  }, [loadWorkflows]);

  const handleNew = () => {
    setEditingWf(null);
    setWfName('');
    setWfMode('dialogue');
    setWfFormat('wav');
    setWfNormalize(true);
    setWfSilence(0.3);
    setWfCrossfade(0.0);
    canvasRef.current = null;
    setShowEditor(true);
  };

  const handleEdit = (wf: WorkflowRecord) => {
    setEditingWf(wf);
    setWfName(wf.config.name);
    setWfMode(wf.config.mode ?? 'dialogue');
    setWfFormat(wf.config.output_format ?? 'wav');
    setWfNormalize(wf.config.normalize ?? true);
    setWfSilence(wf.config.silence_gap ?? 0.3);
    setWfCrossfade(wf.config.crossfade ?? 0.0);
    canvasRef.current = null;
    setShowEditor(true);
  };

  const handleBack = () => {
    setShowEditor(false);
    canvasRef.current = null;
    setEditingWf(null);
  };

  const handleSave = async () => {
    if (!wfName.trim()) return;
    const editorData = canvasRef.current ? canvasRef.current.export() : {};
    const config = {
      name: wfName,
      mode: wfMode,
      output_format: wfFormat,
      normalize: wfNormalize,
      silence_gap: wfSilence,
      crossfade: wfCrossfade,
      editor_data: editorData,
      max_characters: 4,
      description: '',
      voice_overrides: {},
    };

    try {
      if (editingWf?.id) {
        await api.updateWorkflow(editingWf.id, config);
      } else {
        await api.createWorkflow(config);
      }
      handleBack();
      await loadWorkflows();
    } catch (e) {
      console.error('Save failed', e);
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm('Delete this workflow?')) return;
    try {
      await api.deleteWorkflow(id);
      setWorkflows((prev) => prev.filter((w) => w.id !== id));
    } catch {
      // ignore
    }
  };

  const handleTest = async (wf: WorkflowRecord) => {
    const text = testTexts[wf.id] ?? '';
    if (!text.trim()) return;
    setTestLoading(wf.id);
    setTestResults((prev) => ({ ...prev, [wf.id]: {} }));
    try {
      const res = await fetch(`${API_URL}${wf.webhook_url}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      });
      if (res.ok) {
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        setTestResults((prev) => ({
          ...prev,
          [wf.id]: { url, format: wf.config.output_format },
        }));
      } else {
        const err = await res.json().catch(() => ({}));
        setTestResults((prev) => ({
          ...prev,
          [wf.id]: { error: err.detail || 'Failed' },
        }));
      }
    } catch (e) {
      setTestResults((prev) => ({ ...prev, [wf.id]: { error: (e as Error).message } }));
    } finally {
      setTestLoading(null);
    }
  };

  const loadRuns = async (wfId: string) => {
    try {
      const data = await api.getWorkflowRuns(wfId);
      setRunsCache((prev) => ({ ...prev, [wfId]: data.runs ?? [] }));
    } catch {
      // ignore
    }
  };

  // --- Editor view ---
  if (showEditor) {
    return (
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <button
            onClick={handleBack}
            className="btn-secondary"
            style={{ width: 'auto', padding: '8px 16px' }}
          >
            Back
          </button>
          <h3 className="text-lg font-semibold text-main">
            {editingWf ? 'Edit Workflow' : 'New Workflow'}
          </h3>
          <button
            onClick={handleSave}
            disabled={!wfName.trim()}
            className="btn-primary"
            style={{ width: 'auto', padding: '8px 24px' }}
          >
            Save
          </button>
        </div>

        <div className="grid gap-4 lg:grid-cols-3">
          <div className="panel-card space-y-3">
            <label className="label-text">Workflow Name</label>
            <input
              type="text"
              value={wfName}
              onChange={(e) => setWfName(e.target.value)}
              className="select-control"
              placeholder="My Workflow"
            />
          </div>
          <div className="panel-card space-y-3">
            <label className="label-text">Mode</label>
            <div className="flex gap-2">
              {(['dialogue', 'story'] as const).map((m) => (
                <button
                  key={m}
                  onClick={() => setWfMode(m)}
                  className={`flex-1 px-3 py-2 rounded-xl text-xs font-semibold uppercase transition-all ${
                    wfMode === m
                      ? 'bg-primary-500/20 text-primary-400 border border-primary-500/30'
                      : 'text-muted border border-[var(--border)]'
                  }`}
                >
                  {m}
                </button>
              ))}
            </div>
          </div>
          <div className="panel-card space-y-3">
            <label className="label-text">Output</label>
            <div className="flex gap-2">
              {(['wav', 'mp3'] as const).map((f) => (
                <button
                  key={f}
                  onClick={() => setWfFormat(f)}
                  className={`flex-1 px-3 py-2 rounded-xl text-xs font-semibold uppercase transition-all ${
                    wfFormat === f
                      ? 'bg-primary-500/20 text-primary-400 border border-primary-500/30'
                      : 'text-muted border border-[var(--border)]'
                  }`}
                >
                  {f}
                </button>
              ))}
            </div>
          </div>
        </div>

        <WorkflowCanvas
          mode={wfMode}
          format={wfFormat}
          editorData={editingWf?.config.editor_data}
          onReady={(ref) => { canvasRef.current = ref; }}
        />
        <p className="text-xs text-muted text-center">
          Drag nodes to rearrange. Pipeline flows left to right.
        </p>
      </div>
    );
  }

  // --- List view ---
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold text-main">Workflows</h3>
          <p className="text-xs text-muted">
            Create pipelines with webhook URLs. Trigger via curl, cron, or any HTTP client.
          </p>
        </div>
        <button
          onClick={handleNew}
          className="btn-primary"
          style={{ width: 'auto', padding: '10px 20px' }}
        >
          + New Workflow
        </button>
      </div>

      {workflows.length === 0 ? (
        <div className="panel-card text-center py-12">
          <p className="text-muted">No workflows yet. Create one to get a webhook URL.</p>
        </div>
      ) : (
        <div className="space-y-4">
          {workflows.map((wf) => {
            const wfRuns = runsCache[wf.id] ?? [];
            const testText = testTexts[wf.id] ?? '';
            const testResult = testResults[wf.id];
            const isTestLoading = testLoading === wf.id;
            const origin = typeof window !== 'undefined' ? window.location.origin : '';

            return (
              <div key={wf.id} className="wf-card space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <span className="font-semibold text-main">{wf.config.name}</span>
                    <span className="chip">{wf.config.mode}</span>
                    <span className="chip">{wf.config.output_format}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-muted">{wf.run_count} runs</span>
                    <button
                      onClick={() => handleEdit(wf)}
                      className="px-3 py-1 text-xs font-semibold text-primary-400 border border-primary-500/30 rounded-lg hover:bg-primary-500/10"
                    >
                      Edit
                    </button>
                    <button
                      onClick={() => handleDelete(wf.id)}
                      className="px-3 py-1 text-xs font-semibold text-red-400 border border-red-500/30 rounded-lg hover:bg-red-500/10"
                    >
                      Delete
                    </button>
                  </div>
                </div>

                {/* Webhook URL */}
                <div>
                  <label className="label-text">Webhook URL</label>
                  <div className="wf-webhook mt-1">
                    <span className="text-muted">POST</span>{' '}
                    <span className="text-primary-400">
                      {origin}{wf.webhook_url}
                    </span>
                  </div>
                </div>

                {/* Curl example */}
                <details className="text-xs">
                  <summary className="text-muted cursor-pointer hover:text-main">curl example</summary>
                  <pre className="wf-webhook mt-2 text-xs overflow-x-auto" style={{ whiteSpace: 'pre-wrap' }}>
{`curl -X POST ${origin}${wf.webhook_url} \\
  -H "Content-Type: application/json" \\
  -d '{"text": "your text here"}' \\
  --output output.${wf.config.output_format}`}
                  </pre>
                </details>

                {/* Quick test */}
                <details className="text-xs">
                  <summary className="text-muted cursor-pointer hover:text-main">Quick test</summary>
                  <div className="mt-2 space-y-2">
                    <textarea
                      value={testText}
                      onChange={(e) =>
                        setTestTexts((prev) => ({ ...prev, [wf.id]: e.target.value }))
                      }
                      placeholder="Enter test text..."
                      className="select-control"
                      style={{ minHeight: '60px', resize: 'vertical', fontSize: '12px' }}
                    />
                    <button
                      onClick={() => handleTest(wf)}
                      disabled={isTestLoading || !testText.trim()}
                      className="btn-primary"
                      style={{ fontSize: '12px', padding: '8px' }}
                    >
                      {isTestLoading ? 'Running...' : 'Run Workflow'}
                    </button>
                    {testResult?.url && (
                      <div className="flex gap-2 items-center">
                        <audio controls src={testResult.url} style={{ height: '32px', flex: 1 }} />
                        <a
                          href={testResult.url}
                          download
                          className="px-3 py-1 text-xs font-semibold text-primary-400 border border-primary-500/30 rounded-lg"
                        >
                          Download
                        </a>
                      </div>
                    )}
                    {testResult?.error && (
                      <p className="text-red-400 text-xs">{testResult.error}</p>
                    )}
                  </div>
                </details>

                {/* Run history */}
                <details
                  className="text-xs"
                  onToggle={(e) => {
                    if ((e.target as HTMLDetailsElement).open) loadRuns(wf.id);
                  }}
                >
                  <summary className="text-muted cursor-pointer hover:text-main">
                    Run history ({wf.run_count})
                  </summary>
                  <div className="mt-2 space-y-1">
                    {wfRuns.length === 0 ? (
                      <p className="text-muted py-2">No runs yet</p>
                    ) : (
                      wfRuns.map((r) => (
                        <div
                          key={r.run_id}
                          className="flex items-center justify-between py-1 border-b border-[var(--border)]"
                        >
                          <span className={r.status === 'success' ? 'text-green-400' : 'text-red-400'}>
                            {r.status}
                          </span>
                          <span className="text-muted truncate max-w-[200px]">{r.input_text}</span>
                          <span className="text-muted">
                            {new Date(r.started_at * 1000).toLocaleTimeString()}
                          </span>
                          {r.output_url && (
                            <a href={r.output_url} className="text-primary-400">
                              Download
                            </a>
                          )}
                        </div>
                      ))
                    )}
                  </div>
                </details>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
