import { useTranslation } from 'react-i18next';

export function Footer() {
  const { t } = useTranslation();
  return (
    <footer
      className="border-t border-ink-100 bg-white px-4 py-3 text-xs text-ink-900/60"
      role="contentinfo"
    >
      <div className="mx-auto max-w-6xl">
        {t('app.title')} · {t('footer.version')}
      </div>
    </footer>
  );
}
