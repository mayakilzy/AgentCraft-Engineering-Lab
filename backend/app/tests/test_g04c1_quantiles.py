"""G04-C1 — P50/P95 histogram quantile tests (reviewer notes #1 + #2).

Tests verify:
- _histogram_quantile() computes correct quantiles from bucket counts
  using linear interpolation (matching Prometheus' histogram_quantile()).
- Known-latency scenarios produce predictable approximate quantiles.
- Empty state (no observations) returns None.
- The metrics-summary endpoint returns None for p50/p95 when no
  requests have been recorded.
- The metrics-summary endpoint returns approximate p50/p95 within the
  correct bucket range when requests ARE recorded.

The approximation is inherent to histogram-based quantile estimation;
the tests assert the result falls within the expected bucket range, not
an exact value.
"""
from __future__ import annotations

import pytest

from app.api.v1.observability import _histogram_quantile
from app.core.metrics import (
    http_request_duration_seconds,
    http_requests_total,
    record_http_request,
    render_metrics,
    _registry,
)
from prometheus_client.parser import text_string_to_metric_families


# ---- Unit tests for _histogram_quantile() ----

def test_quantile_empty_returns_none():
    """No buckets → None (reviewer note #2: empty state)."""
    assert _histogram_quantile([], 0.50) is None


def test_quantile_zero_observations_returns_none():
    """Buckets exist but all counts are 0 → None."""
    buckets = [(0.005, 0.0), (0.01, 0.0), (float("inf"), 0.0)]
    assert _histogram_quantile(buckets, 0.50) is None


def test_quantile_p50_single_bucket():
    """10 observations all in [0, 0.005] → p50 = 0.0025 (midpoint via
    linear interpolation)."""
    # le=0.005: 10 obs, le=+Inf: 10 obs
    buckets = [(0.005, 10.0), (float("inf"), 10.0)]
    p50 = _histogram_quantile(buckets, 0.50)
    assert p50 is not None
    # target = 0.5 * 10 = 5. Bucket [0, 0.005] has 10 obs.
    # interp: 0 + (5-0)/(10-0) * (0.005-0) = 0.0025
    assert p50 == pytest.approx(0.0025, abs=0.0001)


def test_quantile_p50_known_latency_30ms():
    """10 observations at 30ms each. With buckets (0.005, 0.01, 0.025,
    0.05, ...), all 10 fall in the [0.025, 0.05] bucket. P50 target =
    0.5*10 = 5. Interp: 0.025 + (5-0)/(10-0) * (0.05-0.025) = 0.0375.
    The result is APPROXIMATE — it's 0.0375, not 0.03."""
    buckets = [
        (0.005, 0.0), (0.01, 0.0), (0.025, 0.0),
        (0.05, 10.0),  # all 10 fall here
        (0.1, 10.0), (float("inf"), 10.0),
    ]
    p50 = _histogram_quantile(buckets, 0.50)
    assert p50 is not None
    # Falls in [0.025, 0.05] bucket; interpolated to 0.0375.
    assert 0.025 <= p50 <= 0.05
    assert p50 == pytest.approx(0.0375, abs=0.001)


def test_quantile_p95_known_latency_mixed():
    """20 observations: 19 at 10ms, 1 at 100ms. P95 target = 0.95*20 = 19.
    The 19th observation (in sorted order) is 10ms, which falls in the
    [0.005, 0.01] or [0.01, 0.025] bucket depending on exact value.
    Since 19/20 observations are ≤ 0.025, the 19th cumulative count
    at le=0.025 is 19. target=19, cumulative at le=0.025 is 19 ≥ 19 →
    falls in the bucket ending at le=0.025.
    """
    # 19 obs in [0.01, 0.025] (10ms), 1 obs in [0.05, 0.1] (100ms)
    buckets = [
        (0.005, 0.0), (0.01, 0.0),
        (0.025, 19.0),  # 19 obs ≤ 0.025
        (0.05, 19.0),
        (0.1, 20.0),   # 1 more obs ≤ 0.1
        (float("inf"), 20.0),
    ]
    p95 = _histogram_quantile(buckets, 0.95)
    assert p95 is not None
    # target = 0.95 * 20 = 19. cumulative at le=0.025 is 19 ≥ 19.
    # prev_le=0.01, prev_count=0, bucket [0.01, 0.025] has 19 obs.
    # interp: 0.01 + (19-0)/(19-0) * (0.025-0.01) = 0.01 + 0.015 = 0.025
    assert 0.01 <= p95 <= 0.025
    assert p95 == pytest.approx(0.025, abs=0.001)


def test_quantile_p50_with_clear_buckets():
    """Clear separation: 5 obs at 5ms (bucket le=0.005), 5 obs at 50ms
    (bucket le=0.05). P50 target = 0.5*10 = 5. Cumulative at le=0.005 is 5
    ≥ 5 → falls in bucket ending at le=0.005.
    """
    buckets = [
        (0.005, 5.0),   # 5 obs ≤ 0.005
        (0.01, 5.0),
        (0.025, 5.0),
        (0.05, 10.0),   # 5 more obs ≤ 0.05
        (float("inf"), 10.0),
    ]
    p50 = _histogram_quantile(buckets, 0.50)
    assert p50 is not None
    # target=5, cumulative at le=0.005 is 5 ≥ 5.
    # prev_le=0, prev_count=0, bucket [0, 0.005] has 5 obs.
    # interp: 0 + (5-0)/(5-0) * (0.005-0) = 0.005
    assert p50 == pytest.approx(0.005, abs=0.0001)


# ---- Endpoint integration tests ----
# We monkeypatch render_metrics() to return a controlled Prometheus text
# exposition so the tests don't depend on the shared module-level registry
# state (which accumulates across tests in the full suite).

def _make_empty_metrics_text() -> bytes:
    """A Prometheus text format with no observations."""
    return b""


def _make_known_latency_text(n_obs: int, latency_bucket_le: str, count_in_bucket: int) -> bytes:
    """A Prometheus text format with `n_obs` observations all in one bucket.

    `latency_bucket_le` is the upper bound of the bucket where all
    observations fall (e.g. "0.05" for 30ms latencies).
    `count_in_bucket` is how many fall in that bucket.
    The remaining `n_obs - count_in_bucket` are in the +Inf bucket (0).
    """
    # Build a minimal histogram text with the buckets our metrics.py defines.
    lines = [
        "# HELP agentcraft_http_request_duration_seconds HTTP request latency.",
        "# TYPE agentcraft_http_request_duration_seconds histogram",
    ]
    buckets = ["0.005", "0.01", "0.025", "0.05", "0.1", "0.25", "0.5", "1.0", "2.5", "5.0", "10.0", "+Inf"]
    for le in buckets:
        count = count_in_bucket if le == latency_bucket_le else (n_obs if le == "+Inf" else 0)
        lines.append(
            f'agentcraft_http_request_duration_seconds_bucket{{le="{le}"}} {count}'
        )
    lines.append(f"agentcraft_http_request_duration_seconds_sum {n_obs * 0.03}")
    lines.append(f"agentcraft_http_request_duration_seconds_count {n_obs}")
    # Also include the counter so http_requests_total is nonzero.
    lines.append("# HELP agentcraft_http_requests_total Total HTTP requests.")
    lines.append("# TYPE agentcraft_http_requests_total counter")
    lines.append(f'agentcraft_http_requests_total{{method="GET",path_template="/api/v1/health/live",status="200"}} {n_obs}')
    return "\n".join(lines).encode("utf-8") + b"\n"


def test_metrics_summary_empty_state_returns_none(client, monkeypatch):
    """Reviewer note #2: when no requests have been recorded, p50/p95
    must be None (not 0.0 or a fake value).

    We monkeypatch render_metrics() to return an empty exposition so
    the test is independent of the shared registry state."""
    
    monkeypatch.setattr("app.core.metrics.render_metrics", lambda: _make_empty_metrics_text())

    r = client.get("/api/v1/observability/metrics-summary")
    assert r.status_code == 200
    body = r.json()
    # No observations → p50/p95 are None.
    assert body["http_request_duration_seconds_p50"] is None
    assert body["http_request_duration_seconds_p95"] is None
    assert body["http_requests_total"] == 0.0


def test_metrics_summary_with_known_latencies(client, monkeypatch):
    """10 observations at ~30ms each (all in the le=0.05 bucket). The
    computed p50 must fall in the [0.025, 0.05] bucket and be
    approximately 0.0375s (linear interpolation midpoint).

    The test asserts the result falls in the correct bucket range, not
    an exact value — this is the inherent approximation of histogram
    quantiles, documented in the endpoint's note.
    """
    # 10 obs, all in the le=0.05 bucket (30ms falls between 0.025 and 0.05).
    monkeypatch.setattr(
        "app.core.metrics.render_metrics",
        lambda: _make_known_latency_text(n_obs=10, latency_bucket_le="0.05", count_in_bucket=10),
    )

    r = client.get("/api/v1/observability/metrics-summary")
    assert r.status_code == 200
    body = r.json()
    p50 = body["http_request_duration_seconds_p50"]
    assert p50 is not None, "p50 should not be None after 10 observations"
    assert 0.025 <= p50 <= 0.05, f"p50={p50} should be in [0.025, 0.05]"
    p95 = body["http_request_duration_seconds_p95"]
    assert p95 is not None
    assert 0.025 <= p95 <= 0.05, f"p95={p95} should be in [0.025, 0.05]"
    assert body["http_requests_total"] == 10.0
    # The note must mention approximation or interpolation.
    assert "approximate" in body["note"].lower() or "interpolation" in body["note"].lower()


def test_metrics_summary_p50_lt_p95_with_mixed_latencies(client, monkeypatch):
    """With a mix of fast (5ms) and slow (100ms) requests, p50 < p95."""
    
    # 10 obs in le=0.005 (5ms), 10 obs in le=0.1 (100ms).
    # Total 20 obs.
    text = (
        "# HELP agentcraft_http_request_duration_seconds HTTP latency.\n"
        "# TYPE agentcraft_http_request_duration_seconds histogram\n"
        'agentcraft_http_request_duration_seconds_bucket{le="0.005"} 10\n'
        'agentcraft_http_request_duration_seconds_bucket{le="0.01"} 10\n'
        'agentcraft_http_request_duration_seconds_bucket{le="0.025"} 10\n'
        'agentcraft_http_request_duration_seconds_bucket{le="0.05"} 10\n'
        'agentcraft_http_request_duration_seconds_bucket{le="0.1"} 20\n'
        'agentcraft_http_request_duration_seconds_bucket{le="0.25"} 20\n'
        'agentcraft_http_request_duration_seconds_bucket{le="0.5"} 20\n'
        'agentcraft_http_request_duration_seconds_bucket{le="1.0"} 20\n'
        'agentcraft_http_request_duration_seconds_bucket{le="2.5"} 20\n'
        'agentcraft_http_request_duration_seconds_bucket{le="5.0"} 20\n'
        'agentcraft_http_request_duration_seconds_bucket{le="10.0"} 20\n'
        'agentcraft_http_request_duration_seconds_bucket{le="+Inf"} 20\n'
        "agentcraft_http_request_duration_seconds_sum 1.05\n"
        "agentcraft_http_request_duration_seconds_count 20\n"
        "# HELP agentcraft_http_requests_total Total requests.\n"
        "# TYPE agentcraft_http_requests_total counter\n"
        'agentcraft_http_requests_total{method="GET",path_template="/test",status="200"} 20\n'
    ).encode("utf-8")
    monkeypatch.setattr("app.core.metrics.render_metrics", lambda: text)

    r = client.get("/api/v1/observability/metrics-summary")
    body = r.json()
    p50 = body["http_request_duration_seconds_p50"]
    p95 = body["http_request_duration_seconds_p95"]
    assert p50 is not None and p95 is not None
    # p50 (median: 10 fast + 10 slow → the 10th-11th obs, both in the
    # fast bucket) should be < p95 (the 19th obs, in the slow bucket).
    assert p50 < p95, f"p50={p50} should be < p95={p95}"


def test_metrics_summary_no_pii_in_response(client, monkeypatch):
    """The summary must never include session_id, cookie, or user input."""
    
    monkeypatch.setattr("app.core.metrics.render_metrics", lambda: _make_known_latency_text(5, "0.05", 5))

    r = client.get("/api/v1/observability/metrics-summary")
    body_text = r.text.lower()
    assert "session_id" not in body_text
    assert "cookie" not in body_text
    assert "authorization" not in body_text
