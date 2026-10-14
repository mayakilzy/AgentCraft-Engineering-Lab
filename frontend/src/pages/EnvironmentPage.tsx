/**
 * EnvironmentPage — Lab Environment overview.
 *
 * Layout:
 *   - 4 summary stat cards (ready / degraded / not_ready / total).
 *   - Real service health table from getHealthReady + getHealthLive.
 *   - Deployment profiles card (core / neo4j / observability / test).
 *   - Re-probe button (re-runs the ready + live fetches).
 *
 * Calls getHealthReady + getHealthLive. Uses AppShell.
 */
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { RefreshCw, CheckCircle2, AlertTriangle, XCircle, Layers } from 'lucide-react';
import { AppShell } from '../components/AppShell';
import { Card, StatCard, Status, Callout, EmptyState, verdictTone } from '../components/ui';
import {
  getHealthLive,
  getHealthReady,
  type LiveResponse,
  type ReadyResponse,
} from '../api/client';

interface ServiceRow {
  name: string;
  state: string;
  detail: string | null;
}

const PROFILES = [
  { id: 'core', label: 'core', description: 'FastAPI + uvicorn workers' },
  { id: 'neo4j', label: 'neo4j', description: 'graph store + GDS plugin (optional)' },
  { id: 'observability', label: 'observability', description: 'Prometheus · Tempo · Grafana' },
  { id: 'test', label: 'test', description: 'pytest + Vitest + integration suite' },
];

export function EnvironmentPage() {
  const { t } = useTranslation();
  const [ready, setReady] = useState<ReadyResponse | null>(null);
  const [live, setLive] = useState<LiveResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [probing, setProbing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState(false);
  const [lastChecked, setLastChecked] = useState<Date | null>(null);

  async function probe() {
    setProbing(true);
    setError(null);
    try {
      const r = await getHealthReady();
      setReady(r);
      setPreview(false);
    } catch (err) {
      setPreview(true);
      setError(err instanceof Error ? err.message : String(err));
    }
    try {
      const l = await getHealthLive();
      setLive(l);
    } catch {
      /* live probe is best-effort */
    } finally {
      setLastChecked(new Date());
      setProbing(false);
      setLoading(false);
    }
  }

  useEffect(() => {
    void probe();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const services: ServiceRow[] = ready
    ? Object.entries(ready.services).map(([name, info]) => ({
        name,
        state: info.state,
        detail: info.detail,
      }))
    : [];

  const counts = services.reduce(
    (acc, s) => {
      const key = (s.state || '').toLowerCase();
      if (key === 'ready') acc.ready += 1;
      else if (key === 'degraded') acc.degraded += 1;
      else if (key === 'not_ready' || key === 'notready') acc.notReady += 1;
      acc.total += 1;
      return acc;
    },
    { ready: 0, degraded: 0, notReady: 0, total: 0 },
  );

  return (
    <AppShell previewMode={preview}>
      <section className="page-heading" aria-labelledby="env-title">
        <div>
          <div className="eyebrow">{t('nav.environment')}</div>
          <h1 id="env-title">{t('environment.title')}</h1>
          <p>{t('environment.profilesList')}</p>
        </div>
        <button
          type="button"
          className="btn-secondary"
          onClick={() => void probe()}
          disabled={probing}
          data-testid="env-reprobe"
        >
          <RefreshCw size={12} className={probing ? 'animate-spin' : ''} />
          {probing ? t('environment.probingServices') : t('environment.refresh')}
        </button>
      </section>

      <section className="stats-grid" aria-label="Service health summary">
        <StatCard
          data-testid="env-ready"
          icon={<CheckCircle2 size={18} />}
          iconTone="green"
          label={t('health.ready')}
          value={counts.ready}
        />
        <StatCard
          data-testid="env-degraded"
          icon={<AlertTriangle size={18} />}
          iconTone="purple"
          label={t('health.degraded')}
          value={counts.degraded}
        />
        <StatCard
          data-testid="env-not-ready"
          icon={<XCircle size={18} />}
          label={t('health.notReady')}
          value={counts.notReady}
        />
        <StatCard
          data-testid="env-total"
          icon={<Layers size={18} />}
          label={t('environment.services')}
          value={counts.total}
        />
      </section>

      <Card>
        <header className="mb-3 flex items-center justify-between">
          <h2 className="text-[16px] font-bold text-ink-900">
            {t('environment.services')}
          </h2>
          <div className="flex items-center gap-3">
            {live && (
              <Status tone="green">{t('health.live')}</Status>
            )}
            {lastChecked && (
              <small className="muted">
                {t('environment.lastChecked')}: {lastChecked.toLocaleTimeString()}
              </small>
            )}
          </div>
        </header>
        {loading ? (
          <p className="text-[13px] text-ink-500">{t('environment.probingServices')}</p>
        ) : services.length === 0 ? (
          <EmptyState title={t('observability.servicesUnavailable')} />
        ) : (
          <div className="table-wrap">
            <table data-testid="env-services-table">
              <thead>
                <tr>
                  <th>{t('experiments.technology')}</th>
                  <th>{t('environment.state')}</th>
                  <th>{t('environment.detail')}</th>
                </tr>
              </thead>
              <tbody>
                {services.map((s) => (
                  <tr key={s.name} data-testid={`env-service-${s.name}`}>
                    <td>
                      <code className="text-[11px]">{s.name}</code>
                    </td>
                    <td>
                      <Status tone={verdictTone(s.state)}>{s.state}</Status>
                    </td>
                    <td className="text-ink-500">{s.detail ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {error && (
          <p role="alert" className="mt-3 text-[12px] text-danger-600">
            {error}
          </p>
        )}
      </Card>

      <Card className="mt-[18px]">
        <header className="mb-3">
          <h2 className="text-[16px] font-bold text-ink-900">
            {t('environment.deploymentProfiles')}
          </h2>
        </header>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {PROFILES.map((p) => (
            <div
              key={p.id}
              className="rounded-btn border border-ink-200 bg-surface-subtle p-4"
              data-testid={`env-profile-${p.id}`}
            >
              <div className="text-[12px] font-extrabold uppercase tracking-wide text-brand-700">
                {p.label}
              </div>
              <p className="mt-1 text-[11px] text-ink-500">{p.description}</p>
            </div>
          ))}
        </div>
        <Callout>{t('environment.healthNote')}</Callout>
      </Card>
    </AppShell>
  );
}
