/**
 * HistoryPage — Results & Timeline.
 *
 * Per the contract §4: `GET /api/v1/runs?experiment_id=&limit=` paginated/
 * scope-limited history. Mission II: wrapped in AppShell, restyled with
 * the design-system classes, and bootstraps a guest session via
 * useGuestSession before calling listRuns (the cookie is required).
 */
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Filter, Download, RotateCcw, FileText } from 'lucide-react';
import { AppShell } from '../components/AppShell';
import { Card, Status, EmptyState, verdictTone } from '../components/ui';
import {
  exportRun,
  getExperiment,
  listExperiments,
  listRuns,
  resetRun,
  type ExperimentManifest,
  type RunRecord,
} from '../api/client';
import { useGuestSession } from '../hooks/useGuestSession';

export function HistoryPage() {
  const { t, i18n } = useTranslation();
  const locale = i18n.language === 'ar' ? 'ar' : 'en';
  const { session } = useGuestSession(locale);

  const [runs, setRuns] = useState<RunRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState(false);
  const [filter, setFilter] = useState<string>('');
  const [experimentIds, setExperimentIds] = useState<string[]>([]);
  const [manifestsById, setManifestsById] = useState<Record<string, ExperimentManifest>>({});

  // Load experiments list + manifests (best-effort, not preview-blocking).
  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const list = await listExperiments();
        if (cancelled) return;
        setExperimentIds(list.ids);
        const mans = await Promise.all(list.ids.map((id) => getExperiment(id)));
        if (cancelled) return;
        const byId: Record<string, ExperimentManifest> = {};
        for (const m of mans) byId[m.id] = m;
        setManifestsById(byId);
      } catch {
        /* best-effort */
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  // Load runs once a guest session is available.
  useEffect(() => {
    if (!session) return;
    let cancelled = false;
    async function loadRuns() {
      setLoading(true);
      setError(null);
      try {
        const h = await listRuns(filter || undefined, 100);
        if (!cancelled) {
          setRuns(h.runs);
          setPreview(false);
        }
      } catch (err) {
        if (!cancelled) {
          setPreview(true);
          setError(err instanceof Error ? err.message : String(err));
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void loadRuns();
    return () => {
      cancelled = true;
    };
  }, [filter, session]);

  async function handleExport(runId: string, format: 'md' | 'json') {
    try {
      const res = await exportRun(runId, format);
      const blob = new Blob(
        [format === 'md' ? String(res.report) : JSON.stringify(res.report, null, 2)],
        { type: format === 'md' ? 'text/markdown' : 'application/json' },
      );
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${runId}.${format === 'md' ? 'md' : 'json'}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function handleReset(runId: string) {
    try {
      await resetRun(runId);
      const h = await listRuns(filter || undefined, 100);
      setRuns(h.runs);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <AppShell previewMode={preview}>
      <section className="page-heading" aria-labelledby="history-title">
        <div>
          <div className="eyebrow">{t('nav.history')}</div>
          <h1 id="history-title">{t('history.title')}</h1>
          <p>{t('history.subtitle')}</p>
        </div>
        <Status tone={preview ? 'amber' : 'green'}>
          {preview ? t('common.previewData') : `${runs.length} ${t('history.runHistory')}`}
        </Status>
      </section>

      {/* Filter toolbar */}
      <div className="toolbar">
        <div className="field">
          <Filter size={14} aria-hidden />
          <label className="muted whitespace-nowrap text-[11px] font-bold uppercase tracking-wide">
            {t('history.filterByExperiment')}
          </label>
          <select
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            aria-label={t('history.filterByExperiment')}
            data-testid="filter-experiment"
            className="flex-1"
          >
            <option value="">{t('experiments.filterAll')}</option>
            {experimentIds.map((id) => {
              const m = manifestsById[id];
              const label = m
                ? (locale === 'ar' ? m.title.ar : m.title.en)
                : id;
              return (
                <option key={id} value={id}>
                  {label}
                </option>
              );
            })}
          </select>
        </div>
      </div>

      {loading && (
        <p className="text-[13px] text-ink-500">{t('common.loading')}</p>
      )}
      {error && !preview && (
        <p role="alert" className="text-[13px] text-danger-600">
          {error}
        </p>
      )}

      {!loading && runs.length === 0 ? (
        <EmptyState
          icon={<FileText size={20} />}
          title={t('history.noRuns')}
        />
      ) : (
        <Card>
          <div className="table-wrap">
            <table data-testid="history-table">
              <thead>
                <tr>
                  <th>{t('history.runId')}</th>
                  <th>{t('history.experiment')}</th>
                  <th>{t('experiments.status')}</th>
                  <th>{t('experiments.traceId')}</th>
                  <th>{t('experiments.startedAt')}</th>
                  <th>{t('experiments.endedAt')}</th>
                  <th>{t('experiments.errorCode')}</th>
                  <th>{t('common.refresh')}</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((r) => (
                  <tr key={r.run_id} data-testid={`history-row-${r.run_id}`}>
                    <td>
                      <code className="text-[11px]">{r.run_id.slice(0, 8)}…</code>
                    </td>
                    <td>
                      {(() => {
                        const m = manifestsById[r.experiment_id];
                        return m ? (locale === 'ar' ? m.title.ar : m.title.en) : r.experiment_id;
                      })()}
                    </td>
                    <td>
                      <Status tone={verdictTone(r.status)}>{r.status}</Status>
                    </td>
                    <td>
                      {r.trace_id ? (
                        <code className="text-[11px]">{r.trace_id.slice(0, 8)}…</code>
                      ) : (
                        '—'
                      )}
                    </td>
                    <td className="text-ink-500">
                      {r.started_at ? new Date(r.started_at).toLocaleString() : '—'}
                    </td>
                    <td className="text-ink-500">
                      {r.ended_at ? new Date(r.ended_at).toLocaleString() : '—'}
                    </td>
                    <td className="text-ink-500">
                      {r.error_code ? (
                        <code className="text-[11px]">{r.error_code}</code>
                      ) : (
                        '—'
                      )}
                    </td>
                    <td>
                      <div className="flex flex-wrap gap-1">
                        <button
                          type="button"
                          aria-label="Export Markdown"
                          className="icon-btn"
                          onClick={() => handleExport(r.run_id, 'md')}
                          data-testid={`export-md-${r.run_id}`}
                        >
                          <Download size={12} />
                          MD
                        </button>
                        <button
                          type="button"
                          aria-label="Export JSON"
                          className="icon-btn"
                          onClick={() => handleExport(r.run_id, 'json')}
                          data-testid={`export-json-${r.run_id}`}
                        >
                          <Download size={12} />
                          JSON
                        </button>
                        <button
                          type="button"
                          aria-label={t('experiments.reset')}
                          className="icon-btn"
                          onClick={() => handleReset(r.run_id)}
                          data-testid={`reset-${r.run_id}`}
                        >
                          <RotateCcw size={12} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </AppShell>
  );
}
