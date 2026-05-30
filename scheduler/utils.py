from __future__ import annotations

from datetime import datetime, timedelta

BASE_DATE = datetime(2026, 1, 1)


def parse_hhmm(value: str) -> int:
    hour, minute = map(int, value.split(':'))
    return hour * 60 + minute


def fmt_time(minutes: int) -> str:
    days, mins = divmod(minutes, 24 * 60)
    h, m = divmod(mins, 60)
    suffix = f" +{days}d" if days else ""
    return f"{h:02d}:{m:02d}{suffix}"


def fmt_duration(minutes: int) -> str:
    if minutes < 60:
        return f"{minutes} min"
    h, m = divmod(minutes, 60)
    return f"{h}h {m:02d}m"
