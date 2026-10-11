/**
 * HistoryPage — T20 (G05).
 *
 * Per the contract §4: `GET /api/v1/runs?experiment_id=&limit=` paginated/
 * scope-limited history.
 */
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  exportRun,
  getExperiment,
  listExperiments,
  listRuns,
  resetRun,
  type ExperimentManifest,
  type RunRecord,
} from '../api/client';

export function HistoryPage() {
  const { t } = useTranslation();
  const [runs, setRuns] = useState<RunRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<string>('');
  const [experimentIds, setExperimentIds] = useState<string[]>([]);
  const [, setManifestsById] = useState<Record<string, ExperimentManifest>>({});

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const list = await listExperiments();
        if (cancelled) return;
        setExperimentIds(list.ids);
        // Fetch manifests so we can show the experiment title.
        const mans = await Promise.all(list.ids.map((id) => getExperiment(id)));
        if (cancelled) return;
        const byId: Record<string, ExperimentManifest> = {};
        for (const m of mans) byId[m.id] = m;
        setManifestsById(byId);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : String(err));
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [setManifestsById]);

  useEffect(() => {
    let cancelled = false;
    async function loadRuns() {
      try {
        const h = await listRuns(filter || undefined, 100);
        if (!cancelled) setRuns(h.runs);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : String(err));
        }
      }
    }
    void loadRuns();
    return () => {
      cancelled = true;
    };
  }, [filter]);

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
    <main id="main-content" className="mx-auto max-w-6xl px-4 py-8" tabIndex={-1}>
      <h1 className="text-3xl font-semibold text-ink-900">
        {t('history.title')}
      </h1>
      <p className="mt-3 max-w-2xl text-sm text-ink-900/80">
        {t('history.description')}
      </p>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <label className="text-xs text-ink-900/70" htmlFor="filter-experiment">
          {t('history.filterByExperiment')}:
        </label>
        <select
          id="filter-experiment"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="rounded border border-ink-100 bg-white px-2 py-1 text-xs"
          data-testid="filter-experiment"
        >
          <option value="">—</option>
          {experimentIds.map((id) => (
            <option key={id} value={id}>
              {id}
            </option>
          ))}
        </select>
      </div>

      {loading && <p className="mt-6 text-sm text-ink-900/70">{t('common.loading')}</p>}
      {error && (
        <p role="alert" className="mt-6 text-sm text-red-700">
          {error}
        </p>
      )}
      {!loading && runs.length === 0 && (
        <p className="mt-6 text-sm text-ink-900/70">{t('history.noRuns')}</p>
      )}

      {runs.length > 0 && (
        <div className="mt-6 overflow-x-auto">
          <table className="w-full text-xs" data-testid="history-table">
            <thead>
              <tr className="border-b border-ink-100 text-left text-ink-900/70">
                <th className="py-2 pr-2">{t('experiments.runId')}</th>
                <th className="py-2 pr-2">{t('experiments.status')}</th>
                <th className="py-2 pr-2">{t('experiments.traceId')}</th>
                <th className="py-2 pr-2">{t('experiments.startedAt')}</th>
                <th className="py-2 pr-2">{t('experiments.endedAt')}</th>
                <th className="py-2 pr-2">{t('experiments.errorCode')}</th>
                <th className="py-2 pr-2">Actions</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.run_id} className="border-b border-ink-50">
                  <td className="py-2 pr-2">
                    <code className="text-[10px]">{r.run_id}</code>
                  </td>
                  <td className="py-2 pr-2">
                    <StatusBadge status={r.status} />
                  </td>
                  <td className="py-2 pr-2">
                    {r.trace_id ? (
                      <code className="text-[10px]">{r.trace_id.slice(0, 8)}…</code>
                    ) : (
                      '—'
                    )}
                  </td>
                  <td className="py-2 pr-2 text-ink-900/70">
                    {r.started_at ? new Date(r.started_at).toLocaleString() : '—'}
                  </td>
                  <td className="py-2 pr-2 text-ink-900/70">
                    {r.ended_at ? new Date(r.ended_at).toLocaleString() : '—'}
                  </td>
                  <td className="py-2 pr-2 text-ink-900/70">
                    {r.error_code ? (
                      <code className="text-[10px]">{r.error_code}</code>
                    ) : (
                      '—'
                    )}
                  </td>
                  <td className="py-2 pr-2">
                    <div className="flex flex-wrap gap-1">
                      <button
                        type="button"
                        onClick={() => handleExport(r.run_id, 'md')}
                        className="rounded border border-ink-100 bg-white px-2 py-0.5 text-[10px]"
                      >
                        MD
                      </button>
                      <button
                        type="button"
                        onClick={() => handleExport(r.run_id, 'json')}
                        className="rounded border border-ink-100 bg-white px-2 py-0.5 text-[10px]"
                      >
                        JSON
                      </button>
                      <button
                        type="button"
                        onClick={() => handleReset(r.run_id)}
                        className="rounded border border-ink-100 bg-white px-2 py-0.5 text-[10px]"
                      >
                        {t('experiments.reset')}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    PASSED: 'bg-green-50 text-green-800',
    FAILED: 'bg-red-50 text-red-800',
    BLOCKED: 'bg-amber-50 text-amber-800',
    RUNNING: 'bg-blue-50 text-blue-800',
    CREATED: 'bg-ink-50 text-ink-900',
  };
  const cls = colors[status] || 'bg-ink-50 text-ink-900';
  return (
    <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${cls}`}>
      {status}
    </span>
  );
}
