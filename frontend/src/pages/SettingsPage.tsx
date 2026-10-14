/**
 * SettingsPage — Preferences.
 *
 * Layout:
 *   - Language segmented control (EN/AR via i18next).
 *   - Theme segmented control (light/dark via html class).
 *   - Guest session info readout (session_id, expires_at, locale).
 *
 * No previewMode — settings are always local. Uses AppShell (no preview flag).
 */
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Globe, Moon, Sun, KeyRound } from 'lucide-react';
import { AppShell } from '../components/AppShell';
import { Card } from '../components/ui';
import { applyDocumentDir, type Locale } from '../i18n';
import { getCachedSession } from '../hooks/useGuestSession';

type Theme = 'light' | 'dark';

export function SettingsPage() {
  const { t, i18n } = useTranslation();
  const [theme, setTheme] = useState<Theme>(() => {
    if (typeof document === 'undefined') return 'light';
    return document.documentElement.classList.contains('dark') ? 'dark' : 'light';
  });

  function selectLocale(next: Locale) {
    i18n.changeLanguage(next);
    applyDocumentDir(next);
  }

  function selectTheme(next: Theme) {
    setTheme(next);
    if (typeof document !== 'undefined') {
      document.documentElement.classList.toggle('dark', next === 'dark');
    }
  }

  const session = getCachedSession();

  return (
    <AppShell>
      <section className="page-heading" aria-labelledby="settings-title">
        <div>
          <div className="eyebrow">{t('nav.settings')}</div>
          <h1 id="settings-title">{t('settings.title')}</h1>
          <p>{t('settings.subtitle')}</p>
        </div>
      </section>

      <div className="grid gap-[18px] md:grid-cols-2">
        <Card>
          <header className="mb-3 flex items-center gap-2">
            <Globe size={16} className="text-brand-600" aria-hidden />
            <h2 className="text-[16px] font-bold text-ink-900">
              {t('settings.language')}
            </h2>
          </header>
          <div
            className="segmented"
            role="group"
            aria-label={t('settings.language')}
            data-testid="settings-language"
          >
            <button
              type="button"
              className={i18n.language === 'en' ? 'selected' : ''}
              aria-pressed={i18n.language === 'en'}
              onClick={() => selectLocale('en')}
            >
              English
            </button>
            <button
              type="button"
              className={i18n.language === 'ar' ? 'selected' : ''}
              aria-pressed={i18n.language === 'ar'}
              onClick={() => selectLocale('ar')}
            >
              العربية
            </button>
          </div>
        </Card>

        <Card>
          <header className="mb-3 flex items-center gap-2">
            {theme === 'dark' ? (
              <Moon size={16} className="text-brand-600" aria-hidden />
            ) : (
              <Sun size={16} className="text-brand-600" aria-hidden />
            )}
            <h2 className="text-[16px] font-bold text-ink-900">
              {t('settings.theme')}
            </h2>
          </header>
          <div
            className="segmented"
            role="group"
            aria-label={t('settings.theme')}
            data-testid="settings-theme"
          >
            <button
              type="button"
              className={theme === 'light' ? 'selected' : ''}
              aria-pressed={theme === 'light'}
              onClick={() => selectTheme('light')}
            >
              {t('settings.themeLight')}
            </button>
            <button
              type="button"
              className={theme === 'dark' ? 'selected' : ''}
              aria-pressed={theme === 'dark'}
              onClick={() => selectTheme('dark')}
            >
              {t('settings.themeDark')}
            </button>
          </div>
        </Card>
      </div>

      <Card className="mt-[18px]">
        <header className="mb-3 flex items-center gap-2">
          <KeyRound size={16} className="text-brand-600" aria-hidden />
          <h2 className="text-[16px] font-bold text-ink-900">
            {t('common.guestSession')}
          </h2>
        </header>
        <p className="text-[12px] text-ink-500">{t('settings.guestInfo')}</p>
        <dl className="mt-3 grid gap-2 sm:grid-cols-3">
          <div className="rounded-btn border border-ink-200 bg-surface-subtle p-3">
            <dt className="muted text-[10px] font-bold uppercase tracking-wide">
              session_id
            </dt>
            <dd className="mt-1 font-mono text-[12px] text-ink-700" data-testid="settings-session-id">
              {session ? session.session_id : '—'}
            </dd>
          </div>
          <div className="rounded-btn border border-ink-200 bg-surface-subtle p-3">
            <dt className="muted text-[10px] font-bold uppercase tracking-wide">
              expires_at
            </dt>
            <dd className="mt-1 font-mono text-[12px] text-ink-700" data-testid="settings-session-expires">
              {session ? session.expires_at : '—'}
            </dd>
          </div>
          <div className="rounded-btn border border-ink-200 bg-surface-subtle p-3">
            <dt className="muted text-[10px] font-bold uppercase tracking-wide">
              locale
            </dt>
            <dd className="mt-1 font-mono text-[12px] text-ink-700" data-testid="settings-session-locale">
              {session ? session.locale : '—'}
            </dd>
          </div>
        </dl>
      </Card>
    </AppShell>
  );
}
