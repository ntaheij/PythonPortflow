from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional


@dataclass(frozen=True)
class TimeRange:
    start: Optional[datetime] = None
    end: Optional[datetime] = None

    def describe(self) -> str:
        if self.start is None and self.end is None:
            return "All time"
        if self.start is not None and self.end is not None:
            return f"{self.start.isoformat()} -> {self.end.isoformat()}"
        if self.start is not None:
            return f"From {self.start.isoformat()}"
        return f"Until {self.end.isoformat()}"


def parse_iso_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None

    # unix timestamps (seconds or ms)
    if isinstance(value, (int, float)):
        try:
            v = float(value)
            if v > 1e12:
                v = v / 1000.0
            return datetime.fromtimestamp(v, tz=timezone.utc)
        except (ValueError, OSError):
            return None

    if not isinstance(value, str):
        return None

    s = value.strip()
    if not s:
        return None

    if s.endswith("Z"):
        s = s[:-1] + "+00:00"

    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt


def pick_evaluation_timestamp(item: dict) -> Optional[datetime]:
    # Your API returns top-level "date" as the evaluation moment
    for key in ("date", "evaluation_date", "evaluationDate"):
        dt = parse_iso_datetime(item.get(key))
        if dt:
            return dt

    evaluation = item.get("evaluation")
    if isinstance(evaluation, dict):
        for key in ("date", "evaluation_date", "evaluationDate"):
            dt = parse_iso_datetime(evaluation.get(key))
            if dt:
                return dt

    # Compatibility fallbacks
    for key in ("created_at", "submitted_at", "updated_at", "createdAt", "submittedAt", "updatedAt"):
        dt = parse_iso_datetime(item.get(key))
        if dt:
            return dt

    if isinstance(evaluation, dict):
        for key in ("created_at", "submitted_at", "updated_at", "createdAt", "submittedAt", "updatedAt"):
            dt = parse_iso_datetime(evaluation.get(key))
            if dt:
                return dt

    return None


def in_time_range(ts: Optional[datetime], tr: TimeRange) -> bool:
    if ts is None:
        # strict when a range is set
        return tr.start is None and tr.end is None
    if tr.start and ts < tr.start:
        return False
    if tr.end and ts > tr.end:
        return False
    return True


def range_last_days(days: int) -> TimeRange:
    end = datetime.now(timezone.utc)
    return TimeRange(start=end - timedelta(days=days), end=end)


def range_between_dates(start_date: str, end_date: str) -> TimeRange:
    start_d = datetime.strptime(start_date, "%Y-%m-%d").date()
    end_d = datetime.strptime(end_date, "%Y-%m-%d").date()
    if end_d < start_d:
        raise ValueError("end_date must be on/after start_date")
    start = datetime.combine(start_d, datetime.min.time(), tzinfo=timezone.utc)
    end = datetime.combine(end_d, datetime.max.time(), tzinfo=timezone.utc)
    return TimeRange(start=start, end=end)


def range_since_date(start_date: str) -> TimeRange:
    start_d = datetime.strptime(start_date, "%Y-%m-%d").date()
    start = datetime.combine(start_d, datetime.min.time(), tzinfo=timezone.utc)
    end = datetime.now(timezone.utc)
    return TimeRange(start=start, end=end)

