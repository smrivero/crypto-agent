"""Buffers x402 payment step logs for SSE streams (ContextVar per request)."""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any, Literal

PaymentStepStatus = Literal["info", "ok", "warn", "error"]

_payment_buffer: ContextVar[list[dict[str, Any]] | None] = ContextVar(
    "payment_trace_buffer", default=None
)


def payment_trace_reset() -> None:
    _payment_buffer.set([])


def payment_trace_emit(
    step: str,
    message: str,
    *,
    status: PaymentStepStatus = "info",
    detail: str | None = None,
) -> None:
    buf = _payment_buffer.get()
    if buf is None:
        return
    entry: dict[str, Any] = {
        "type":    "payment_log",
        "step":    step,
        "status":  status,
        "message": message,
    }
    if detail:
        entry["detail"] = detail
    buf.append(entry)


def payment_trace_drain() -> list[dict[str, Any]]:
    buf = _payment_buffer.get()
    if not buf:
        return []
    out = list(buf)
    buf.clear()
    return out
