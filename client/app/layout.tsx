import type { Metadata } from 'next';
import { Noto_Sans, Noto_Sans_Display, JetBrains_Mono } from 'next/font/google';
import './globals.css';
import { ThemeProvider } from '@/components/layout/ThemeProvider';
import { Navigation } from '@/components/layout/Navigation';
import { SettingsProvider } from '@/providers/settings-provider';

const notoSans = Noto_Sans({
  subsets: ['latin'],
  weight: ['400', '500', '600', '700'],
  variable: '--font-noto-sans',
  display: 'swap',
});

const notoSansDisplay = Noto_Sans_Display({
  subsets: ['latin'],
  weight: ['500', '700'],
  variable: '--font-noto-display',
  display: 'swap',
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ['latin'],
  weight: ['400', '600'],
  variable: '--font-jetbrains-mono',
  display: 'swap',
});

export const metadata: Metadata = {
  title: 'VietVoice Studio',
  description: 'Multi-character Vietnamese TTS production studio',
  icons: { icon: '/icon.svg' },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="vi"
      className={`${notoSans.variable} ${notoSansDisplay.variable} ${jetbrainsMono.variable}`}
      suppressHydrationWarning
    >
      <body suppressHydrationWarning>
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){try{var t=localStorage.getItem('vietvoice-theme');if(t==='light')document.documentElement.setAttribute('data-theme','light');}catch(e){}})();`,
          }}
        />
        <ThemeProvider>
          <SettingsProvider>
            <Navigation />
            <main>{children}</main>
          </SettingsProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
