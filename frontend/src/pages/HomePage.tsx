/**
 * HomePage — dashboard.
 *
 * Layout:
 *   - 4 stat cards (experiments count, passed runs, blocked runs, total runs)
 *   - Two-column: experiment preview grid (6 cards) + recent activity timeline
 *
 * Calls getModules + listRuns + getHealthReady. Falls back to PREVIEW mode
 * with FALLBACK_EXPERIMENTS_COMPACT when the backend is down.
 */
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  FlaskConical,
  CheckCircle2,
  AlertTriangle,
  ListChecks,
  ArrowRight,
  Clock,
} from 'lucide-react';
import { AppShell } from '../components/AppShell';
import { Card, StatCard, Status, Callout, verdictTone } from '../components/ui';
import {
  getModules,
  getHealthReady,
  listRuns,
  type ReadyResponse,
  type RunListResponse,
} from '../api/client';
import { FALLBACK_EXPERIMENTS_COMPACT } from '../data/fallbackExperiments';
import { useGuestSession } from '../hooks/useGuestSession';

interface HomeStats {
  experiments: number;
  passed: number;
  blocked: number;
  total: number;
}

export function HomePage() {
  const { t, i18n } = useTranslation();
  const locale = i18n.language === 'ar' ? 'ar' : 'en';
  const { session } = useGuestSession(locale);

  const [stats, setStats] = useState<HomeStats>({
    experiments: 0,
    passed: 0,
    blocked: 0,
    total: 0,
  });
  const [preview, setPreview] = useState(false);
  const [health, setHealth] = useState<ReadyResponse | null>(null);
  const [runs, setRuns] = useState<RunListResponse | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const next: HomeStats = { experiments: 0, passed: 0, blocked: 0, total: 0 };
      try {
        const modules = await getModules();
        next.experiments = modules.count;
      } catch {
        if (!cancelled) setPreview(true);
        next.experiments = FALLBACK_EXPERIMENTS_COMPACT.length;
      }
      try {
        const h = await getHealthReady();
        if (!cancelled) setHealth(h);
      } catch {
        /* health is best-effort */
      }
      try {
        const r = await listRuns(undefined, 50);
        if (!cancelled) {
          setRuns(r);
          next.total = r.count;
          for (const run of r.runs) {
            const s = (run.status || '').toUpperCase();
            if (s === 'PASSED') next.passed += 1;
            else if (s === 'BLOCKED') next.blocked += 1;
          }
        }
      } catch {
        /* runs are best-effort */
      }
      if (!cancelled) setStats(next);
    })();
    return () => {
      cancelled = true;
    };
  }, [session?.session_id]);

  const previewExperiments = FALLBACK_EXPERIMENTS_COMPACT.slice(0, 6);
  const recentRuns = runs?.runs.slice(0, 6) ?? [];

  return (
    <AppShell previewMode={preview}>
      <section className="page-heading" aria-labelledby="home-title">
        <div>
          <div className="eyebrow">{t('home.welcomeTitle')}</div>
          <h1 id="home-title">{t('home.hero')}</h1>
          <p>{t('home.description')}</p>
        </div>
        <Status tone={preview ? 'amber' : 'green'}>
          {preview ? t('common.previewData') : t('common.available')}
        </Status>
      </section>

      <section className="stats-grid" aria-label="Session statistics">
        <StatCard
          data-testid="stat-experiments"
          icon={<FlaskConical size={18} />}
          label={t('home.stats.canonicalExperiments')}
          value={stats.experiments}
        />
        <StatCard
          data-testid="stat-passed"
          icon={<CheckCircle2 size={18} />}
          iconTone="green"
          label={t('home.stats.passedRuns')}
          value={stats.passed}
        />
        <StatCard
          data-testid="stat-blocked"
          icon={<AlertTriangle size={18} />}
          iconTone="purple"
          label={t('home.stats.blockedRuns')}
          value={stats.blocked}
        />
        <StatCard
          data-testid="stat-total"
          icon={<ListChecks size={18} />}
          label={t('home.stats.totalRuns')}
          value={stats.total}
        />
      </section>

      <section className="two-col">
        <Card>
          <header className="mb-4 flex items-center justify-between">
            <h2 className="text-[16px] font-bold text-ink-900">
              {t('home.sections.exploreExperiments')}
            </h2>
            <Link className="text-link inline-flex items-center gap-1" to="/experiments">
              {t('home.sections.viewAll')}
              <ArrowRight size={12} />
            </Link>
          </header>
          <div className="exp-grid">
            {previewExperiments.map((e) => (
              <Link
                key={e.id}
                to="/experiments"
                className="exp-card card-hover block"
              >
                <div className="exp-thumb">
                  <span className="text-[10px] font-extrabold uppercase tracking-widest text-white/80">
                    {e.displayLabel}
                  </span>
                </div>
                <div className="exp-body">
                  <b>{locale === 'ar' ? e.title_ar : e.title_en}</b>
                  <p>{e.id}</p>
                  <div className="exp-foot">
                    <Status tone={levelTone(e.level)}>
                      {t(`experiments.level.${e.level}`)}
                    </Status>
                    <small>
                      {e.minutes} {t('common.minutes')}
                    </small>
                  </div>
                </div>
              </Link>
            ))}
          </div>

          <Callout title={t('home.sections.readyCalloutTitle')}>
            {t('home.sections.readyCalloutBody')}
          </Callout>
        </Card>

        <Card>
          <header className="mb-3 flex items-center justify-between">
            <h2 className="text-[16px] font-bold text-ink-900">
              {t('home.sections.recentActivity')}
            </h2>
            <Link className="text-link" to="/history">
              {t('history.runHistory')}
            </Link>
          </header>
          {recentRuns.length === 0 ? (
            <div className="muted py-6 text-center text-[12px]">
              {t('history.noRuns')}
            </div>
          ) : (
            <ul className="m-0 list-none p-0">
              {recentRuns.map((r) => (
                <li key={r.run_id} className="activity">
                  <span className="activity-icon">
                    <Clock size={14} />
                  </span>
                  <div>
                    <b>{r.experiment_id}</b>
                    <small>
                      {r.started_at
                        ? new Date(r.started_at).toLocaleString()
                        : t('common.notChecked')}
                    </small>
                  </div>
                  <Status tone={verdictTone(r.status)}>{r.status}</Status>
                </li>
              ))}
            </ul>
          )}
          {health && (
            <div className="info-line mt-2">
              <span>{t('environment.state')}</span>
              <Status tone={verdictTone(health.status)}>{health.status}</Status>
            </div>
          )}
        </Card>
      </section>
    </AppShell>
  );
}

function levelTone(level: string): 'green' | 'amber' | 'red' {
  if (level === 'beginner') return 'green';
  if (level === 'intermediate') return 'amber';
  return 'red';
}
