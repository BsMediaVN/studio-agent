'use client';

import {
  createContext,
  useContext,
  useState,
  useCallback,
  type ReactNode,
} from 'react';

export interface StudioSettings {
  llmProvider: 'claude' | 'openai';
  llmModel: string;
  maxCharacters: number;
  outputFormat: 'wav' | 'mp3';
  normalize: boolean;
  silenceGap: number;
  crossfade: number;
  speed: number;
  temperature: number;
  topK: number;
  targetDuration: number | null;
}

export const SETTINGS_DEFAULTS: StudioSettings = {
  llmProvider: 'claude',
  llmModel: 'claude-sonnet-4-20250514',
  maxCharacters: 4,
  outputFormat: 'wav',
  normalize: true,
  silenceGap: 0.3,
  crossfade: 0.0,
  speed: 1.0,
  temperature: 0.8,
  topK: 50,
  targetDuration: null,
};

const STORAGE_KEY = 'studio-settings';

function loadSettings(): StudioSettings {
  if (typeof window === 'undefined') return SETTINGS_DEFAULTS;
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    return stored ? { ...SETTINGS_DEFAULTS, ...JSON.parse(stored) } : SETTINGS_DEFAULTS;
  } catch {
    return SETTINGS_DEFAULTS;
  }
}

interface SettingsContextValue {
  settings: StudioSettings;
  updateSetting: <K extends keyof StudioSettings>(key: K, value: StudioSettings[K]) => void;
  resetSettings: () => void;
}

export const SettingsContext = createContext<SettingsContextValue>({
  settings: SETTINGS_DEFAULTS,
  updateSetting: () => {},
  resetSettings: () => {},
});

export function useSettings() {
  return useContext(SettingsContext);
}

export function SettingsProvider({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useState<StudioSettings>(loadSettings);

  const updateSetting = useCallback(
    <K extends keyof StudioSettings>(key: K, value: StudioSettings[K]) => {
      setSettings((prev) => {
        const next = { ...prev, [key]: value };
        try {
          localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
        } catch {}
        return next;
      });
    },
    [],
  );

  const resetSettings = useCallback(() => {
    setSettings(SETTINGS_DEFAULTS);
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch {}
  }, []);

  return (
    <SettingsContext.Provider value={{ settings, updateSetting, resetSettings }}>
      {children}
    </SettingsContext.Provider>
  );
}
