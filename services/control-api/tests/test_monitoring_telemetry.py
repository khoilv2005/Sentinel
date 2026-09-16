from datetime import datetime, timezone
import uuid

from app.db import Base, SessionLocal, engine
from app.models import AgentlessMonitor, AgentlessTelemetryLatest, CredentialProfile, Device
from app.monitoring import derive_device_health, services_for_device
from app.monitoring_models import MonitoringTelemetryLatest
from app.monitoring_telemetry import refresh_device_compat_telemetry, write_assignment_telemetry
from app.secretbox import encrypt_secrets


def test_assignment_scoped_telemetry_prevents_cross_method_overwrite():
    Base.metadata.create_all(bind=engine)
    suffix = uuid.uuid4().hex[:8]
    db = SessionLocal()
    try:
        device = Device(ip_address=f"10.252.1.{int(suffix[:2],16)%200+20}", hostname=f"multi-{suffix}", state="unknown", device_class="server", site=f"telemetry-{suffix}")
        ssh_cred = CredentialProfile(name=f"ssh-telemetry-{suffix}", credential_type="ssh_password", username="qa", secret_encrypted=encrypt_secrets({"password":"x"}), options_json={}, enabled=True)
        snmp_cred = CredentialProfile(name=f"snmp-telemetry-{suffix}", credential_type="snmp_v2", username=None, secret_encrypted=encrypt_secrets({"community":"x"}), options_json={}, enabled=True)
        db.add_all([device, ssh_cred, snmp_cred]); db.flush()
        ssh = AgentlessMonitor(device_id=device.id, method="ssh", credential_id=ssh_cred.id, interval_seconds=60, enabled=True)
        snmp = AgentlessMonitor(device_id=device.id, method="snmp", credential_id=snmp_cred.id, interval_seconds=60, enabled=True)
        db.add_all([ssh, snmp]); db.flush()
        now = datetime.now(timezone.utc)
        ssh.last_success_at = now; snmp.last_success_at = now
        write_assignment_telemetry(db, ssh, {
            "cpu_usage_percent": 42.0,
            "memory_total_bytes": 16000000000,
            "memory_used_bytes": 8000000000,
            "memory_usage_percent": 50.0,
            "uptime_seconds": 1234,
            "process_count": 88,
            "disks": [{"mountpoint":"/","total_bytes":1000,"used_bytes":500,"usage_percent":50.0}],
            "interfaces": [{"name":"eth0","receive_bytes_total":10,"transmit_bytes_total":20}],
            "raw": {"collector":"ssh"},
        }, now)
        write_assignment_telemetry(db, snmp, {
            "cpu_usage_percent": 17.0,
            "memory_total_bytes": None,
            "memory_used_bytes": None,
            "memory_usage_percent": None,
            "uptime_seconds": 1200,
            "process_count": None,
            "disks": [],
            "interfaces": [{"name":"if1","receive_bytes_total":100,"transmit_bytes_total":200}],
            "raw": {"collector":"snmp"},
        }, now)
        compat = refresh_device_compat_telemetry(db, device.id, now=now)
        db.commit()

        assert compat is not None
        assert compat.source == "aggregate"
        assert compat.cpu_usage_percent == 42.0
        assert compat.memory_usage_percent == 50.0
        assert compat.disks[0]["mountpoint"] == "/"
        assert compat.interfaces[0]["name"] == "if1"
        assert set((compat.raw or {}).keys()) == {"ssh", "snmp"}
        assert db.get(MonitoringTelemetryLatest, ssh.id).cpu_usage_percent == 42.0
        assert db.get(MonitoringTelemetryLatest, snmp.id).cpu_usage_percent == 17.0

        service_names = {row["service_name"] for row in services_for_device(db, device)}
        assert "SSH monitoring" in service_names
        assert "SNMP monitoring" in service_names
        assert derive_device_health(db, device, now) == "up"
    finally:
        db.rollback()
        # Isolated CI databases are disposable; explicit cleanup keeps repeated
        # local runs deterministic without relying on table truncation.
        db.query(MonitoringTelemetryLatest).filter(MonitoringTelemetryLatest.device_id == getattr(locals().get("device", None), "id", "")).delete(synchronize_session=False)
        if "device" in locals():
            db.query(AgentlessTelemetryLatest).filter(AgentlessTelemetryLatest.device_id == device.id).delete(synchronize_session=False)
            db.query(AgentlessMonitor).filter(AgentlessMonitor.device_id == device.id).delete(synchronize_session=False)
            db.delete(device)
        for name in [f"ssh-telemetry-{suffix}", f"snmp-telemetry-{suffix}"]:
            row = db.query(CredentialProfile).filter(CredentialProfile.name == name).one_or_none()
            if row: db.delete(row)
        db.commit(); db.close()


def test_asset_health_is_degraded_when_one_method_is_up_and_one_is_down():
    suffix = uuid.uuid4().hex[:8]
    db = SessionLocal()
    try:
        device = Device(ip_address=f"10.252.2.{int(suffix[:2],16)%200+20}", hostname=f"health-{suffix}", state="unknown", device_class="server")
        cred = CredentialProfile(name=f"health-cred-{suffix}", credential_type="ssh_password", username="qa", secret_encrypted=encrypt_secrets({"password":"x"}), options_json={}, enabled=True)
        snmp_cred = CredentialProfile(name=f"health-snmp-{suffix}", credential_type="snmp_v2", username=None, secret_encrypted=encrypt_secrets({"community":"x"}), options_json={}, enabled=True)
        db.add_all([device, cred, snmp_cred]); db.flush()
        now = datetime.now(timezone.utc)
        ssh = AgentlessMonitor(device_id=device.id, method="ssh", credential_id=cred.id, interval_seconds=60, enabled=True, last_success_at=now, consecutive_failures=0)
        snmp = AgentlessMonitor(device_id=device.id, method="snmp", credential_id=snmp_cred.id, interval_seconds=60, enabled=True, last_success_at=now, consecutive_failures=3)
        db.add_all([ssh, snmp]); db.commit()
        assert derive_device_health(db, device, now) == "degraded"
    finally:
        if "device" in locals():
            db.query(AgentlessMonitor).filter(AgentlessMonitor.device_id == device.id).delete(synchronize_session=False)
            db.delete(device)
        for name in [f"health-cred-{suffix}", f"health-snmp-{suffix}"]:
            row = db.query(CredentialProfile).filter(CredentialProfile.name == name).one_or_none()
            if row: db.delete(row)
        db.commit(); db.close()
