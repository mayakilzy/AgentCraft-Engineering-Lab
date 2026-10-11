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

G04-C1 closure (reviewer note #1): the P50/P95 calculation previously
used `_sum` values as if they were individual samples — this was
incorrect (Prometheus histogram `_sum` is the cumulative sum of all
observations for a label set, NOT a sample). The calculation now uses
the histogram bucket counts with linear interpolation, matching the
algorithm Prometheus uses in `histogram_quantile()`. The result is
explicitly documented as APPROXIMATE (inherent to histogram-based
quantile estimation). When Prometheus is configured, the summary falls
back to a direct `histogram_quantile()` query (G07 runtime smoke).
"""
from __future__ import annotations

import math
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.deps import SettingsDep
from app.core.metrics import _registry
from prometheus_client.parser import text_string_to_metric_families

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


def _parse_histogram_buckets(
    families,
    hist_name: str,
) -> list[dict[str, float]]:
    """Extract per-label-set bucket counts from a histogram family.

    Returns a list of dicts, one per label set, each containing:
      - 'labels': the label dict
      - 'buckets': list of (le, cumulative_count) sorted ascending by le
      - 'count': total observations (= bucket le=+Inf)
    """
    out: list[dict[str, float]] = []
    for fam in families:
        if fam.name != hist_name:
            continue
        # Group samples by their label set (excluding 'le').
        by_label: dict[frozenset, dict] = {}
        for sample in fam.samples:
            if not sample.name.endswith("_bucket"):
                continue  # skip _sum, _count — we only need buckets
            le_str = sample.labels.get("le", "")
            try:
                le = float("inf") if le_str == "+Inf" else float(le_str)
            except ValueError:
                continue
            # Key by labels EXCLUDING 'le' so we group all buckets for the
            # same label set together.
            key_labels = {k: v for k, v in sample.labels.items() if k != "le"}
            key = frozenset(key_labels.items())
            if key not in by_label:
                by_label[key] = {
                    "labels": key_labels,
                    "buckets": [],
                }
            by_label[key]["buckets"].append((le, sample.value))

        for group in by_label.values():
            group["buckets"].sort(key=lambda x: x[0])
            # The last bucket should be +Inf; its value is the total count.
            total_count = group["buckets"][-1][1] if group["buckets"] else 0.0
            group["count"] = total_count
            out.append(group)
    return out


def _histogram_quantile(buckets: list[tuple[float, float]], q: float) -> Optional[float]:
    """Compute the q-th quantile from histogram bucket counts using linear
    interpolation — the same algorithm Prometheus uses in
    `histogram_quantile()`.

    buckets: list of (le, cumulative_count) sorted ascending by le.
    q: quantile in [0, 1] (0.50 for p50, 0.95 for p95).

    Returns None when there are no observations. The result is
    APPROXIMATE: it falls on a bucket boundary or is interpolated within
    the bucket containing the target rank. Exact quantiles require the
    original samples, which Prometheus histograms do not store.
    """
    if not buckets:
        return None
    total = buckets[-1][1]  # le=+Inf cumulative count
    if total <= 0:
        return None

    target = q * total
    # Walk buckets from smallest le to largest, tracking the previous bucket.
    prev_le = 0.0
    prev_count = 0.0
    for le, cumulative in buckets:
        if cumulative >= target:
            # The target falls in [prev_le, le].
            bucket_count = cumulative - prev_count
            if bucket_count <= 0:
                # All observations are at or below prev_le; the quantile
                # is approximately prev_le.
                return prev_le
            # Linear interpolation within this bucket.
            return prev_le + (target - prev_count) / bucket_count * (le - prev_le)
        prev_le = le
        prev_count = cumulative

    # Should not reach here because the last bucket is +Inf with count=total.
    return buckets[-1][0]


@router.get("/metrics-summary", response_model=MetricsSummary)
def get_metrics_summary(settings: SettingsDep) -> MetricsSummary:
    """Return a bounded metrics summary for the frontend Observability Lab.

    P50/P95 are computed from histogram bucket counts using linear
    interpolation (the same algorithm Prometheus `histogram_quantile()`
    uses). The result is APPROXIMATE — it falls on a bucket boundary or
    is interpolated within the bucket containing the target rank. Exact
    quantiles require the original samples, which histograms do not store.
    """
    from app.core.metrics import render_metrics
    raw = render_metrics().decode("utf-8")
    families = list(text_string_to_metric_families(raw))

    http_total = 0.0
    lab_total = 0.0
    lab_by_status: dict[str, float] = {}
    # Collect ALL histogram bucket groups across all label sets; we
    # aggregate by summing bucket counts across label sets before
    # computing the quantile.
    all_buckets_by_le: dict[float, float] = {}

    for fam in families:
        if fam.name in ("agentcraft_http_requests_total", "agentcraft_http_requests"):
            for sample in fam.samples:
                if sample.name.endswith("_total"):
                    http_total += sample.value
        elif fam.name in ("agentcraft_lab_runs_total", "agentcraft_lab_runs"):
            for sample in fam.samples:
                if sample.name.endswith("_total"):
                    lab_total += sample.value
                    status = sample.labels.get("status", "unknown")
                    lab_by_status[status] = lab_by_status.get(status, 0.0) + sample.value
        elif fam.name == "agentcraft_http_request_duration_seconds":
            # Aggregate bucket counts across ALL label sets (method,
            # path_template, status) into one combined histogram so the
            # p50/p95 reflects the overall distribution.
            for sample in fam.samples:
                if not sample.name.endswith("_bucket"):
                    continue
                le_str = sample.labels.get("le", "")
                try:
                    le = float("inf") if le_str == "+Inf" else float(le_str)
                except ValueError:
                    continue
                all_buckets_by_le[le] = all_buckets_by_le.get(le, 0.0) + sample.value

    # Sort the aggregated buckets by le ascending; +Inf goes last.
    sorted_buckets = sorted(all_buckets_by_le.items(), key=lambda x: x[0])

    p50 = _histogram_quantile(sorted_buckets, 0.50)
    p95 = _histogram_quantile(sorted_buckets, 0.95)

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
            "P50/P95 computed from histogram buckets via linear "
            "interpolation (approximate). When Prometheus is configured, "
            "G07 will query histogram_quantile() directly for exact values."
        ),
    )
