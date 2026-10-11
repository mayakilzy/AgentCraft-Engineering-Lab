import { NavLink } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useState } from 'react';
import { SUPPORTED_LOCALES, type Locale } from '../i18n';

const navItems = [
  { to: '/', key: 'nav.home' },
  { to: '/graph', key: 'nav.graphLab' },
  { to: '/observability', key: 'nav.observabilityLab' },
  { to: '/experiments', key: 'nav.experiments' },
  { to: '/history', key: 'nav.history' },
] as const;

export function NavBar() {
  const { t, i18n } = useTranslation();
  const [locale, setLocale] = useState<Locale>(
    i18n.language === 'ar' ? 'ar' : 'en',
  );

  function onLocaleChange(e: React.ChangeEvent<HTMLSelectElement>) {
    const next = e.target.value as Locale;
    setLocale(next);
    i18n.changeLanguage(next);
    document.documentElement.lang = next;
    document.documentElement.dir = next === 'ar' ? 'rtl' : 'ltr';
  }

  return (
    <nav
      className="border-b border-ink-100 bg-white px-4 py-3"
      aria-label="Main navigation"
    >
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-2">
        <span className="text-sm font-semibold text-ink-900">
          {t('app.title')}
        </span>
        <ul className="flex flex-wrap gap-1">
          {navItems.map((it) => (
            <li key={it.to}>
              <NavLink
                to={it.to}
                className={({ isActive }) =>
                  `rounded px-3 py-1.5 text-sm transition-colors ${
                    isActive
                      ? 'bg-accent-500 text-white'
                      : 'text-ink-900 hover:bg-ink-100'
                  }`
                }
              >
                {t(it.key)}
              </NavLink>
            </li>
          ))}
        </ul>
        <label className="flex items-center gap-1 text-xs text-ink-900">
          <span aria-hidden>{t('common.language')}:</span>
          <select
            value={locale}
            onChange={onLocaleChange}
            className="rounded border border-ink-100 bg-white px-2 py-1 text-xs"
            aria-label={t('common.language')}
            data-testid="locale-select"
          >
            {SUPPORTED_LOCALES.map((l) => (
              <option key={l} value={l}>
                {l === 'en' ? 'English' : 'العربية'}
              </option>
            ))}
          </select>
        </label>
      </div>
    </nav>
  );
}
