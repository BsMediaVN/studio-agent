'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { NAV_TABS } from '@/lib/constants';
import { ThemeSwitch } from './ThemeSwitch';

export function Navigation() {
  const pathname = usePathname();

  return (
    <header
      style={{
        position: 'sticky',
        top: 0,
        zIndex: 50,
        borderBottom: '1px solid var(--border)',
        background: 'var(--surface)',
        backdropFilter: 'blur(12px)',
        WebkitBackdropFilter: 'blur(12px)',
      }}
    >
      <div
        style={{
          maxWidth: 1280,
          margin: '0 auto',
          padding: '12px 24px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 16,
        }}
      >
        {/* Logo */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexShrink: 0 }}>
          <svg
            width="32"
            height="32"
            viewBox="0 0 100 100"
            xmlns="http://www.w3.org/2000/svg"
            aria-hidden="true"
          >
            <defs>
              <linearGradient id="nav-flame" x1="0%" y1="100%" x2="0%" y2="0%">
                <stop offset="0%" stopColor="#84cc16" />
                <stop offset="50%" stopColor="#f59e0b" />
                <stop offset="100%" stopColor="#ef4444" />
              </linearGradient>
            </defs>
            <circle cx="50" cy="50" r="45" fill="#1a1a2e" />
            <rect x="25" y="30" width="5" height="40" rx="2.5" fill="url(#nav-flame)" />
            <rect x="35" y="20" width="5" height="60" rx="2.5" fill="url(#nav-flame)" />
            <rect x="45" y="10" width="5" height="80" rx="2.5" fill="url(#nav-flame)" />
            <rect x="55" y="20" width="5" height="60" rx="2.5" fill="url(#nav-flame)" />
            <rect x="65" y="30" width="5" height="40" rx="2.5" fill="url(#nav-flame)" />
          </svg>
          <span className="title-text" style={{ fontSize: 16, color: 'var(--text-1)' }}>
            VietVoice Studio
          </span>
        </div>

        {/* Tab bar */}
        <nav className="tab-bar" aria-label="Main navigation">
          {NAV_TABS.map((tab) => {
            const isActive = pathname === tab.href || pathname.startsWith(tab.href + '/');
            return (
              <Link
                key={tab.href}
                href={tab.href}
                className={`tab-btn${isActive ? ' active' : ''}`}
                aria-current={isActive ? 'page' : undefined}
              >
                {tab.label}
              </Link>
            );
          })}
        </nav>

        {/* Theme toggle */}
        <ThemeSwitch />
      </div>
    </header>
  );
}
