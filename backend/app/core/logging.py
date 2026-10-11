"""Structured JSON logging with request_id / trace_id correlation.

Minimal footprint: a `get_logger(name)` factory that emits single-line JSON
records. OpenTelemetry span ids are attached when the OTEL SDK is active
(wired in G04); until then, logs carry only `request_id` if set in a context
var.
"""
from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from typing import Any, Dict

_request_id_var: ContextVar[str] = ContextVar("request_id", default="-")
_trace_id_var: ContextVar[str] = ContextVar("trace_id", default="-")


def set_request_id(value: str) -> None:
    _request_id_var.set(value)


def set_trace_id(value: str) -> None:
    _trace_id_var.set(value)


class _JsonFormatter(logging.Formatter):
    """One JSON object per log record. No multi-line, no extras leakage."""

    _safe_keys = {
        "name", "msg", "levelname", "levelno", "pathname", "lineno",
        "funcName", "created", "msecs", "process", "processName",
        "thread", "threadName", "exc_info", "message",
    }

    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S.%fZ"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": _request_id_var.get(),
            "trace_id": _trace_id_var.get(),
        }
        # Attach any extra fields the caller added via logger.info(..., extra=...)
        for k, v in record.__dict__.items():
            if k not in self._safe_keys and not k.startswith("_"):
                payload[k] = v
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str = "INFO") -> None:
    """Configure root logger once at startup."""
    root = logging.getLogger()
    # Clear any pre-existing handlers (uvicorn adds its own; we keep ours).
    for h in list(root.handlers):
        root.removeHandler(h)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JsonFormatter())
    root.addHandler(handler)
    root.setLevel(level.upper())


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
