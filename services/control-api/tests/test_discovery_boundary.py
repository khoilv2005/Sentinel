import uuid

from app import worker
from app.db import SessionLocal
from app.models import Device, Event, ScanJob


def test_discovery_does_not_override_operational_health(monkeypatch):
    suffix = uuid.uuid4().hex[:8]
    cidr = "192.168.247.0/30"
    existing_ip = "192.168.247.1"
    new_ip = "192.168.247.2"

    db = SessionLocal()
    try:
        existing = Device(
            ip_address=existing_ip,
            hostname=f"monitored-{suffix}",
            state="up",
            device_class="server",
            site=f"discovery-boundary-{suffix}",
        )
        job = ScanJob(cidr=cidr, site=f"discovery-boundary-{suffix}")
        db.add(existing)
        db.add(job)
        db.commit()
        job_id = job.id
        existing_id = existing.id
    finally:
        db.close()

    def fake_inspect_host(ip_address: str):
        # Existing monitored asset is deliberately absent from this discovery
        # pass. The second address is newly discovered.
        if ip_address == new_ip:
            return {
                "ip_address": new_ip,
                "hostname": f"new-{suffix}",
                "mac_address": None,
                "latency_ms": 1.0,
                "open_ports": [22],
                "device_class": "server",
            }
        return None

    monkeypatch.setattr(worker, "inspect_host", fake_inspect_host)
    worker.run_job(job_id)

    db = SessionLocal()
    try:
        existing = db.get(Device, existing_id)
        assert existing is not None
        assert existing.state == "up"

        new_asset = db.query(Device).filter(Device.ip_address == new_ip).one()
        assert new_asset.state == "unknown"

        state_changes = (
            db.query(Event)
            .filter(
                Event.device_id.in_([existing.id, new_asset.id]),
                Event.event_type == "state_change",
            )
            .all()
        )
        assert state_changes == []

        scan = db.get(ScanJob, job_id)
        assert scan.status == "complete"
        assert scan.scanned == 2
        assert scan.discovered == 1

        db.delete(scan)
        db.delete(new_asset)
        db.delete(existing)
        db.commit()
    finally:
        db.close()
