from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from .models import Device, Event, MaintenanceWindow


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def window_matches_device(window: MaintenanceWindow, device: Device) -> bool:
    if window.device_id is not None and window.device_id != device.id:
        return False
    if window.site is not None and window.site != device.site:
        return False
    return True


def matching_windows(
    db: Session,
    device: Device,
    *,
    at: datetime | None = None,
    suppress_notifications: bool | None = None,
    exclude_from_sla: bool | None = None,
) -> list[MaintenanceWindow]:
    moment = aware(at) or utcnow()
    rows = list(db.execute(select(MaintenanceWindow)).scalars())
    result: list[MaintenanceWindow] = []
    for row in rows:
        start = aware(row.starts_at)
        end = aware(row.ends_at)
        if start is None or end is None or not (start <= moment < end):
            continue
        if not window_matches_device(row, device):
            continue
        if suppress_notifications is not None and bool(row.suppress_notifications) != suppress_notifications:
            continue
        if exclude_from_sla is not None and bool(row.exclude_from_sla) != exclude_from_sla:
            continue
        result.append(row)
    return result


def active_maintenance(db: Session, device: Device, at: datetime | None = None) -> list[MaintenanceWindow]:
    return matching_windows(db, device, at=at)


def notifications_suppressed(db: Session, device: Device, at: datetime | None = None) -> bool:
    return bool(matching_windows(db, device, at=at, suppress_notifications=True))


def _merge_intervals(intervals: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    if not intervals:
        return []
    ordered = sorted(intervals, key=lambda item: item[0])
    merged: list[list[datetime]] = [[ordered[0][0], ordered[0][1]]]
    for start, end in ordered[1:]:
        current = merged[-1]
        if start <= current[1]:
            if end > current[1]:
                current[1] = end
        else:
            merged.append([start, end])
    return [(item[0], item[1]) for item in merged]


def sla_exclusion_intervals(
    db: Session,
    device: Device,
    start: datetime,
    end: datetime,
) -> list[tuple[datetime, datetime]]:
    start = aware(start) or start
    end = aware(end) or end
    intervals: list[tuple[datetime, datetime]] = []
    for row in db.execute(select(MaintenanceWindow).where(MaintenanceWindow.exclude_from_sla.is_(True))).scalars():
        if not window_matches_device(row, device):
            continue
        row_start = aware(row.starts_at)
        row_end = aware(row.ends_at)
        if row_start is None or row_end is None or row_end <= start or row_start >= end:
            continue
        intervals.append((max(start, row_start), min(end, row_end)))
    return _merge_intervals(intervals)


def _interval_seconds(start: datetime, end: datetime) -> float:
    return max(0.0, (end - start).total_seconds())


def _excluded_seconds(start: datetime, end: datetime, exclusions: list[tuple[datetime, datetime]]) -> float:
    total = 0.0
    for excluded_start, excluded_end in exclusions:
        left = max(start, excluded_start)
        right = min(end, excluded_end)
        if right > left:
            total += _interval_seconds(left, right)
    return total


def availability_for_device(
    db: Session,
    device: Device,
    hours: int,
    *,
    end: datetime | None = None,
) -> float | None:
    period_end = aware(end) or utcnow()
    period_start = period_end - timedelta(hours=hours)

    events = list(db.execute(
        select(Event)
        .where(
            Event.device_id == device.id,
            Event.event_type == "state_change",
            Event.created_at >= period_start,
            Event.created_at <= period_end,
        )
        .order_by(Event.created_at)
    ).scalars())

    previous = db.execute(
        select(Event)
        .where(
            Event.device_id == device.id,
            Event.event_type == "state_change",
            Event.created_at < period_start,
        )
        .order_by(desc(Event.created_at))
        .limit(1)
    ).scalars().first()

    if previous is not None:
        state = str((previous.details or {}).get("to", device.state or "unknown"))
    elif events:
        state = str((events[0].details or {}).get("from", device.state or "unknown"))
    else:
        state = str(device.state or "unknown")

    segments: list[tuple[datetime, datetime, str]] = []
    cursor = period_start
    for event in events:
        at = aware(event.created_at) or period_start
        at = max(period_start, min(at, period_end))
        if at > cursor:
            segments.append((cursor, at, state))
        state = str((event.details or {}).get("to", state))
        cursor = at
    if cursor < period_end:
        segments.append((cursor, period_end, state))

    exclusions = sla_exclusion_intervals(db, device, period_start, period_end)
    excluded_total = sum(_interval_seconds(start, finish) for start, finish in exclusions)
    eligible_total = max(0.0, _interval_seconds(period_start, period_end) - excluded_total)
    if eligible_total <= 0:
        return None

    up_seconds = 0.0
    for segment_start, segment_end, segment_state in segments:
        if segment_state != "up":
            continue
        duration = _interval_seconds(segment_start, segment_end)
        duration -= _excluded_seconds(segment_start, segment_end, exclusions)
        up_seconds += max(0.0, duration)

    return round(100.0 * up_seconds / eligible_total, 4)
