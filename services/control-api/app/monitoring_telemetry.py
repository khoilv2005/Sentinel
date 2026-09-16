from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import AgentlessMonitor, AgentlessTelemetryLatest
from .monitoring_models import MonitoringTelemetryLatest


HOST_METHODS = {"winrm": 30, "ssh": 30, "snmp": 10}
INTERFACE_METHODS = {"snmp": 30, "winrm": 20, "ssh": 20}


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _active_rows(db: Session, device_id: str, now: datetime) -> list[MonitoringTelemetryLatest]:
    rows = list(
        db.execute(
            select(MonitoringTelemetryLatest).where(
                MonitoringTelemetryLatest.device_id == device_id
            )
        ).scalars()
    )
    if not rows:
        return []

    monitor_ids = [row.assignment_id for row in rows]
    monitors = {
        row.id: row
        for row in db.execute(
            select(AgentlessMonitor).where(AgentlessMonitor.id.in_(monitor_ids))
        ).scalars()
    }
    active: list[MonitoringTelemetryLatest] = []
    for row in rows:
        monitor = monitors.get(row.assignment_id)
        if monitor is None or not monitor.enabled:
            continue
        collected_at = _aware(row.collected_at)
        if collected_at is None:
            continue
        max_age = max(120, int(monitor.interval_seconds or 60) * 3)
        if (now - collected_at).total_seconds() <= max_age:
            active.append(row)
    return active


def _pick_scalar(rows: list[MonitoringTelemetryLatest], field: str):
    candidates = [row for row in rows if getattr(row, field) is not None]
    if not candidates:
        return None
    candidates.sort(
        key=lambda row: (
            HOST_METHODS.get(row.method, 0),
            _aware(row.collected_at) or datetime.min.replace(tzinfo=timezone.utc),
        ),
        reverse=True,
    )
    return getattr(candidates[0], field)


def _pick_list(rows: list[MonitoringTelemetryLatest], field: str, priorities: dict[str, int]) -> list:
    candidates = [row for row in rows if getattr(row, field)]
    if not candidates:
        return []
    candidates.sort(
        key=lambda row: (
            priorities.get(row.method, 0),
            _aware(row.collected_at) or datetime.min.replace(tzinfo=timezone.utc),
        ),
        reverse=True,
    )
    return list(getattr(candidates[0], field) or [])


def write_assignment_telemetry(
    db: Session,
    monitor: AgentlessMonitor,
    result: dict,
    collected_at: datetime,
) -> MonitoringTelemetryLatest:
    row = db.get(MonitoringTelemetryLatest, monitor.id)
    if row is None:
        row = MonitoringTelemetryLatest(
            assignment_id=monitor.id,
            device_id=monitor.device_id,
            method=monitor.method,
        )
        db.add(row)

    row.device_id = monitor.device_id
    row.method = monitor.method
    row.collected_at = collected_at
    row.cpu_usage_percent = result.get("cpu_usage_percent")
    row.memory_total_bytes = result.get("memory_total_bytes")
    row.memory_used_bytes = result.get("memory_used_bytes")
    row.memory_usage_percent = result.get("memory_usage_percent")
    row.uptime_seconds = result.get("uptime_seconds")
    row.process_count = result.get("process_count")
    row.disks = result.get("disks") or []
    row.interfaces = result.get("interfaces") or []
    row.raw = result.get("raw") or {}
    db.flush()
    return row


def refresh_device_compat_telemetry(
    db: Session,
    device_id: str,
    *,
    now: datetime | None = None,
) -> AgentlessTelemetryLatest | None:
    """Build the legacy device-level row from assignment-scoped telemetry.

    This row remains only for compatibility with the current metrics/UI layer.
    It is no longer the source of truth. Host-oriented metrics prefer WinRM/SSH;
    interface lists prefer SNMP. Missing fields from one method therefore cannot
    erase data supplied by another active method.
    """

    now = now or datetime.now(timezone.utc)
    rows = _active_rows(db, device_id, now)
    compat = db.get(AgentlessTelemetryLatest, device_id)

    if not rows:
        if compat is not None:
            db.delete(compat)
            db.flush()
        return None

    if compat is None:
        compat = AgentlessTelemetryLatest(device_id=device_id)
        db.add(compat)

    methods = sorted({row.method for row in rows})
    compat.source = methods[0] if len(methods) == 1 else "aggregate"
    compat.collected_at = max(
        (_aware(row.collected_at) for row in rows if row.collected_at is not None),
        default=now,
    )
    compat.cpu_usage_percent = _pick_scalar(rows, "cpu_usage_percent")
    compat.memory_total_bytes = _pick_scalar(rows, "memory_total_bytes")
    compat.memory_used_bytes = _pick_scalar(rows, "memory_used_bytes")
    compat.memory_usage_percent = _pick_scalar(rows, "memory_usage_percent")
    compat.uptime_seconds = _pick_scalar(rows, "uptime_seconds")
    compat.process_count = _pick_scalar(rows, "process_count")
    compat.disks = _pick_list(rows, "disks", HOST_METHODS)
    compat.interfaces = _pick_list(rows, "interfaces", INTERFACE_METHODS)
    compat.raw = {
        row.method: row.raw or {}
        for row in sorted(rows, key=lambda item: item.method)
    }
    db.flush()
    return compat
