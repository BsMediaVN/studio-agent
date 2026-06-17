import { WorkflowsPage } from '@/components/workflows/workflows-page';

export default function WorkflowsRoute() {
  return (
    <div style={{ maxWidth: 1280, margin: '0 auto', padding: '40px 24px' }}>
      <div className="reveal space-y-2 mb-8">
        <h1 className="title-text" style={{ fontSize: 28, color: 'var(--text-1)' }}>
          Workflows
        </h1>
        <p className="text-muted" style={{ fontSize: 15 }}>
          Automated TTS pipelines triggered by webhook.
        </p>
      </div>
      <WorkflowsPage />
    </div>
  );
}
