from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from .agentless_collectors import collect_target
from .config import settings
from .db import Base, SessionLocal, engine
from .models import AgentlessMonitor, AgentlessTelemetryLatest, CredentialProfile, Device, Event
from .monitoring import sync_problems
from .secretbox import decrypt_secrets

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
log = logging.getLogger("sentinel-agentless")
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
            db.commit()
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
            telemetry = db.get(AgentlessTelemetryLatest, device.id)
            if telemetry is None:
                telemetry = AgentlessTelemetryLatest(device_id=device.id)
                db.add(telemetry)
            telemetry.source = monitor.method
            telemetry.collected_at = now
            telemetry.cpu_usage_percent = result.get("cpu_usage_percent")
            telemetry.memory_total_bytes = result.get("memory_total_bytes")
            telemetry.memory_used_bytes = result.get("memory_used_bytes")
            telemetry.memory_usage_percent = result.get("memory_usage_percent")
            telemetry.uptime_seconds = result.get("uptime_seconds")
            telemetry.process_count = result.get("process_count")
            telemetry.disks = result.get("disks") or []
            telemetry.interfaces = result.get("interfaces") or []
            telemetry.raw = result.get("raw") or {}
            previous_state = device.state
            device.state = "up"
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
            if previous_state != "up":
                db.add(Event(device_id=device.id, severity="info", event_type="state_change",
                             message=f"{device.hostname or device.ip_address}: {previous_state} -> up",
                             details={"from": previous_state, "to": "up", "source": monitor.method}))
            db.add(Event(device_id=device.id, severity="info", event_type="agentless_poll",
                         message=f"Collected {monitor.method} telemetry from {device.hostname or device.ip_address}",
                         details={"method": monitor.method}))
            db.commit()
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
            if device is not None and monitor.consecutive_failures >= 3:
                previous_state = device.state
                device.state = "down"
                if previous_state != "down":
                    db.add(Event(device_id=device.id, severity="critical", event_type="state_change",
                                 message=f"{device.hostname or device.ip_address}: {previous_state} -> down",
                                 details={"from": previous_state, "to": "down", "source": monitor.method, "error": monitor.last_error}))
            db.commit()
            sync_problems(db)
            log.warning("%s poll failed for %s: %s", monitor.method, device.ip_address if device else monitor.device_id, exc)
    finally:
        db.close()


def loop():
    workers = max(1, min(64, int(settings.agentless_workers)))
    log.info("SentinelView agentless worker started with %s poll workers", workers)
    pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="agentless")
    try:
        while True:
            db = SessionLocal()
            try:
                now = utcnow()
                rows = list(db.execute(select(AgentlessMonitor).where(AgentlessMonitor.enabled.is_(True))).scalars())
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
