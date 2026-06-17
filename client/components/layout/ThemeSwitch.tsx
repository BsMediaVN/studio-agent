'use client';

import { useTheme } from '@/lib/hooks/use-theme';

export function ThemeSwitch() {
  const { theme, toggle } = useTheme();
  const isLight = theme === 'light';

  return (
    <button
      type="button"
      aria-label={isLight ? 'Switch to dark mode' : 'Switch to light mode'}
      onClick={toggle}
      className={`theme-switch ${isLight ? 'is-light' : 'is-dark'}`}
    >
      <span className="icon icon-sun">&#9728;</span>
      <span className="icon icon-moon">&#9790;</span>
      <span className="thumb" />
    </button>
  );
}
