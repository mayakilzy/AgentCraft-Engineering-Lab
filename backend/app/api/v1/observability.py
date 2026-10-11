"""Observability endpoints — T15.

Per the architecture contract §4 + §7:
- `GET /api/v1/observability/links/{run_id}` returns safe configured
  dashboards or internal status, never privileged URL credentials.
- `GET /api/v1/observability/metrics-summary` returns a bounded aggregate
  the frontend can render without needing to scrape Prometheus directly.
- `GET /api/v1/observability/trace/{run_id}` returns the trace_id
  correlated with a run, so the user can follow a request → processing → DB.

No Grafana credentials are ever returned; only a deep-link to a
configured base URL. When Grafana is not configured, the endpoint
honestly reports `grafana_url: null`.
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.deps import SettingsDep
from app.core.metrics import _registry
from prometheus_client.parser import text_string_to_metric_families
import io

router = APIRouter(prefix="/observability", tags=["observability"])


class TraceLink(BaseModel):
    run_id: str
    trace_id: str | None
    grafana_url: str | None
    grafana_tempo_query: str | None
    note: str


class MetricsSummary(BaseModel):
    """Bounded aggregate the frontend renders without scraping Prometheus.
    Labels are the bounded set (method, path_template, status) — no PII."""
    http_requests_total: float
    http_request_duration_seconds_p50: float | None
    http_request_duration_seconds_p95: float | None
    lab_runs_total: float
    lab_runs_by_status: dict[str, float]
    prometheus_url: str | None
    grafana_url: str | None
    tempo_url: str | None
    note: str


@router.get("/links/{run_id}", response_model=TraceLink)
def get_trace_links(run_id: str, settings: SettingsDep) -> TraceLink:
    """Return safe deep-links for tracing a run.

    The trace_id is read from the run record's stored trace_id (wired in
    G05/G06 when runs are persisted; for G04 we return null and the
    frontend uses the x-trace-id response header captured at request time).

    Grafana deep-link: `{grafana_url}/explore?left=...` — a read-only
    Tempo query by trace_id. No credentials included.
    """
    grafana = settings.grafana_url
    tempo_query = None
    if grafana:
        # Build a safe read-only Tempo explore URL. The trace_id is
        # populated by the caller (or null if not yet captured).
        tempo_query = (
            f"{grafana}/explore?left="
            '{"datasource":"tempo","queries":[{"query":"${{traceId}}"}],'
            '"range":{"from":"now-1h","to":"now"}}'
        )
    return TraceLink(
        run_id=run_id,
        trace_id=None,  # populated when runs are persisted (G05+)
        grafana_url=grafana,
        grafana_tempo_query=tempo_query,
        note=(
            "trace_id is populated from the run record when available. "
            "Grafana deep-link is read-only; no credentials returned."
        ),
    )


@router.get("/metrics-summary", response_model=MetricsSummary)
def get_metrics_summary(settings: SettingsDep) -> MetricsSummary:
    """Return a bounded metrics summary for the frontend Observability Lab.

    This is a SAFE alternative to exposing the raw /metrics endpoint to
    the browser (which would leak internal route patterns). The summary
    aggregates to totals + p50/p95, bounded by the metric definitions.
    """
    # Render the registry and parse it back so we can compute aggregates.
    from app.core.metrics import render_metrics
    raw = render_metrics().decode("utf-8")
    families = list(text_string_to_metric_families(raw))

    http_total = 0.0
    lab_total = 0.0
    lab_by_status: dict[str, float] = {}
    durations: list[float] = []

    for fam in families:
        # The prometheus_client parser strips the `_total` suffix from
        # counter family names (per Prometheus convention), so
        # `agentcraft_http_requests_total` becomes `agentcraft_http_requests`.
        if fam.name in ("agentcraft_http_requests_total", "agentcraft_http_requests"):
            for sample in fam.samples:
                # Only count the `_total` samples, not `_created`.
                if sample.name.endswith("_total"):
                    http_total += sample.value
        elif fam.name in ("agentcraft_lab_runs_total", "agentcraft_lab_runs"):
            for sample in fam.samples:
                if sample.name.endswith("_total"):
                    lab_total += sample.value
                    status = sample.labels.get("status", "unknown")
                    lab_by_status[status] = lab_by_status.get(status, 0.0) + sample.value
        elif fam.name == "agentcraft_http_request_duration_seconds":
            for sample in fam.samples:
                if sample.name.endswith("_sum"):
                    durations.append(sample.value)

    p50 = sorted(durations)[len(durations) // 2] if durations else None
    p95_idx = int(len(durations) * 0.95)
    p95 = sorted(durations)[min(p95_idx, len(durations) - 1)] if durations else None

    return MetricsSummary(
        http_requests_total=http_total,
        http_request_duration_seconds_p50=p50,
        http_request_duration_seconds_p95=p95,
        lab_runs_total=lab_total,
        lab_runs_by_status=lab_by_status,
        prometheus_url=settings.prometheus_url,
        grafana_url=settings.grafana_url,
        tempo_url=settings.tempo_url,
        note=(
            "Aggregated metrics summary. Bounded labels only "
            "(method, path_template, status, operation). No PII. "
            "When Prometheus/Grafana are not configured, the URLs are null "
            "and the frontend shows the local summary only."
        ),
    )
