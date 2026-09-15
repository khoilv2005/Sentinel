import uuid
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
ADMIN = {"X-API-Key": "change-me-now"}


def test_agentless_credentials_and_cidr_modes():
    suffix = uuid.uuid4().hex[:8]
    name = f"agentless-{suffix}"
    created = client.post("/api/v1/credentials", headers=ADMIN, json={
        "name": name, "credential_type": "winrm", "username": "monitor",
        "secret": "not-a-real-password", "options": {"transport": "ntlm"},
    })
    assert created.status_code == 200, created.text
    credential = created.json()
    assert credential["has_secret"] is True
    assert "secret" not in credential and "secret_encrypted" not in credential

    rows = client.get("/api/v1/credentials", headers=ADMIN)
    assert rows.status_code == 200
    row = next(x for x in rows.json() if x["id"] == credential["id"])
    assert "secret" not in row and "secret_encrypted" not in row

    candidates = client.get("/api/v1/agentless/candidates?cidr=192.168.248.0/30", headers=ADMIN)
    assert candidates.status_code == 200, candidates.text
    assert [x["ip_address"] for x in candidates.json()] == ["192.168.248.1", "192.168.248.2"]

    bulk = client.post("/api/v1/agentless/monitors/bulk", headers=ADMIN, json={
        "method": "winrm", "credential_id": credential["id"], "scope": "cidr_all",
        "cidr": "192.168.248.0/30", "site": "agentless-test", "interval_seconds": 60,
    })
    assert bulk.status_code == 200, bulk.text
    assert bulk.json()["targets"] == 2

    monitors = client.get("/api/v1/agentless/monitors", headers=ADMIN)
    assert monitors.status_code == 200
    ours = [m for m in monitors.json() if m["credential_id"] == credential["id"]]
    assert len(ours) == 2


def test_agentless_selected_scope_rejects_empty_selection():
    suffix = uuid.uuid4().hex[:8]
    cred = client.post("/api/v1/credentials", headers=ADMIN, json={
        "name": f"ssh-{suffix}", "credential_type": "ssh_password", "username": "monitor",
        "secret": "not-a-real-password", "options": {},
    }).json()
    response = client.post("/api/v1/agentless/monitors/bulk", headers=ADMIN, json={
        "method": "ssh", "credential_id": cred["id"], "scope": "selected", "targets": [],
    })
    assert response.status_code == 400


def test_agentless_entire_24_creates_254_unique_assignments():
    from app.db import SessionLocal
    from app.models import AgentlessMonitor, CredentialProfile, Device

    suffix = uuid.uuid4().hex[:8]
    credential = client.post("/api/v1/credentials", headers=ADMIN, json={
        "name": f"cidr24-{suffix}", "credential_type": "ssh_password", "username": "monitor",
        "secret": "not-a-real-password", "options": {"port": 22},
    })
    assert credential.status_code == 200, credential.text
    credential_id = credential.json()["id"]
    cidr = "10.254.17.0/24"
    site = f"cidr24-test-{suffix}"

    first = client.post("/api/v1/agentless/monitors/bulk", headers=ADMIN, json={
        "method": "ssh", "credential_id": credential_id, "scope": "cidr_all",
        "cidr": cidr, "site": site, "interval_seconds": 60,
    })
    assert first.status_code == 200, first.text
    assert first.json() == {"targets": 254, "created": 254, "updated": 0}

    second = client.post("/api/v1/agentless/monitors/bulk", headers=ADMIN, json={
        "method": "ssh", "credential_id": credential_id, "scope": "cidr_all",
        "cidr": cidr, "site": site, "interval_seconds": 120,
    })
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
