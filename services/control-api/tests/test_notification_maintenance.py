import json
import threading
import uuid
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from app.db import SessionLocal
from app.maintenance_engine import availability_for_device
from app.models import AgentlessMonitor, CredentialProfile, Device, Event, MaintenanceWindow, NotificationChannel, Problem
from app.monitoring import sync_problems
from app.notification_engine import process_delivery
from app.notification_models import NotificationDelivery
from app.secretbox import encrypt_secrets


class _WebhookHandler(BaseHTTPRequestHandler):
    received: list[dict] = []

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length) or b"{}")
        self.__class__.received.append(payload)
        self.send_response(204)
        self.end_headers()

    def log_message(self, _format, *_args):
        return


def _start_webhook():
    _WebhookHandler.received = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _WebhookHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def _add_health_monitor(db, device: Device, suffix: str, *, down: bool) -> AgentlessMonitor:
    credential = CredentialProfile(
        name=f"qa-health-{suffix}",
        credential_type="ssh_password",
        username="qa",
        secret_encrypted=encrypt_secrets({"password": "qa-only"}),
        options_json={},
        enabled=True,
    )
    db.add(credential)
    db.flush()
    monitor = AgentlessMonitor(
        device_id=device.id,
        method="ssh",
        credential_id=credential.id,
        interval_seconds=60,
        enabled=True,
        last_poll_at=datetime.now(timezone.utc),
        last_success_at=datetime.now(timezone.utc),
        consecutive_failures=3 if down else 0,
        last_error="qa simulated collector failure" if down else None,
    )
    db.add(monitor)
    return monitor


def _cleanup(db, *, device_id: str, channel_id: str | None = None):
    for row in db.query(NotificationDelivery).filter(NotificationDelivery.device_id == device_id).all():
        db.delete(row)
    for row in db.query(Problem).filter(Problem.device_id == device_id).all():
        db.delete(row)
    for row in db.query(MaintenanceWindow).filter(MaintenanceWindow.device_id == device_id).all():
        db.delete(row)
    for row in db.query(Event).filter(Event.device_id == device_id).all():
        db.delete(row)

    monitors = db.query(AgentlessMonitor).filter(AgentlessMonitor.device_id == device_id).all()
    credential_ids = [row.credential_id for row in monitors]
    for row in monitors:
        db.delete(row)
    db.flush()
    for credential_id in credential_ids:
        credential = db.get(CredentialProfile, credential_id)
        if credential:
            db.delete(credential)

    if channel_id:
        channel = db.get(NotificationChannel, channel_id)
        if channel:
            db.delete(channel)
    device = db.get(Device, device_id)
    if device:
        db.delete(device)
    db.commit()


def test_problem_open_and_recovery_are_dispatched_to_webhook():
    server = _start_webhook()
    db = SessionLocal()
    device_id = ""
    channel_id = ""
    try:
        suffix = uuid.uuid4().hex[:8]
        device = Device(
            ip_address=f"192.168.245.{int(suffix[:2], 16) % 200 + 1}",
            hostname=f"notify-{suffix}",
            state="unknown",
        )
        channel = NotificationChannel(
            name=f"qa-webhook-{suffix}",
            channel_type="webhook",
            enabled=True,
            config={"url": f"http://127.0.0.1:{server.server_port}/notify"},
        )
        db.add_all([device, channel])
        db.flush()
        monitor = _add_health_monitor(db, device, suffix, down=True)
        db.commit()
        db.refresh(device)
        db.refresh(channel)
        device_id, channel_id = device.id, channel.id

        sync_problems(db)
        db.refresh(device)
        assert device.state == "down"
        problem = db.query(Problem).filter(
            Problem.device_id == device.id,
            Problem.service_key == "host:availability",
        ).first()
        assert problem is not None
        delivery = db.query(NotificationDelivery).filter(
            NotificationDelivery.problem_id == problem.id,
            NotificationDelivery.transition == "opened",
        ).first()
        assert delivery is not None and delivery.status == "pending"

        process_delivery(db, delivery)
        assert delivery.status == "sent"
        assert _WebhookHandler.received
        assert _WebhookHandler.received[-1]["problem_id"] == problem.id
        assert _WebhookHandler.received[-1]["event"] == "opened"

        monitor.consecutive_failures = 0
        monitor.last_error = None
        monitor.last_success_at = datetime.now(timezone.utc)
        db.commit()
        sync_problems(db)
        db.refresh(device)
        db.refresh(problem)
        assert device.state == "up"
        assert problem.state == "resolved"
        recovery = db.query(NotificationDelivery).filter(
            NotificationDelivery.problem_id == problem.id,
            NotificationDelivery.transition == "resolved",
        ).first()
        assert recovery is not None and recovery.status == "pending"
        process_delivery(db, recovery)
        assert recovery.status == "sent"
        assert _WebhookHandler.received[-1]["event"] == "resolved"
    finally:
        if device_id:
            _cleanup(db, device_id=device_id, channel_id=channel_id or None)
        db.close()
        server.shutdown()
        server.server_close()


def test_active_maintenance_suppresses_problem_notifications_then_reopens_after_window():
    db = SessionLocal()
    device_id = ""
    channel_id = ""
    try:
        suffix = uuid.uuid4().hex[:8]
        now = datetime.now(timezone.utc)
        device = Device(
            ip_address=f"192.168.244.{int(suffix[:2], 16) % 200 + 1}",
            hostname=f"maint-{suffix}",
            state="unknown",
        )
        channel = NotificationChannel(
            name=f"qa-maint-webhook-{suffix}",
            channel_type="webhook",
            enabled=True,
            config={"url": "http://127.0.0.1:9/unreachable"},
        )
        db.add_all([device, channel])
        db.flush()
        _add_health_monitor(db, device, suffix, down=True)
        window = MaintenanceWindow(
            name=f"qa-maint-{suffix}",
            device_id=device.id,
            starts_at=now - timedelta(minutes=5),
            ends_at=now + timedelta(minutes=5),
            suppress_notifications=True,
            exclude_from_sla=True,
            created_by="qa",
        )
        db.add(window)
        db.commit()
        device_id, channel_id = device.id, channel.id

        sync_problems(db)
        problem = db.query(Problem).filter(
            Problem.device_id == device.id,
            Problem.service_key == "host:availability",
        ).first()
        assert problem is not None
        assert problem.state == "suppressed"
        delivery = db.query(NotificationDelivery).filter(
            NotificationDelivery.problem_id == problem.id,
            NotificationDelivery.transition == "opened",
        ).first()
        assert delivery is not None
        assert delivery.status == "suppressed"
        assert delivery.attempts == 0

        window.ends_at = now - timedelta(seconds=1)
        db.commit()
        sync_problems(db)
        db.refresh(problem)
        assert problem.state == "open"
        resumed = db.query(NotificationDelivery).filter(
            NotificationDelivery.problem_id == problem.id,
            NotificationDelivery.transition == "maintenance-ended",
        ).first()
        assert resumed is not None
        assert resumed.status == "pending"
    finally:
        if device_id:
            _cleanup(db, device_id=device_id, channel_id=channel_id or None)
        db.close()


def test_sla_excludes_maintenance_interval_from_denominator():
    db = SessionLocal()
    device_id = ""
    try:
        suffix = uuid.uuid4().hex[:8]
        end = datetime(2026, 1, 1, 1, 0, tzinfo=timezone.utc)
        start = end - timedelta(hours=1)
        device = Device(
            ip_address=f"192.168.243.{int(suffix[:2], 16) % 200 + 1}",
            hostname=f"sla-{suffix}",
            state="down",
        )
        db.add(device)
        db.flush()
        device_id = device.id
        db.add(
            Event(
                device_id=device.id,
                severity="critical",
                event_type="state_change",
                message="up -> down",
                details={"from": "up", "to": "down", "source": "qa"},
                created_at=start + timedelta(minutes=30),
            )
        )
        db.add(
            MaintenanceWindow(
                name=f"sla-exclusion-{suffix}",
                device_id=device.id,
                starts_at=start + timedelta(minutes=30),
                ends_at=start + timedelta(minutes=50),
                suppress_notifications=False,
                exclude_from_sla=True,
                created_by="qa",
            )
        )
        db.commit()

        # Raw availability is 30/60 = 50%. Excluding 20 minutes of downtime
        # leaves 30 minutes up in a 40-minute eligible window = 75%.
        assert availability_for_device(db, device, 1, end=end) == 75.0
    finally:
        if device_id:
            _cleanup(db, device_id=device_id)
        db.close()
