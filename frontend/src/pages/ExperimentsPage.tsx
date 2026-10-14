/**
 * ExperimentsPage — gallery of all 10 canonical experiments.
 *
 * Per the architecture contract §1 + A09: cards, levels, stepper,
 * prerequisites, expected/actual and mode switch; no direct code execution.
 *
 * Loads the 10 experiment manifests from the backend, displays each as
 * a card with run/rerun/reset/compare/export controls, and provides a
 * compare panel for selecting two runs. Uses AppShell. Falls back to
 * FALLBACK_MANIFESTS in preview mode.
 */
import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Search, Filter } from 'lucide-react';
import {
  compareRuns,
  getExperiment,
  listExperiments,
  type CompareResponse,
  type ExperimentManifest,
} from '../api/client';
import { ExperimentCard } from '../components/ExperimentCard';
import { AppShell } from '../components/AppShell';
import { Card, Status } from '../components/ui';
import { FALLBACK_MANIFESTS } from '../data/fallbackExperiments';

const LEVELS = ['all', 'beginner', 'intermediate', 'advanced'] as const;
type LevelFilter = (typeof LEVELS)[number];

export function ExperimentsPage() {
  const { t, i18n } = useTranslation();
  const locale = (i18n.language === 'ar' ? 'ar' : 'en') as 'en' | 'ar';

  const [manifests, setManifests] = useState<ExperimentManifest[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState(false);
  const [selectedForCompare, setSelectedForCompare] = useState<string[]>([]);
  const [compareResult, setCompareResult] = useState<CompareResponse | null>(null);
  const [search, setSearch] = useState('');
  const [levelFilter, setLevelFilter] = useState<LevelFilter>('all');

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
          setPreview(true);
          setManifests(FALLBACK_MANIFESTS);
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
    const q = search.trim().toLowerCase();
    return [...manifests]
      .filter((m) => {
        if (levelFilter !== 'all' && m.level !== levelFilter) return false;
        if (!q) return true;
        const title = (locale === 'ar' ? m.title.ar : m.title.en).toLowerCase();
        return (
          title.includes(q) ||
          m.id.toLowerCase().includes(q) ||
          m.technology.some((tech) => tech.toLowerCase().includes(q))
        );
      })
      .sort((a, b) => {
        const la = levelOrder[a.level] ?? 99;
        const lb = levelOrder[b.level] ?? 99;
        if (la !== lb) return la - lb;
        return a.id.localeCompare(b.id);
      });
  }, [manifests, levelFilter, search, locale]);

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
    <AppShell previewMode={preview}>
      <section className="page-heading" aria-labelledby="experiments-title">
        <div>
          <div className="eyebrow">{t('nav.experiments')}</div>
          <h1 id="experiments-title">{t('experiments.title')}</h1>
          <p>{t('experiments.description')}</p>
        </div>
        <Status tone={preview ? 'amber' : 'green'}>
          {preview ? t('common.previewData') : `${manifests.length} ${t('experiments.experimentCount')}`}
        </Status>
      </section>

      {/* Toolbar: search + level filter */}
      <div className="toolbar">
        <div className="field">
          <Search size={14} aria-hidden />
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={t('experiments.searchPlaceholder')}
            aria-label={t('experiments.searchPlaceholder')}
            data-testid="experiments-search"
          />
        </div>
        <div className="segmented" role="group" aria-label="Level filter">
          <Filter size={14} className="me-1" aria-hidden />
          {LEVELS.map((lv) => (
            <button
              key={lv}
              type="button"
              className={levelFilter === lv ? 'selected' : ''}
              aria-pressed={levelFilter === lv}
              onClick={() => setLevelFilter(lv)}
              data-testid={`experiments-filter-${lv}`}
            >
              {lv === 'all' ? t('experiments.filterAll') : t(`experiments.level.${lv}`)}
            </button>
          ))}
        </div>
      </div>

      {loading && (
        <p className="text-[13px] text-ink-500" data-testid="loading-experiments">
          {t('common.loading')}
        </p>
      )}

      {error && !preview && (
        <p role="alert" className="text-[13px] text-danger-600">
          {t('experiments.failedToLoad')}: {error}
        </p>
      )}

      {!loading && sorted.length === 0 && (
        <p className="text-[13px] text-ink-500">{t('experiments.noExperiments')}</p>
      )}

      {!loading && sorted.length > 0 && (
        <>
          <div className="exp-grid">
            {sorted.map((m, i) => (
              <ExperimentCard
                key={m.id}
                manifest={m}
                locale={locale}
                selectedForCompare={selectedForCompare}
                onCompareSelect={onCompareSelect}
                displayLabel={`E${String(i + 1).padStart(2, '0')}`}
              />
            ))}
          </div>

          {/* Compare panel */}
          <Card className="mt-[18px]">
            <h2 className="text-[16px] font-bold text-ink-900">
              {t('experiments.compare')}
            </h2>
            <p className="mt-1 text-[12px] text-ink-500">
              {t('experiments.selectToCompare')}
            </p>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              {selectedForCompare.map((id, i) => (
                <code
                  key={id}
                  className="rounded-btn bg-surface-subtle px-2 py-1 text-[10px] text-ink-600"
                >
                  {i + 1}: {id.slice(0, 8)}…
                </code>
              ))}
              <button
                type="button"
                onClick={handleCompare}
                disabled={selectedForCompare.length !== 2}
                className="btn-primary"
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
                  className="btn-secondary"
                >
                  {t('history.clearSelection')}
                </button>
              )}
            </div>
            {compareResult && (
              <div
                className="mt-4 rounded-btn bg-surface-subtle p-3 text-[12px]"
                data-testid="compare-results"
              >
                <h3 className="font-bold text-ink-900">
                  {t('experiments.compareResults')}
                </h3>
                <dl className="mt-2 grid grid-cols-3 gap-2">
                  <div className="rounded-btn bg-white p-2">
                    <dt className="text-[10px] text-ink-500">
                      {t('experiments.sameExperiment')}
                    </dt>
                    <dd className="mt-0.5 text-[14px] font-bold">
                      {compareResult.same_experiment ? '✓' : '✗'}
                    </dd>
                  </div>
                  <div className="rounded-btn bg-white p-2">
                    <dt className="text-[10px] text-ink-500">
                      {t('experiments.sameStatus')}
                    </dt>
                    <dd className="mt-0.5 text-[14px] font-bold">
                      {compareResult.same_final_status ? '✓' : '✗'}
                    </dd>
                  </div>
                  <div className="rounded-btn bg-white p-2">
                    <dt className="text-[10px] text-ink-500">
                      {t('experiments.sameStepCount')}
                    </dt>
                    <dd className="mt-0.5 text-[14px] font-bold">
                      {compareResult.same_step_count ? '✓' : '✗'}
                    </dd>
                  </div>
                </dl>
                <p className="mt-2 text-ink-500">{compareResult.note}</p>
                {compareResult.step_diffs.length > 0 && (
                  <div className="mt-3">
                    <h4 className="text-[10px] font-bold text-ink-500">
                      {t('experiments.steps')}
                    </h4>
                    <table className="mt-1 w-full text-[10px]">
                      <thead>
                        <tr>
                          <th>#</th>
                          <th>{t('experiments.step')}</th>
                          <th>A {t('experiments.verdict')}</th>
                          <th>B {t('experiments.verdict')}</th>
                          <th>Match</th>
                        </tr>
                      </thead>
                      <tbody>
                        {compareResult.step_diffs.map((d, i) => (
                          <tr
                            key={i}
                            className={d.same_verdict === false ? 'bg-warn-50' : ''}
                          >
                            <td>{i + 1}</td>
                            <td>{String(d.step_id ?? '-')}</td>
                            <td>{String(d.a_passed ?? '-')}</td>
                            <td>{String(d.b_passed ?? '-')}</td>
                            <td>
                              {d.same_verdict === true ? '✓' : d.same_verdict === false ? '✗' : '?'}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )}
          </Card>
        </>
      )}
    </AppShell>
  );
}
