"""Časové utility — konverze na pražský čas (CEST = UTC+2 v létě)."""
from datetime import datetime, timezone, timedelta

PRAGUE_TZ = timezone(timedelta(hours=2))  # CEST (letní čas, platný po celé MS 2026)


def to_prague(dt: datetime | None) -> datetime | None:
    """Převede datetime (naivní UTC nebo aware) na Prague time."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(PRAGUE_TZ)


def fmt_prague(dt: datetime | None, fmt: str = "%-d.%-m. %H:%M") -> str:
    """Vrátí formátovaný čas v Prague timezone, nebo '' pokud None."""
    p = to_prague(dt)
    if p is None:
        return ""
    return p.strftime(fmt)
