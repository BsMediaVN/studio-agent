export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8001';
export const WS_URL = process.env.NEXT_PUBLIC_WS_URL ?? 'ws://localhost:8001';

export const SAMPLE_RATE = 24000;
export const SEGMENT_CHAR_SIZE = 160;

export const CHAR_COLORS = [
  { bg: 'rgba(45,212,191,0.15)', border: 'rgba(45,212,191,0.4)', text: '#5eead4' },
  { bg: 'rgba(245,158,11,0.15)', border: 'rgba(245,158,11,0.4)', text: '#fcd34d' },
  { bg: 'rgba(251,113,133,0.15)', border: 'rgba(251,113,133,0.4)', text: '#fda4af' },
  { bg: 'rgba(129,140,248,0.15)', border: 'rgba(129,140,248,0.4)', text: '#a5b4fc' },
] as const;

export const NAV_TABS = [
  { label: 'Studio', href: '/studio' },
  { label: 'Video', href: '/video' },
  { label: 'Workflows', href: '/workflows' },
  { label: 'Single Voice', href: '/voice' },
  { label: 'Settings', href: '/settings' },
] as const;

export const JOB_POLL_INTERVAL_MS = 1000;
export const WS_RECONNECT_DELAY_MS = 2000;
