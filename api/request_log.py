"""In-memory request log — development only, resets on restart."""

from collections import deque
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel


class LogEntry(BaseModel):
    timestamp: str
    query: str
    status: str  # "success" | "error"
    duration_ms: int
    error: Optional[str] = None


_log: deque[LogEntry] = deque(maxlen=50)


def record(query: str, status: str, duration_ms: int, error: Optional[str] = None) -> None:
    _log.appendleft(
        LogEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            query=query,
            status=status,
            duration_ms=duration_ms,
            error=error,
        )
    )


def get_recent() -> list[LogEntry]:
    return list(_log)
