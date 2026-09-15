from datetime import datetime, timezone
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
ADMIN = {"X-API-Key": "change-me-now"}


def test_managed_agent_enrollment_and_outbound_telemetry():
    policies = client.get("/api/v1/agent-policies", headers=ADMIN).json()
    assert policies
    policy_id = policies[0]["id"]

    token_resp = client.post(
        "/api/v1/agents/enrollment-tokens",
        headers=ADMIN,
        json={"policy_id": policy_id, "site": "test-lab", "expires_in_minutes": 30, "max_uses": 1},
    )
    assert token_resp.status_code == 200, token_resp.text
    token = token_resp.json()["token"]
    assert token.startswith("sv_enr_")

    enroll = client.post(
        "/api/v1/agents/enroll",
        json={
            "enrollment_token": token,
            "hostname": "qa-win01",
            "os_name": "windows",
            "arch": "amd64",
            "version": "0.3.0",
            "ip_address": "192.168.250.10",
            "site": "test-lab",
            "tags": ["qa"],
        },
    )
    assert enroll.status_code == 200, enroll.text
    data = enroll.json()
    assert data["agent_token"].startswith("sv_agt_")
    bearer = {"Authorization": f"Bearer {data['agent_token']}"}

    second_use = client.post(
        "/api/v1/agents/enroll",
        json={
            "enrollment_token": token,
            "hostname": "qa-win02",
            "os_name": "windows",
            "arch": "amd64",
            "version": "0.3.0",
        },
    )
    assert second_use.status_code == 401

    checkin = client.post(
        "/api/v1/agents/checkin",
        headers=bearer,
        json={"hostname": "qa-win01", "version": "0.3.0", "ip_address": "192.168.250.10"},
    )
    assert checkin.status_code == 200, checkin.text
    assert checkin.json()["policy_id"] == policy_id

    telemetry = client.post(
        "/api/v1/agents/telemetry",
        headers=bearer,
        json={
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "cpu_usage_percent": 31.5,
            "memory_total_bytes": 17179869184,
            "memory_used_bytes": 8589934592,
            "memory_usage_percent": 50.0,
            "uptime_seconds": 12345,
            "process_count": 210,
            "disks": [{"mountpoint": "C:\\\\", "fstype": "NTFS", "total_bytes": 1000, "used_bytes": 500, "usage_percent": 50}],
            "interfaces": [{"name": "Ethernet", "receive_bytes_total": 10000, "transmit_bytes_total": 5000}],
        },
    )
    assert telemetry.status_code == 200, telemetry.text

    agents = client.get("/api/v1/agents", headers=ADMIN).json()
    assert any(a["hostname"] == "qa-win01" and a["online"] for a in agents)

    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    assert 'sentinel_cpu_usage_percent' in metrics.text
    assert 'hostname="qa-win01"' in metrics.text
    assert 'sentinel_agent_up' in metrics.text


def test_bootstrap_installers_verify_download_hashes():
    win = client.get("/install/windows.ps1")
    assert win.status_code == 200
    assert "Get-FileHash" in win.text
    assert "sentinel-agent-windows-amd64.exe.sha256" in win.text

    linux = client.get("/install/linux.sh")
    assert linux.status_code == 200
    assert "sha256sum" in linux.text
    assert "sentinel-agent-linux-amd64" in linux.text


def test_token_listing_never_returns_plaintext_token():
    policies = client.get("/api/v1/agent-policies", headers=ADMIN).json()
    created = client.post(
        "/api/v1/agents/enrollment-tokens",
        headers=ADMIN,
        json={"policy_id": policies[0]["id"], "expires_in_minutes": 5, "max_uses": 1},
    ).json()
    rows = client.get("/api/v1/agents/enrollment-tokens", headers=ADMIN).json()
    matching = next(row for row in rows if row["id"] == created["id"])
    assert "token" not in matching
    assert "token_hash" not in matching
    assert matching["token_prefix"] == created["token_prefix"]


def test_reenrollment_rotates_credential_without_duplicate_device_agent():
    policy_id = client.get("/api/v1/agent-policies", headers=ADMIN).json()[0]["id"]
    def mint():
        return client.post(
            "/api/v1/agents/enrollment-tokens",
            headers=ADMIN,
            json={"policy_id": policy_id, "site": "reinstall-lab", "expires_in_minutes": 30, "max_uses": 1},
        ).json()["token"]

    first = client.post("/api/v1/agents/enroll", json={
        "enrollment_token": mint(), "hostname": "reinstall-win", "os_name": "windows",
        "arch": "amd64", "version": "0.3.0", "ip_address": "192.168.250.20",
    }).json()
    old_credential = first["agent_token"]

    second_resp = client.post("/api/v1/agents/enroll", json={
        "enrollment_token": mint(), "hostname": "reinstall-win", "os_name": "windows",
        "arch": "amd64", "version": "0.3.0", "ip_address": "192.168.250.20",
    })
    assert second_resp.status_code == 200, second_resp.text
    second = second_resp.json()
    assert second["agent_id"] == first["agent_id"]
    assert second["device_id"] == first["device_id"]
    assert second["agent_token"] != old_credential

    old_checkin = client.post(
        "/api/v1/agents/checkin",
        headers={"Authorization": f"Bearer {old_credential}"},
        json={"hostname": "reinstall-win", "version": "0.3.0"},
    )
    assert old_checkin.status_code == 401
