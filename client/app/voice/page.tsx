import { VoicePage } from '@/components/voice/voice-page';

export default function VoiceRoute() {
  return (
    <div style={{ maxWidth: 1280, margin: '0 auto', padding: '40px 24px' }}>
      <div className="reveal space-y-2 mb-8">
        <h1 className="title-text" style={{ fontSize: 28, color: 'var(--text-1)' }}>
          Single Voice
        </h1>
        <p className="text-muted" style={{ fontSize: 15 }}>
          Stream TTS directly from text — no script generation.
        </p>
      </div>
      <VoicePage />
    </div>
  );
}
