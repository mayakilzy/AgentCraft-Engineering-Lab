/**
 * ExperimentsPage — T20 (G05).
 *
 * Per the architecture contract §1 + A09: cards, levels, stepper,
 * prerequisites, expected/actual and mode switch; no direct code execution.
 *
 * Loads the 10 experiment manifests from the backend, displays each as
 * a card with run/rerun/reset/compare/export controls, and provides a
 * compare panel for selecting two runs.
 */
import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  compareRuns,
  getExperiment,
  listExperiments,
  type CompareResponse,
  type ExperimentManifest,
} from '../api/client';
import { ExperimentCard } from '../components/ExperimentCard';

export function ExperimentsPage() {
  const { t, i18n } = useTranslation();
  const locale = (i18n.language === 'ar' ? 'ar' : 'en') as 'en' | 'ar';

  const [manifests, setManifests] = useState<ExperimentManifest[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedForCompare, setSelectedForCompare] = useState<string[]>([]);
  const [compareResult, setCompareResult] = useState<CompareResponse | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const list = await listExperiments();
        const fetched = await Promise.all(
          list.ids.map((id) => getExperiment(id)),
        );
        if (!cancelled) {
          setManifests(fetched);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : String(err));
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  // Sort by level then by id so the gallery has a stable, useful order.
  const sorted = useMemo(() => {
    const levelOrder: Record<string, number> = {
      beginner: 0,
      intermediate: 1,
      advanced: 2,
    };
    return [...manifests].sort((a, b) => {
      const la = levelOrder[a.level] ?? 99;
      const lb = levelOrder[b.level] ?? 99;
      if (la !== lb) return la - lb;
      return a.id.localeCompare(b.id);
    });
  }, [manifests]);

  function onCompareSelect(runId: string) {
    setSelectedForCompare((prev) => {
      if (prev.includes(runId)) {
        return prev.filter((r) => r !== runId);
      }
      if (prev.length >= 2) {
        return [prev[1], runId];
      }
      return [...prev, runId];
    });
  }

  async function handleCompare() {
    if (selectedForCompare.length !== 2) return;
    try {
      const result = await compareRuns(selectedForCompare[0], selectedForCompare[1]);
      setCompareResult(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <main
      id="main-content"
      className="mx-auto max-w-6xl px-4 py-8"
      tabIndex={-1}
    >
      <h1 className="text-3xl font-semibold text-ink-900">
        {t('experiments.title')}
      </h1>
      <p className="mt-3 max-w-2xl text-sm text-ink-900/80">
        {t('experiments.description')}
      </p>

      {loading && (
        <p className="mt-6 text-sm text-ink-900/70" data-testid="loading-experiments">
          {t('common.loading')}
        </p>
      )}

      {error && (
        <p role="alert" className="mt-6 text-sm text-red-700">
          {t('experiments.failedToLoad')}: {error}
        </p>
      )}

      {!loading && !error && manifests.length === 0 && (
        <p className="mt-6 text-sm text-ink-900/70">
          {t('experiments.noExperiments')}
        </p>
      )}

      {!loading && !error && manifests.length > 0 && (
        <>
          <div className="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-2">
            {sorted.map((m) => (
              <ExperimentCard
                key={m.id}
                manifest={m}
                locale={locale}
                selectedForCompare={selectedForCompare}
                onCompareSelect={onCompareSelect}
              />
            ))}
          </div>

          {/* Compare panel */}
          <section className="mt-6 rounded border border-ink-100 bg-white p-4">
            <h2 className="text-lg font-semibold text-ink-900">
              {t('experiments.compare')}
            </h2>
            <p className="mt-1 text-xs text-ink-900/70">
              {t('experiments.selectToCompare')}
            </p>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              {selectedForCompare.map((id, i) => (
                <code
                  key={id}
                  className="rounded bg-ink-50 px-2 py-1 text-[10px] text-ink-900/70"
                >
                  {i + 1}: {id.slice(0, 8)}…
                </code>
              ))}
              <button
                type="button"
                onClick={handleCompare}
                disabled={selectedForCompare.length !== 2}
                className="rounded bg-ink-900 px-3 py-1 text-xs font-medium text-white disabled:opacity-50"
                data-testid="compare-button"
              >
                {t('experiments.compare')}
              </button>
              {selectedForCompare.length > 0 && (
                <button
                  type="button"
                  onClick={() => {
                    setSelectedForCompare([]);
                    setCompareResult(null);
                  }}
                  className="rounded border border-ink-100 bg-white px-3 py-1 text-xs"
                >
                  Clear
                </button>
              )}
            </div>
            {compareResult && (
              <div
                className="mt-4 rounded bg-ink-50 p-3 text-xs"
                data-testid="compare-results"
              >
                <h3 className="font-medium text-ink-900">
                  {t('experiments.compareResults')}
                </h3>
                <dl className="mt-2 grid grid-cols-2 gap-2">
                  <div>
                    <dt className="text-ink-900/60">
                      {t('experiments.sameExperiment')}
                    </dt>
                    <dd>{String(compareResult.same_experiment)}</dd>
                  </div>
                  <div>
                    <dt className="text-ink-900/60">
                      {t('experiments.sameStatus')}
                    </dt>
                    <dd>{String(compareResult.same_final_status)}</dd>
                  </div>
                  <div>
                    <dt className="text-ink-900/60">
                      {t('experiments.sameStepCount')}
                    </dt>
                    <dd>{String(compareResult.same_step_count)}</dd>
                  </div>
                </dl>
                <p className="mt-2 text-ink-900/70">{compareResult.note}</p>
                <details className="mt-2">
                  <summary className="cursor-pointer text-ink-900/70">
                    {t('experiments.steps')} ({compareResult.step_diffs.length})
                  </summary>
                  <pre className="mt-1 overflow-x-auto rounded bg-white p-2 text-[10px]">
                    {JSON.stringify(compareResult.step_diffs, null, 2)}
                  </pre>
                </details>
              </div>
            )}
          </section>
        </>
      )}
    </main>
  );
}
