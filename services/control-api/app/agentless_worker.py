from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from .agentless_collectors import collect_target
from .collector_models import CollectorTelemetryLatest
from .config import settings
from .db import Base, SessionLocal, engine
from .models import (
    AgentlessMonitor,
    AgentlessTelemetryLatest,
    CredentialProfile,
    Device,
    Event,
    ManagedAgent,
)
from .monitoring import is_agent_online, sync_problems
from .secretbox import decrypt_secrets

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
log = logging.getLogger("sentinel-collector")
Base.metadata.create_all(bind=engine)

SOURCE_PRIORITY = {
    "snmp": 10,
    "ssh": 30,
    "winrm": 30,
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _due(row: AgentlessMonitor, now: datetime) -> bool:
    last = _aware(row.last_poll_at)
    return last is None or now - last >= timedelta(seconds=row.interval_seconds)


def _copy_result(target, method: str, result: dict, collected_at: datetime):
    target.source = method
    target.collected_at = collected_at
    target.cpu_usage_percent = result.get("cpu_usage_percent")
    target.memory_total_bytes = result.get("memory_total_bytes")
    target.memory_used_bytes = result.get("memory_used_bytes")
    target.memory_usage_percent = result.get("memory_usage_percent")
    target.uptime_seconds = result.get("uptime_seconds")
    target.process_count = result.get("process_count")
    target.disks = result.get("disks") or []
    target.interfaces = result.get("interfaces") or []
    target.raw = result.get("raw") or {}


def _should_refresh_aggregate(
    aggregate: AgentlessTelemetryLatest | None,
    method: str,
    now: datetime,
    interval_seconds: int,
) -> bool:
    if aggregate is None:
        return True
    current_priority = SOURCE_PRIORITY.get(aggregate.source, 0)
    new_priority = SOURCE_PRIORITY.get(method, 0)
    if new_priority >= current_priority:
        return True
    collected_at = _aware(aggregate.collected_at)
    stale_after = max(300, int(interval_seconds) * 3)
    return collected_at is None or (now - collected_at).total_seconds() > stale_after


def _record_state_change(db, device: Device, new_state: str, source: str, details: dict | None = None):
    previous = device.state
    if previous == new_state:
        return
    device.state = new_state
    db.add(Event(
        device_id=device.id,
        severity="critical" if new_state == "down" else "info",
        event_type="state_change",
        message=f"{device.hostname or device.ip_address}: {previous} -> {new_state}",
        details={"from": previous, "to": new_state, "source": source, **(details or {})},
    ))


def recompute_device_state(db, device: Device):
    """Aggregate health across independent monitoring methods.

    One failed collector must not mark an asset down while another configured
    method is healthy. Managed Agent check-in is treated as positive evidence.
    Remote monitoring marks the asset down only when every enabled remote
    assignment has reached the three-failure threshold.
    """
    agent = db.execute(
        select(ManagedAgent).where(
            ManagedAgent.device_id == device.id,
            ManagedAgent.revoked.is_(False),
        )
    ).scalar_one_or_none()
    if is_agent_online(agent):
        _record_state_change(db, device, "up", "monitoring")
        return

    monitors = list(db.execute(
        select(AgentlessMonitor).where(
            AgentlessMonitor.device_id == device.id,
            AgentlessMonitor.enabled.is_(True),
        )
    ).scalars())
    if not monitors:
        return

    healthy = [m for m in monitors if m.last_success_at is not None and int(m.consecutive_failures or 0) < 3]
    if healthy:
        _record_state_change(db, device, "up", "monitoring")
        return

    if all(int(m.consecutive_failures or 0) >= 3 for m in monitors):
        errors = {m.method: m.last_error for m in monitors if m.last_error}
        _record_state_change(db, device, "down", "monitoring", {"collector_errors": errors})


def _record_failure(db, monitor: AgentlessMonitor, device: Device | None, exc: Exception | str):
    now = utcnow()
    monitor.last_poll_at = now
    monitor.last_error = str(exc)[:2000]
    monitor.consecutive_failures = int(monitor.consecutive_failures or 0) + 1
    if device is not None:
        recompute_device_state(db, device)
    db.commit()
    sync_problems(db)


def poll_monitor(monitor_id: str):
    db = SessionLocal()
    try:
        monitor = db.get(AgentlessMonitor, monitor_id)
        if monitor is None or not monitor.enabled:
            return

        device = db.get(Device, monitor.device_id)
        credential = db.get(CredentialProfile, monitor.credential_id)
        if device is None or credential is None or not credential.enabled:
            _record_failure(db, monitor, device, "device or credential is unavailable")
            return

        monitor.last_poll_at = utcnow()
        db.commit()

        try:
            result = collect_target(
                monitor.method,
                device.ip_address,
                credential.username,
                decrypt_secrets(credential.secret_encrypted),
                credential.options_json or {},
            )
            now = utcnow()

            # Keep telemetry independent per monitoring assignment.
            sample = db.get(CollectorTelemetryLatest, monitor.id)
            if sample is None:
                sample = CollectorTelemetryLatest(
                    monitor_id=monitor.id,
                    device_id=device.id,
                    method=monitor.method,
                )
                db.add(sample)
            sample.device_id = device.id
            sample.method = monitor.method
            _copy_result(sample, monitor.method, result, now)

            # Transitional aggregate used by existing Host Detail/Prometheus.
            aggregate = db.get(AgentlessTelemetryLatest, device.id)
            if _should_refresh_aggregate(aggregate, monitor.method, now, monitor.interval_seconds):
                if aggregate is None:
                    aggregate = AgentlessTelemetryLatest(device_id=device.id)
                    db.add(aggregate)
                _copy_result(aggregate, monitor.method, result, now)

            device.last_seen = now
            if result.get("hostname"):
                device.hostname = str(result["hostname"])[:255]
            if result.get("os_name"):
                device.os_name = str(result["os_name"])[:128]
            if monitor.method == "winrm" and device.device_class in {None, "unknown"}:
                device.device_class = "windows"
            elif monitor.method == "ssh" and device.device_class in {None, "unknown"}:
                device.device_class = "server"

            monitor.last_success_at = now
            monitor.last_error = None
            monitor.consecutive_failures = 0
            recompute_device_state(db, device)

            db.add(Event(
                device_id=device.id,
                severity="info",
                event_type="monitor_poll",
                message=f"Collected {monitor.method} telemetry from {device.hostname or device.ip_address}",
                details={"method": monitor.method, "monitor_id": monitor.id},
            ))
            db.commit()
            sync_problems(db)
        except Exception as exc:
            monitor = db.get(AgentlessMonitor, monitor_id)
            device = db.get(Device, monitor.device_id) if monitor else None
            if monitor is None:
                return
            _record_failure(db, monitor, device, exc)
            log.warning(
                "%s poll failed for %s: %s",
                monitor.method,
                device.ip_address if device else monitor.device_id,
                exc,
            )
    finally:
        db.close()


def loop():
    workers = max(1, min(64, int(settings.agentless_workers)))
    log.info("SentinelView collector worker started with %s poll workers", workers)
    pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="collector")
    try:
        while True:
            db = SessionLocal()
            try:
                now = utcnow()
                rows = list(db.execute(
                    select(AgentlessMonitor).where(AgentlessMonitor.enabled.is_(True))
                ).scalars())
                due = [row.id for row in rows if _due(row, now)]
            finally:
                db.close()
            for monitor_id in due:
                pool.submit(poll_monitor, monitor_id)
            time.sleep(2)
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


if __name__ == "__main__":
    loop()
