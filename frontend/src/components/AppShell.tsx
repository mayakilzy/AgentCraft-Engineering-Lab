/**
 * AppShell — shared layout for every page in the 10-page frontend.
 *
 * Design system contract (styles/index.css):
 *   .app-shell       — flex row, min-h-screen
 *   .sidebar         — deep-navy 252px column with brand + nav + footer card
 *   .nav-btn         — sidebar nav link (active state via NavLink)
 *   .topbar          — top bar with search, lang/theme toggle, avatar
 *   .content         — max-width container for the page body
 *
 * Behaviour:
 *   - Sidebar collapses below 850px into a slide-in drawer (CSS-only).
 *   - Language toggle uses a button (NOT a select) per Mission II spec.
 *   - Theme toggle adds/removes the `dark` class on <html>.
 *   - RTL: flips dir on <html> via applyDocumentDir.
 *   - Skip link for keyboard users (visible on focus).
 *   - `previewMode` shows an orange PREVIEW DATA pill in the topbar.
 */
import { useEffect, useState, type ReactNode } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  Home,
  FlaskConical,
  Wrench,
  Share2,
  Activity,
  Bot,
  History,
  Server,
  NotebookPen,
  Settings,
  Menu,
  Search,
  Moon,
  Sun,
  Languages,
  X,
} from 'lucide-react';
import { applyDocumentDir, type Locale } from '../i18n';
import { getCachedSession } from '../hooks/useGuestSession';

interface NavItem {
  to: string;
  key: string;
  icon: typeof Home;
}

const NAV_ITEMS: NavItem[] = [
  { to: '/', key: 'nav.home', icon: Home },
  { to: '/experiments', key: 'nav.experiments', icon: FlaskConical },
  { to: '/workbench', key: 'nav.workbench', icon: Wrench },
  { to: '/graph', key: 'nav.graphLab', icon: Share2 },
  { to: '/observability', key: 'nav.observabilityLab', icon: Activity },
  { to: '/mentor', key: 'nav.mentor', icon: Bot },
  { to: '/history', key: 'nav.history', icon: History },
  { to: '/environment', key: 'nav.environment', icon: Server },
  { to: '/notes', key: 'nav.notes', icon: NotebookPen },
  { to: '/settings', key: 'nav.settings', icon: Settings },
];

interface AppShellProps {
  children: ReactNode;
  /** Show the orange "PREVIEW DATA" pill in the top bar (backend down). */
  previewMode?: boolean;
}

export function AppShell({ children, previewMode = false }: AppShellProps) {
  const { t, i18n } = useTranslation();
  const location = useLocation();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [theme, setTheme] = useState<'light' | 'dark'>(() => {
    if (typeof document === 'undefined') return 'light';
    return document.documentElement.classList.contains('dark')
      ? 'dark'
      : 'light';
  });

  // Close the mobile drawer whenever the route changes.
  useEffect(() => {
    setDrawerOpen(false);
  }, [location.pathname]);

  function toggleLocale() {
    const next: Locale = i18n.language === 'ar' ? 'en' : 'ar';
    i18n.changeLanguage(next);
    applyDocumentDir(next);
  }

  function toggleTheme() {
    const next = theme === 'dark' ? 'light' : 'dark';
    setTheme(next);
    if (typeof document !== 'undefined') {
      document.documentElement.classList.toggle('dark', next === 'dark');
    }
  }

  const session = getCachedSession();
  const isArabic = i18n.language === 'ar';

  return (
    <div className="app-shell">
      {/* Skip link for keyboard users */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-white focus:px-3 focus:py-2 focus:text-sm focus:text-ink-900 focus:shadow-card"
      >
        {t('common.skipToContent')}
      </a>

      {/* Sidebar (desktop: static; mobile: drawer) */}
      <aside
        className={`sidebar${drawerOpen ? ' show' : ''}`}
        role="navigation"
        aria-label="Main navigation"
      >
        <div className="sidebar-brand">
          <span className="brand-icon" aria-hidden>
            ⬡
          </span>
          <div>
            <strong>{t('app.title')}</strong>
            <small>{t('app.subtitle')}</small>
          </div>
        </div>

        <div className="side-caption">{t('nav.experiments')}</div>
        <nav className="flex flex-col">
          {NAV_ITEMS.map((it) => {
            const Icon = it.icon;
            return (
              <NavLink
                key={it.to}
                to={it.to}
                end={it.to === '/'}
                className={({ isActive }) =>
                  `nav-btn${isActive ? ' active' : ''}`
                }
              >
                <Icon size={16} aria-hidden />
                <span>{t(it.key)}</span>
              </NavLink>
            );
          })}
        </nav>

        <div className="sidebar-bottom">
          <span className="online-dot" aria-hidden />
          {t('common.guestSession')}
          <small>
            {session
              ? `${session.session_id.slice(0, 8)}…`
              : t('common.notChecked')}
          </small>
        </div>
      </aside>

      {/* Mobile drawer backdrop */}
      {drawerOpen && (
        <button
          type="button"
          aria-label={t('common.toggleMenu')}
          onClick={() => setDrawerOpen(false)}
          className="fixed inset-0 z-20 border-0 bg-black/40 md:hidden"
        />
      )}

      {/* Main column: top bar + content */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="topbar">
          <button
            type="button"
            className="menu-toggle icon-btn"
            aria-label={t('common.toggleMenu')}
            onClick={() => setDrawerOpen((v) => !v)}
          >
            {drawerOpen ? <X size={16} /> : <Menu size={16} />}
          </button>

          <div className="top-search">
            <Search size={14} aria-hidden />
            <input
              type="search"
              placeholder={t('common.searchPlaceholder')}
              aria-label={t('common.searchPlaceholder')}
            />
          </div>

          {previewMode && (
            <span className="preview-pill" data-testid="preview-pill">
              {t('common.previewData')}
            </span>
          )}

          <button
            type="button"
            className="lang-btn"
            aria-label="Toggle language"
            onClick={toggleLocale}
          >
            <Languages size={14} aria-hidden />
            {isArabic ? 'EN' : 'ع'}
          </button>

          <button
            type="button"
            className="icon-btn"
            aria-label="Toggle theme"
            onClick={toggleTheme}
          >
            {theme === 'dark' ? <Sun size={14} /> : <Moon size={14} />}
          </button>

          <span className="avatar" aria-hidden>
            G
          </span>
        </header>

        <main id="main-content" className="content flex-1" tabIndex={-1}>
          {children}
        </main>
      </div>
    </div>
  );
}
