'use client';

import { useEffect, useRef } from 'react';
import type { ScriptMode, OutputFormat } from '@/lib/types';

// Drawflow ships its own types but they may not be installed; use a loose interface
interface DrawflowInstance {
  reroute: boolean;
  start: () => void;
  addNode: (
    name: string,
    inputs: number,
    outputs: number,
    x: number,
    y: number,
    className: string,
    data: Record<string, unknown>,
    html: string,
  ) => void;
  addConnection: (
    outputId: number,
    inputId: number,
    outputClass: string,
    inputClass: string,
  ) => void;
  export: () => Record<string, unknown>;
  import: (data: Record<string, unknown>) => void;
}

interface DrawflowConstructor {
  new (el: HTMLElement): DrawflowInstance;
}

interface WorkflowCanvasProps {
  mode: ScriptMode;
  format: OutputFormat;
  editorData?: Record<string, unknown>;
  onReady: (ref: { export: () => Record<string, unknown>; import: (d: Record<string, unknown>) => void }) => void;
}

function makeNodeHtml(title: string, label: string, extra?: string): string {
  const d = document.createElement('div');
  const tb = document.createElement('div');
  tb.className = 'title-box';
  tb.textContent = title;
  const bx = document.createElement('div');
  bx.className = 'box';
  const lb = document.createElement('div');
  lb.className = 'node-label';
  lb.textContent = label;
  bx.appendChild(lb);
  if (extra) {
    const ex = document.createElement('div');
    ex.className = 'node-config';
    ex.textContent = extra;
    bx.appendChild(ex);
  }
  d.appendChild(tb);
  d.appendChild(bx);
  return d.innerHTML;
}

export function WorkflowCanvas({ mode, format, editorData, onReady }: WorkflowCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const editorRef = useRef<DrawflowInstance | null>(null);

  useEffect(() => {
    if (!containerRef.current || editorRef.current) return;

    let mounted = true;

    (async () => {
      try {
        const DrawflowModule = await import('drawflow');
        // Drawflow may export default or named
        const DrawflowClass: DrawflowConstructor =
          (DrawflowModule as unknown as { default: DrawflowConstructor }).default ??
          (DrawflowModule as unknown as DrawflowConstructor);

        if (!mounted || !containerRef.current) return;

        // Import Drawflow CSS
        await import('drawflow/dist/drawflow.min.css');

        const ed = new DrawflowClass(containerRef.current);
        ed.reroute = true;
        ed.start();

        const hasImportData =
          editorData && typeof editorData === 'object' && Object.keys(editorData).length > 0;

        if (hasImportData) {
          try {
            ed.import(editorData!);
          } catch (e) {
            console.warn('Failed to import editor data', e);
            addDefaultNodes(ed, mode, format);
          }
        } else {
          addDefaultNodes(ed, mode, format);
        }

        editorRef.current = ed;
        onReady({
          export: () => ed.export(),
          import: (data) => ed.import(data),
        });
      } catch (e) {
        console.error('Drawflow failed to load', e);
      }
    })();

    return () => {
      mounted = false;
    };
    // Only run once on mount
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="panel-card" style={{ padding: 0, overflow: 'hidden' }}>
      <div ref={containerRef} style={{ width: '100%', height: '400px' }} />
    </div>
  );
}

function addDefaultNodes(ed: DrawflowInstance, mode: ScriptMode, format: OutputFormat) {
  ed.addNode('text_input', 0, 1, 50, 120, 'text_input', {}, makeNodeHtml('Text Input', 'User text or webhook payload'));
  ed.addNode('script_gen', 1, 1, 320, 80, 'script_gen', {}, makeNodeHtml('Script Generator', 'LLM generates dialogue/story', 'Mode: ' + mode));
  ed.addNode('voice_assign', 1, 1, 590, 120, 'voice_assign', {}, makeNodeHtml('Voice Assigner', 'Auto-assign voices by gender'));
  ed.addNode('tts_produce', 1, 1, 860, 80, 'tts_produce', {}, makeNodeHtml('TTS Producer', 'Synthesize & merge audio', 'Format: ' + format));
  ed.addNode('output', 1, 0, 1130, 120, 'output', {}, makeNodeHtml('Output', 'Audio file / webhook response'));

  ed.addConnection(1, 2, 'output_1', 'input_1');
  ed.addConnection(2, 3, 'output_1', 'input_1');
  ed.addConnection(3, 4, 'output_1', 'input_1');
  ed.addConnection(4, 5, 'output_1', 'input_1');
}
