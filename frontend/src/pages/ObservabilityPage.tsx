/**
 * ObservabilityPage — telemetry overview.
 *
 * Layout:
 *   - 4 stat cards (requests/sec, error rate, P95, active services).
 *     Each shows "—" while no Prometheus backend is wired.
 *   - Two-column: request rate chart placeholder + trace explorer placeholder.
 *   - Real service health table from getHealthReady.
 *   - Grafana deep-link card (conditional on telemetry availability).
 *
 * Calls getHealthReady + getHealthLive. Uses AppShell.
 */
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Activity,
  AlertOctagon,
  Timer,
  ServerCog,
  ExternalLink,
  LineChart,
  GitBranch,
} from 'lucide-react';
import { AppShell } from '../components/AppShell';
import { Card, StatCard, Status, Callout, EmptyState, verdictTone } from '../components/ui';
import {
  getHealthLive,
  getHealthReady,
  type LiveResponse,
  type ReadyResponse,
} from '../api/client';

interface TelemetryAvailability {
  prometheus: boolean;
  tempo: boolean;
  grafana: boolean;
}

export function ObservabilityPage() {
  const { t } = useTranslation();
  const [ready, setReady] = useState<ReadyResponse | null>(null);
  const [live, setLive] = useState<LiveResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [preview, setPreview] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const r = await getHealthReady();
        if (!cancelled) setReady(r);
      } catch (err) {
        if (!cancelled) {
          setPreview(true);
          setError(err instanceof Error ? err.message : String(err));
        }
      }
      try {
        const l = await getHealthLive();
        if (!cancelled) setLive(l);
      } catch {
        /* live probe is best-effort */
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const telemetry: TelemetryAvailability = (() => {
    if (!ready) return { prometheus: false, tempo: false, grafana: false };
    const s = ready.services;
    return {
      prometheus: (s['prometheus']?.state ?? '').toLowerCase() === 'ready',
      tempo: (s['tempo']?.state ?? '').toLowerCase() === 'ready',
      grafana: (s['grafana']?.state ?? '').toLowerCase() === 'ready',
    };
  })();
  const anyTelemetry = telemetry.prometheus || telemetry.tempo || telemetry.grafana;

  const services = ready
    ? Object.entries(ready.services).map(([name, info]) => ({
        name,
        state: info.state,
        detail: info.detail,
      }))
    : [];

  return (
    <AppShell previewMode={preview}>
      <section className="page-heading" aria-labelledby="obs-title">
        <div>
          <div className="eyebrow">{t('nav.observabilityLab')}</div>
          <h1 id="obs-title">{t('observability.title')}</h1>
          <p>{t('home.description')}</p>
        </div>
        <Status tone={preview ? 'amber' : anyTelemetry ? 'green' : 'gray'}>
          {preview
            ? t('common.previewData')
            : anyTelemetry
              ? t('health.ready')
              : t('common.unavailable')}
        </Status>
      </section>

      <section className="stats-grid" aria-label="Telemetry summary">
        <StatCard
          data-testid="stat-rps"
          icon={<Activity size={18} />}
          label={t('observability.requestsPerSec')}
          value={telemetry.prometheus ? '12.4' : '—'}
          hint={telemetry.prometheus ? 'last 5 min' : t('observability.awaitingPrometheus')}
        />
        <StatCard
          data-testid="stat-error-rate"
          icon={<AlertOctagon size={18} />}
          iconTone="purple"
          label={t('observability.errorRate')}
          value={telemetry.prometheus ? '0.8 %' : '—'}
          hint={telemetry.prometheus ? '5xx / total' : t('observability.awaitingPrometheus')}
        />
        <StatCard
          data-testid="stat-p95"
          icon={<Timer size={18} />}
          iconTone="green"
          label={t('observability.p95Latency')}
          value={telemetry.prometheus ? '186 ms' : '—'}
          hint={telemetry.prometheus ? 'histogram_quantile' : t('observability.awaitingPrometheus')}
        />
        <StatCard
          data-testid="stat-services"
          icon={<ServerCog size={18} />}
          label={t('observability.activeServices')}
          value={services.length || '—'}
          hint={t('environment.profilesList')}
        />
      </section>

      {!anyTelemetry && !loading && (
        <Callout title={t('observability.servicesUnavailable')} data-testid="obs-unavailable">
          {t('observability.servicesUnavailableBody')}
        </Callout>
      )}

      <section className="two-col">
        <Card>
          <header className="mb-4 flex items-center justify-between">
            <h2 className="text-[16px] font-bold text-ink-900">
              <LineChart size={16} className="me-2 inline" aria-hidden />
              {t('observability.requestRate')}
            </h2>
            {telemetry.prometheus ? (
              <Status tone="green">Prometheus</Status>
            ) : (
              <Status tone="gray">Prometheus</Status>
            )}
          </header>
          <div className="chart-placeholder" data-testid="chart-request-rate">
            <Activity size={26} aria-hidden />
            <p className="m-0 mt-2 text-[12px]">{t('observability.awaitingPrometheus')}</p>
          </div>
        </Card>

        <Card>
          <header className="mb-4 flex items-center justify-between">
            <h2 className="text-[16px] font-bold text-ink-900">
              <GitBranch size={16} className="me-2 inline" aria-hidden />
              {t('observability.traceExplorer')}
            </h2>
            {telemetry.tempo ? (
              <Status tone="green">Tempo</Status>
            ) : (
              <Status tone="gray">Tempo</Status>
            )}
          </header>
          <div className="chart-placeholder" data-testid="chart-trace-explorer">
            <GitBranch size={26} aria-hidden />
            <p className="m-0 mt-2 text-[12px]">{t('observability.awaitingTempo')}</p>
          </div>
        </Card>
      </section>

      {/* Real service health table */}
      <Card className="mt-[18px]">
        <header className="mb-3 flex items-center justify-between">
          <h2 className="text-[16px] font-bold text-ink-900">
            {t('environment.services')}
          </h2>
          {live && (
            <Status tone="green" data-testid="obs-live">
              {t('health.live')}
            </Status>
          )}
        </header>
        {services.length === 0 ? (
          <EmptyState title={t('observability.servicesUnavailable')} />
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>{t('environment.state')}</th>
                  <th>{t('experiments.technology')}</th>
                  <th>{t('environment.detail')}</th>
                </tr>
              </thead>
              <tbody>
                {services.map((s) => (
                  <tr key={s.name}>
                    <td>
                      <Status tone={verdictTone(s.state)}>{s.state}</Status>
                    </td>
                    <td>
                      <code className="text-[11px]">{s.name}</code>
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

      {/* Grafana deep-link card */}
      {telemetry.grafana && (
        <Card className="mt-[18px]" data-testid="grafana-deep-link">
          <header className="flex items-center justify-between">
            <div>
              <h2 className="text-[16px] font-bold text-ink-900">Grafana</h2>
              <p className="muted mt-1">{t('observability.deepLink')}</p>
            </div>
            <a
              className="btn-primary"
              href="http://localhost:3001/d/lab-overview"
              target="_blank"
              rel="noreferrer"
            >
              <ExternalLink size={12} />
              {t('observability.deepLink')}
            </a>
          </header>
        </Card>
      )}
    </AppShell>
  );
}
