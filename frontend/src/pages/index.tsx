/**
 * Pages: Graph Lab is fully wired in G02 (T07); the other four remain
 * clearly-marked placeholders until their owning groups.
 */
import { useTranslation } from 'react-i18next';
import { GraphLabPage } from './GraphLabPage';

interface PageProps {
  title: string;
  body?: string;
}

function PageShell({ title, body }: PageProps) {
  const { t } = useTranslation();
  return (
    <main
      id="main-content"
      className="mx-auto max-w-6xl px-4 py-8"
      tabIndex={-1}
    >
      <h1 className="text-2xl font-semibold text-ink-900">{title}</h1>
      <p className="mt-2 text-sm text-ink-900/70">
        {body ?? t('home.description')}
      </p>
      <div
        className="mt-6 rounded border border-dashed border-ink-100 bg-ink-50 p-6 text-xs text-ink-900/60"
        role="note"
      >
        {/* Marked as a placeholder until the owning group implements it. */}
        Placeholder — wired in a later group per the V1.0 mission sequence.
      </div>
    </main>
  );
}

export function HomePage() {
  const { t } = useTranslation();
  return (
    <main id="main-content" className="mx-auto max-w-6xl px-4 py-8" tabIndex={-1}>
      <h1 className="text-3xl font-semibold text-ink-900">{t('home.hero')}</h1>
      <p className="mt-3 max-w-2xl text-sm text-ink-900/80">
        {t('home.description')}
      </p>
    </main>
  );
}

// GraphLabPage is implemented in its own module to keep this file small.
export { GraphLabPage };

export function ObservabilityLabPage() {
  const { t } = useTranslation();
  return <PageShell title={t('nav.observabilityLab')} />;
}

export function ExperimentsPage() {
  const { t } = useTranslation();
  return <PageShell title={t('nav.experiments')} />;
}

export function HistoryPage() {
  const { t } = useTranslation();
  return <PageShell title={t('nav.history')} />;
}
