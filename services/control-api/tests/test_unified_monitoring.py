import uuid

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
ADMIN = {"X-API-Key": "change-me-now"}


def test_unified_monitoring_api_keeps_legacy_aliases():
    from app.db import SessionLocal
    from app.models import AgentlessMonitor, CredentialProfile, Device

    suffix = uuid.uuid4().hex[:8]
    credential = client.post("/api/v1/credentials", headers=ADMIN, json={
        "name": f"unified-{suffix}",
        "credential_type": "ssh_password",
        "username": "monitor",
        "secret": "not-a-real-password",
        "options": {},
    })
    assert credential.status_code == 200, credential.text
    credential_id = credential.json()["id"]
    target = "10.253.201.10"

    created = client.post("/api/v1/monitoring/assignments/bulk", headers=ADMIN, json={
        "method": "ssh",
        "credential_id": credential_id,
        "scope": "selected",
        "targets": [target],
        "site": f"unified-{suffix}",
        "interval_seconds": 60,
    })
    assert created.status_code == 200, created.text
    assert created.json()["targets"] == 1

    unified = client.get("/api/v1/monitoring/assignments", headers=ADMIN)
    legacy = client.get("/api/v1/agentless/monitors", headers=ADMIN)
    assert unified.status_code == 200
    assert legacy.status_code == 200
    unified_ids = {row["id"] for row in unified.json() if row["credential_id"] == credential_id}
    legacy_ids = {row["id"] for row in legacy.json() if row["credential_id"] == credential_id}
    assert unified_ids
    assert unified_ids == legacy_ids

    db = SessionLocal()
    try:
        monitors = db.query(AgentlessMonitor).filter(AgentlessMonitor.credential_id == credential_id).all()
        device_ids = [row.device_id for row in monitors]
        for row in monitors:
            db.delete(row)
        for device_id in device_ids:
            device = db.get(Device, device_id)
            if device:
                db.delete(device)
        cred = db.get(CredentialProfile, credential_id)
        if cred:
            db.delete(cred)
        db.commit()
    finally:
        db.close()


def test_per_assignment_telemetry_does_not_collide_for_same_asset():
    from app.collector_models import CollectorTelemetryLatest
    from app.db import SessionLocal
    from app.models import AgentlessMonitor, CredentialProfile, Device
    from app.secretbox import encrypt_secrets

    db = SessionLocal()
    suffix = uuid.uuid4().hex[:8]
    try:
        device = Device(ip_address=f"10.253.202.{int(suffix[:2], 16) % 200 + 1}", state="unknown")
        ssh_cred = CredentialProfile(
            name=f"ssh-multi-{suffix}", credential_type="ssh_password", username="monitor",
            secret_encrypted=encrypt_secrets({"password": "x"}), options_json={}, enabled=True,
        )
        snmp_cred = CredentialProfile(
            name=f"snmp-multi-{suffix}", credential_type="snmp_v2", username=None,
            secret_encrypted=encrypt_secrets({"community": "x"}), options_json={}, enabled=True,
        )
        db.add_all([device, ssh_cred, snmp_cred])
        db.flush()
        ssh = AgentlessMonitor(device_id=device.id, method="ssh", credential_id=ssh_cred.id, enabled=True)
        snmp = AgentlessMonitor(device_id=device.id, method="snmp", credential_id=snmp_cred.id, enabled=True)
        db.add_all([ssh, snmp])
        db.flush()
        db.add_all([
            CollectorTelemetryLatest(
                monitor_id=ssh.id, device_id=device.id, method="ssh",
                cpu_usage_percent=20.0, memory_usage_percent=30.0,
            ),
            CollectorTelemetryLatest(
                monitor_id=snmp.id, device_id=device.id, method="snmp",
                cpu_usage_percent=10.0, memory_usage_percent=None,
            ),
        ])
        db.commit()

        rows = db.query(CollectorTelemetryLatest).filter(
            CollectorTelemetryLatest.device_id == device.id
        ).all()
        assert len(rows) == 2
        assert {row.method for row in rows} == {"ssh", "snmp"}
        assert {row.monitor_id for row in rows} == {ssh.id, snmp.id}
    finally:
        db.rollback()
        if 'device' in locals():
            db.query(CollectorTelemetryLatest).filter(CollectorTelemetryLatest.device_id == device.id).delete()
            db.query(AgentlessMonitor).filter(AgentlessMonitor.device_id == device.id).delete()
            db.query(CredentialProfile).filter(CredentialProfile.name.in_([
                f"ssh-multi-{suffix}", f"snmp-multi-{suffix}"
            ])).delete(synchronize_session=False)
            db.query(Device).filter(Device.id == device.id).delete()
            db.commit()
        db.close()


def test_device_is_down_only_when_all_remote_methods_fail():
    from app.agentless_worker import recompute_device_state
    from app.db import SessionLocal
    from app.models import AgentlessMonitor, CredentialProfile, Device
    from app.secretbox import encrypt_secrets

    db = SessionLocal()
    suffix = uuid.uuid4().hex[:8]
    try:
        device = Device(ip_address=f"10.253.203.{int(suffix[:2], 16) % 200 + 1}", state="up")
        ssh_cred = CredentialProfile(
            name=f"ssh-health-{suffix}", credential_type="ssh_password", username="monitor",
            secret_encrypted=encrypt_secrets({"password": "x"}), options_json={}, enabled=True,
        )
        snmp_cred = CredentialProfile(
            name=f"snmp-health-{suffix}", credential_type="snmp_v2", username=None,
            secret_encrypted=encrypt_secrets({"community": "x"}), options_json={}, enabled=True,
        )
        db.add_all([device, ssh_cred, snmp_cred])
        db.flush()
        ssh = AgentlessMonitor(
            device_id=device.id, method="ssh", credential_id=ssh_cred.id,
            enabled=True, consecutive_failures=3,
        )
        snmp = AgentlessMonitor(
            device_id=device.id, method="snmp", credential_id=snmp_cred.id,
            enabled=True, consecutive_failures=0,
        )
        db.add_all([ssh, snmp])
        db.commit()

        recompute_device_state(db, device)
        assert device.state == "up"

        snmp.consecutive_failures = 3
        recompute_device_state(db, device)
        assert device.state == "down"
        db.commit()
    finally:
        db.rollback()
        if 'device' in locals():
            db.query(AgentlessMonitor).filter(AgentlessMonitor.device_id == device.id).delete()
            db.query(CredentialProfile).filter(CredentialProfile.name.in_([
                f"ssh-health-{suffix}", f"snmp-health-{suffix}"
            ])).delete(synchronize_session=False)
            db.query(Device).filter(Device.id == device.id).delete()
            db.commit()
        db.close()


def test_discovery_enriches_inventory_without_changing_health(monkeypatch):
    from app import worker
    from app.db import SessionLocal
    from app.models import Device, Event, ScanJob

    db = SessionLocal()
    suffix = uuid.uuid4().hex[:8]
    site = f"discovery-boundary-{suffix}"
    try:
        down_device = Device(ip_address="10.253.204.1", hostname="existing-down", state="down", site=site)
        up_device = Device(ip_address="10.253.204.2", hostname="existing-up", state="up", site=site)
        job = ScanJob(cidr="10.253.204.0/30", site=site)
        db.add_all([down_device, up_device, job])
        db.commit()
        job_id = job.id
        down_id = down_device.id
        up_id = up_device.id
    finally:
        db.close()

    def fake_inspect(ip):
        if ip == "10.253.204.1":
            return {
                "ip_address": ip,
                "hostname": "observed-down",
                "mac_address": None,
                "latency_ms": 1.0,
                "open_ports": [22],
                "device_class": "server",
            }
        return None

    monkeypatch.setattr(worker, "inspect_host", fake_inspect)
    worker.run_job(job_id)

    db = SessionLocal()
    try:
        down_device = db.get(Device, down_id)
        up_device = db.get(Device, up_id)
        job = db.get(ScanJob, job_id)
        assert down_device.state == "down"
        assert up_device.state == "up"
        assert down_device.hostname == "observed-down"
        assert job.status == "complete"
        state_events = db.query(Event).filter(
            Event.device_id.in_([down_id, up_id]),
            Event.event_type == "state_change",
        ).all()
        assert not state_events
    finally:
        db.query(Event).filter(Event.device_id.in_([down_id, up_id])).delete(synchronize_session=False)
        db.query(ScanJob).filter(ScanJob.id == job_id).delete()
        db.query(Device).filter(Device.id.in_([down_id, up_id])).delete(synchronize_session=False)
        db.commit()
        db.close()
