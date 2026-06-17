import { SettingsPage } from '@/components/settings/settings-page';

export default function SettingsRoute() {
  return (
    <div style={{ maxWidth: 1280, margin: '0 auto', padding: '40px 24px' }}>
      <div className="reveal space-y-2 mb-8">
        <h1 className="title-text" style={{ fontSize: 28, color: 'var(--text-1)' }}>
          Settings
        </h1>
        <p className="text-muted" style={{ fontSize: 15 }}>
          Configure voice quality, LLM provider, audio output, and voice cloning.
        </p>
      </div>
      <SettingsPage />
    </div>
  );
}
