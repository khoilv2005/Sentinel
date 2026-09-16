from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from .agentless_collectors import collect_target
from .config import settings
from .db import Base, SessionLocal, engine
from .models import AgentlessMonitor, CredentialProfile, Device, Event
from .monitoring import sync_problems
from .monitoring_models import MonitoringTelemetryLatest  # noqa: F401 - registers table metadata
from .monitoring_telemetry import refresh_device_compat_telemetry, write_assignment_telemetry
from .secretbox import decrypt_secrets

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
log = logging.getLogger("sentinel-collector")
Base.metadata.create_all(bind=engine)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _due(row: AgentlessMonitor, now: datetime) -> bool:
    last = _aware(row.last_poll_at)
    return last is None or now - last >= timedelta(seconds=row.interval_seconds)


def poll_monitor(monitor_id: str):
    db = SessionLocal()
    try:
        monitor = db.get(AgentlessMonitor, monitor_id)
        if monitor is None or not monitor.enabled:
            return
        device = db.get(Device, monitor.device_id)
        credential = db.get(CredentialProfile, monitor.credential_id)
        if device is None or credential is None or not credential.enabled:
            monitor.last_poll_at = utcnow()
            monitor.last_error = "device or credential is unavailable"
            monitor.consecutive_failures = int(monitor.consecutive_failures or 0) + 1
            db.commit()
            if device is not None:
                refresh_device_compat_telemetry(db, device.id)
                db.commit()
                sync_problems(db)
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

            # Assignment-scoped telemetry is the v0.4 source of truth.
            write_assignment_telemetry(db, monitor, result, now)

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

            refresh_device_compat_telemetry(db, device.id, now=now)
            db.add(
                Event(
                    device_id=device.id,
                    severity="info",
                    event_type="monitoring_poll",
                    message=f"Collected {monitor.method} telemetry from {device.hostname or device.ip_address}",
                    details={"method": monitor.method, "assignment_id": monitor.id},
                )
            )
            db.commit()
            # sync_problems also reconciles overall Asset health from all active
            # monitoring methods, so one collector cannot overwrite another.
            sync_problems(db)
        except Exception as exc:
            now = utcnow()
            monitor = db.get(AgentlessMonitor, monitor_id)
            device = db.get(Device, monitor.device_id) if monitor else None
            if monitor is None:
                return
            monitor.last_poll_at = now
            monitor.last_error = str(exc)[:2000]
            monitor.consecutive_failures = int(monitor.consecutive_failures or 0) + 1
            if device is not None:
                refresh_device_compat_telemetry(db, device.id, now=now)
            db.commit()
            sync_problems(db)
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
                rows = list(
                    db.execute(
                        select(AgentlessMonitor).where(AgentlessMonitor.enabled.is_(True))
                    ).scalars()
                )
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
