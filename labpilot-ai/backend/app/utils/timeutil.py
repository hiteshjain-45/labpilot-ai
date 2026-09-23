"""Time helpers. The database stores naive UTC datetimes (portable across SQLite/PostgreSQL)."""
from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
