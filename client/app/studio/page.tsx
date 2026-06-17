import { StudioPage } from '@/components/studio/studio-page';

export default function StudioRoute() {
  return (
    <div
      style={{
        maxWidth: 1280,
        margin: '0 auto',
        padding: '40px 24px',
      }}
    >
      <div className="reveal" style={{ marginBottom: '32px' }}>
        <h1
          className="title-text"
          style={{ fontSize: 28, color: 'var(--text-1)', marginBottom: 8 }}
        >
          Studio
        </h1>
        <p className="text-muted" style={{ fontSize: 15 }}>
          Multi-character Vietnamese TTS production
        </p>
      </div>
      <StudioPage />
    </div>
  );
}
