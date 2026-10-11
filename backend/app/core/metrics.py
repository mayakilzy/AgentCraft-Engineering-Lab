"""Prometheus metrics — bounded cardinality, no sensitive data.

Per the architecture contract §9 + reviewer note #4:
- Labels use bounded sets: HTTP method, path template (e.g. "/api/v1/graph/{dataset_id}"),
  status code. These are bounded by the route table, not by user input.
- run_id and session_id are NEVER metric labels (would explode cardinality).
- They are attached ONLY to trace spans (TTL-bounded in Tempo).
- A `/metrics` endpoint exposes the registry for Prometheus scraping.
"""
from __future__ import annotations

from prometheus_client import Counter, Histogram, CollectorRegistry, generate_latest

# Use a dedicated registry so we never accidentally pick up process metrics
# that could leak host info (reviewer note #4: no sensitive data).
_registry = CollectorRegistry()

# HTTP request counter. `path_template` is the FastAPI route pattern
# (e.g. "/api/v1/graph/{dataset_id}"), NOT the actual URL with parameter
# values — this keeps cardinality bounded by the route count.
http_requests_total = Counter(
    "agentcraft_http_requests_total",
    "Total HTTP requests by method, route, and status.",
    labelnames=["method", "path_template", "status"],
    registry=_registry,
)

# HTTP request latency. Buckets chosen for a learning lab: 5ms → 10s.
http_request_duration_seconds = Histogram(
    "agentcraft_http_request_duration_seconds",
    "HTTP request latency in seconds.",
    labelnames=["method", "path_template", "status"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
    registry=_registry,
)

# Lab operation counter. `operation` is the allowlisted operation_key
# (bounded by the registry, ~10 keys). `status` is the OperationResult
# status (ok/failed/blocked). Never includes user input.
lab_runs_total = Counter(
    "agentcraft_lab_runs_total",
    "Total lab operation runs by operation_key and outcome.",
    labelnames=["operation", "status"],
    registry=_registry,
)


def record_http_request(method: str, path_template: str, status: int, duration_s: float) -> None:
    """Record one HTTP request. Called from the middleware after the
    response is produced."""
    labels = {"method": method, "path_template": path_template, "status": str(status)}
    http_requests_total.labels(**labels).inc()
    http_request_duration_seconds.labels(**labels).observe(duration_s)


def record_lab_run(operation: str, status: str) -> None:
    """Record one lab operation outcome. Called from the lab operations."""
    lab_runs_total.labels(operation=operation, status=status).inc()


def render_metrics() -> bytes:
    """Render the Prometheus text exposition format for /metrics."""
    return generate_latest(_registry)
