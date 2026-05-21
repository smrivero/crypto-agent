"""Buffers execution trace lines for the SSE stream (ContextVar per request)."""

from contextvars import ContextVar
from typing import Any

_trace_buffer: ContextVar[list[dict[str, Any]] | None] = ContextVar(
    "stream_trace_buffer", default=None
)


def trace_reset() -> None:
    """Call once at the start of a streaming research run."""
    _trace_buffer.set([])


def trace_emit(level: str, node: str, message: str) -> None:
    """Append a log line if tracing is active for this request."""
    buf = _trace_buffer.get()
    if buf is not None:
        buf.append({"type": "log", "level": level, "node": node, "message": message})


def trace_drain() -> list[dict[str, Any]]:
    """Return and clear buffered trace events (SSE-shaped dicts)."""
    buf = _trace_buffer.get()
    if not buf:
        return []
    out = list(buf)
    buf.clear()
    return out
