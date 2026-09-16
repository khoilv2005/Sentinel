import uuid
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
ADMIN = {"X-API-Key": "change-me-now"}


def _create_asset(ip_address: str, *, site: str | None = None, observed: bool = False):
    response = client.post(
        "/api/v1/devices",
        headers=ADMIN,
        json={"ip_address": ip_address, "hostname": None, "device_class": "unknown", "site": site, "tags": []},
    )
    assert response.status_code == 200, response.text
    if observed:
        from app.db import SessionLocal
        from app.models import Device

        db = SessionLocal()
        try:
            row = db.query(Device).filter(Device.ip_address == ip_address).one()
            row.last_seen = datetime.now(timezone.utc)
            db.commit()
        finally:
            db.close()
    return response.json()


def test_monitoring_credentials_and_inventory_scopes():
    suffix = uuid.uuid4().hex[:8]
    created = client.post(
        "/api/v1/credentials",
        headers=ADMIN,
        json={
            "name": f"monitoring-{suffix}",
            "credential_type": "winrm",
            "username": "monitor",
            "secret": "not-a-real-password",
            "options": {"transport": "ntlm"},
        },
    )
    assert created.status_code == 200, created.text
    credential = created.json()
    assert credential["has_secret"] is True
    assert "secret" not in credential and "secret_encrypted" not in credential

    first = _create_asset("192.168.248.1", site="monitoring-test", observed=True)
    second = _create_asset("192.168.248.2", site="monitoring-test", observed=True)

    candidates = client.get("/api/v1/monitoring/candidates?cidr=192.168.248.0/30", headers=ADMIN)
    assert candidates.status_code == 200, candidates.text
    assert [x["ip_address"] for x in candidates.json()] == ["192.168.248.1", "192.168.248.2"]
    assert all(x["discovered"] for x in candidates.json())

    bulk = client.post(
        "/api/v1/monitoring/assignments/bulk",
        headers=ADMIN,
        json={
            "method": "winrm",
            "credential_id": credential["id"],
            "scope": "cidr_all",
            "cidr": "192.168.248.0/30",
            "site": "monitoring-test",
            "interval_seconds": 60,
        },
    )
    assert bulk.status_code == 200, bulk.text
    assert bulk.json()["targets"] == 2

    monitors = client.get("/api/v1/monitoring/assignments", headers=ADMIN)
    assert monitors.status_code == 200
    ours = [m for m in monitors.json() if m["credential_id"] == credential["id"]]
    assert len(ours) == 2
    assert {m["device_id"] for m in ours} == {first["id"], second["id"]}


def test_selected_scope_rejects_empty_selection():
    suffix = uuid.uuid4().hex[:8]
    cred = client.post(
        "/api/v1/credentials",
        headers=ADMIN,
        json={
            "name": f"ssh-{suffix}",
            "credential_type": "ssh_password",
            "username": "monitor",
            "secret": "not-a-real-password",
            "options": {},
        },
    ).json()
    response = client.post(
        "/api/v1/monitoring/assignments/bulk",
        headers=ADMIN,
        json={"method": "ssh", "credential_id": cred["id"], "scope": "selected", "targets": []},
    )
    assert response.status_code == 400


def test_selected_scope_does_not_create_missing_assets():
    from app.db import SessionLocal
    from app.models import Device

    suffix = uuid.uuid4().hex[:8]
    target = "10.253.19.77"
    cred = client.post(
        "/api/v1/credentials",
        headers=ADMIN,
        json={
            "name": f"no-implicit-asset-{suffix}",
            "credential_type": "ssh_password",
            "username": "monitor",
            "secret": "not-a-real-password",
            "options": {},
        },
    ).json()
    response = client.post(
        "/api/v1/monitoring/assignments/bulk",
        headers=ADMIN,
        json={"method": "ssh", "credential_id": cred["id"], "scope": "selected", "targets": [target]},
    )
    assert response.status_code == 409
    assert "add or discover first" in response.text

    db = SessionLocal()
    try:
        assert db.query(Device).filter(Device.ip_address == target).count() == 0
    finally:
        db.close()


def test_entire_24_assigns_only_preexisting_assets_without_duplicates():
    from app.db import SessionLocal
    from app.models import AgentlessMonitor, CredentialProfile, Device

    suffix = uuid.uuid4().hex[:8]
    credential = client.post(
        "/api/v1/credentials",
        headers=ADMIN,
        json={
            "name": f"cidr24-{suffix}",
            "credential_type": "ssh_password",
            "username": "monitor",
            "secret": "not-a-real-password",
            "options": {"port": 22},
        },
    )
    assert credential.status_code == 200, credential.text
    credential_id = credential.json()["id"]
    site = f"cidr24-test-{suffix}"

    db = SessionLocal()
    try:
        for host in range(1, 255):
            db.add(Device(ip_address=f"10.254.17.{host}", site=site, state="unknown", device_class="unknown"))
        db.commit()
        baseline_count = db.query(Device).count()
    finally:
        db.close()

    first = client.post(
        "/api/v1/monitoring/assignments/bulk",
        headers=ADMIN,
        json={
            "method": "ssh",
            "credential_id": credential_id,
            "scope": "cidr_all",
            "cidr": "10.254.17.0/24",
            "site": site,
            "interval_seconds": 60,
        },
    )
    assert first.status_code == 200, first.text
    assert first.json() == {"targets": 254, "created": 254, "updated": 0}

    second = client.post(
        "/api/v1/monitoring/assignments/bulk",
        headers=ADMIN,
        json={
            "method": "ssh",
            "credential_id": credential_id,
            "scope": "cidr_all",
            "cidr": "10.254.17.0/24",
            "site": site,
            "interval_seconds": 120,
        },
    )
    assert second.status_code == 200, second.text
    assert second.json() == {"targets": 254, "created": 0, "updated": 254}

    db = SessionLocal()
    try:
        devices = db.query(Device).filter(Device.site == site).all()
        device_ids = [device.id for device in devices]
        monitors = db.query(AgentlessMonitor).filter(AgentlessMonitor.device_id.in_(device_ids)).all()
        assert len(devices) == 254
        assert len(monitors) == 254
        assert len({device.ip_address for device in devices}) == 254
        assert all(monitor.interval_seconds == 120 for monitor in monitors)
        assert db.query(Device).count() == baseline_count

        for monitor in monitors:
            db.delete(monitor)
        for device in devices:
            db.delete(device)
        credential_row = db.get(CredentialProfile, credential_id)
        if credential_row:
            db.delete(credential_row)
        db.commit()
    finally:
        db.close()


def test_snmp_exporter_targets_can_derive_from_snmp_monitoring_assignment():
    suffix = uuid.uuid4().hex[:8]
    octet = int(suffix[:2], 16) % 200 + 20
    ip_address = f"10.251.40.{octet}"
    asset = _create_asset(ip_address, site=f"snmp-unified-{suffix}")

    credential = client.post(
        "/api/v1/credentials",
        headers=ADMIN,
        json={
            "name": f"snmp-unified-{suffix}",
            "credential_type": "snmp_v2",
            "username": None,
            "secret": "qa-community-not-returned",
            "options": {
                "exporter_auth": "public_v2",
                "exporter_module": "if_mib",
            },
        },
    )
    assert credential.status_code == 200, credential.text
    credential_id = credential.json()["id"]

    assignment = client.post(
        "/api/v1/monitoring/assignments/bulk",
        headers=ADMIN,
        json={
            "method": "snmp",
            "credential_id": credential_id,
            "scope": "selected",
            "targets": [ip_address],
            "interval_seconds": 60,
        },
    )
    assert assignment.status_code == 200, assignment.text
    assert assignment.json()["created"] == 1

    targets = client.get("/api/v1/targets/snmp")
    assert targets.status_code == 200, targets.text
    ours = [row for row in targets.json() if row["targets"] == [ip_address]]
    assert len(ours) == 1
    labels = ours[0]["labels"]
    assert labels["source"] == "monitoring_assignment"
    assert labels["snmp_module"] == "if_mib"
    assert labels["snmp_auth"] == "public_v2"
    assert labels["host_id"] == asset["id"]
    assert "community" not in str(ours[0]).lower()

    monitors = client.get("/api/v1/monitoring/assignments", headers=ADMIN).json()
    monitor = next(row for row in monitors if row["credential_id"] == credential_id)
    assert client.delete(f"/api/v1/monitoring/assignments/{monitor['id']}", headers=ADMIN).status_code == 200
    assert client.delete(f"/api/v1/credentials/{credential_id}", headers=ADMIN).status_code == 200
    assert client.delete(f"/api/v1/devices/{asset['id']}", headers=ADMIN).status_code == 200
