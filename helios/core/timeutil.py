"""UTC helpers shared by the core modules."""
from datetime import datetime, timezone


def utc(t: datetime) -> datetime:
    """Aware UTC datetime: naive values are taken as UTC, others converted."""
    return t.replace(tzinfo=timezone.utc) if t.tzinfo is None else t.astimezone(timezone.utc)


def parse_utc(s: str) -> datetime:
    """ISO 8601 or catalogue time text ('2017/09/10 16:00:05', '...Z') as an aware UTC datetime."""
    return utc(datetime.fromisoformat(str(s).replace("Z", "+00:00").replace("/", "-").replace(" ", "T")))
