'use client';

import type { ReactNode } from 'react';
import { ThemeContext, useThemeState } from '@/lib/hooks/use-theme';

export function ThemeProvider({ children }: { children: ReactNode }) {
  const value = useThemeState();
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}
