from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
ADMIN = {"X-API-Key": "change-me-now"}


def ui_auth():
    response = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin"})
    assert response.status_code == 200, response.text
    token = response.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def test_ui_login_and_session_authorize_mutations():
    headers = ui_auth()
    me = client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["username"] == "admin"
    assert me.json()["role"] == "admin"

    scan = client.post(
        "/api/v1/discovery/scans",
        headers=headers,
        json={"cidr": "192.168.252.0/30", "site": "ui-test"},
    )
    assert scan.status_code == 200, scan.text


def test_first_party_overview_hosts_services_and_problems():
    headers = ui_auth()
    policies = client.get("/api/v1/agent-policies", headers=ADMIN).json()
    token_response = client.post(
        "/api/v1/agents/enrollment-tokens",
        headers=headers,
        json={"policy_id": policies[0]["id"], "site": "ui-test", "expires_in_minutes": 30, "max_uses": 1},
    )
    assert token_response.status_code == 200, token_response.text
    enrollment = client.post(
        "/api/v1/agents/enroll",
        json={
            "enrollment_token": token_response.json()["token"],
            "hostname": "ui-highcpu-01",
            "os_name": "windows",
            "arch": "amd64",
            "version": "0.3.0",
            "ip_address": "192.168.252.10",
            "site": "ui-test",
            "tags": ["ui"],
        },
    )
    assert enrollment.status_code == 200, enrollment.text
    bearer = {"Authorization": f"Bearer {enrollment.json()['agent_token']}"}
    telemetry = client.post(
        "/api/v1/agents/telemetry",
        headers=bearer,
        json={
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "cpu_usage_percent": 99.0,
            "memory_total_bytes": 1000,
            "memory_used_bytes": 900,
            "memory_usage_percent": 90.0,
            "uptime_seconds": 500,
            "process_count": 100,
            "disks": [{"mountpoint": "C:\\", "fstype": "NTFS", "total_bytes": 1000, "used_bytes": 970, "usage_percent": 97.0}],
            "interfaces": [{"name": "Ethernet", "receive_bytes_total": 1, "transmit_bytes_total": 1}],
        },
    )
    assert telemetry.status_code == 200, telemetry.text

    overview = client.get("/api/v1/ui/overview", headers=headers)
    assert overview.status_code == 200, overview.text
    assert overview.json()["hosts"]["total"] >= 1

    hosts = client.get("/api/v1/hosts", headers=headers)
    assert hosts.status_code == 200
    host = next(h for h in hosts.json() if h["hostname"] == "ui-highcpu-01")
    assert host["service_count"] >= 5
    assert host["problem_count"] >= 1

    services = client.get(f"/api/v1/services?host_id={host['id']}", headers=headers)
    assert services.status_code == 200
    assert any(s["service_name"] == "CPU utilization" and s["state"] == "critical" for s in services.json())

    problems = client.get(f"/api/v1/problems?device_id={host['id']}", headers=headers)
    assert problems.status_code == 200
    assert any(p["severity"] == "critical" for p in problems.json())


def test_platform_settings_topology_integrations_and_availability():
    headers = ui_auth()
    assert client.get("/api/v1/platform/settings", headers=headers).status_code == 200
    assert client.get("/api/v1/topology/graph", headers=headers).status_code == 200
    integrations = client.get("/api/v1/integrations", headers=headers)
    assert integrations.status_code == 200
    assert any(i["id"] == "windows" and i["status"] == "available" for i in integrations.json())
    assert client.get("/api/v1/availability", headers=headers).status_code == 200


def test_viewer_session_can_read_but_cannot_mutate():
    admin = ui_auth()
    username = "viewer-qa"
    created = client.post(
        "/api/v1/users",
        headers=admin,
        json={"username": username, "password": "viewer-pass-123", "role": "viewer"},
    )
    if created.status_code == 409:
        users = client.get("/api/v1/users", headers=admin).json()
        user = next(u for u in users if u["username"] == username)
        client.patch(f"/api/v1/users/{user['id']}", headers=admin, json={"password": "viewer-pass-123", "role": "viewer", "enabled": True})
    else:
        assert created.status_code == 200, created.text

    login_response = client.post("/api/v1/auth/login", json={"username": username, "password": "viewer-pass-123"})
    assert login_response.status_code == 200, login_response.text
    viewer = {"Authorization": f"Bearer {login_response.json()['token']}"}
    assert client.get("/api/v1/hosts", headers=viewer).status_code == 200
    blocked = client.post(
        "/api/v1/discovery/scans",
        headers=viewer,
        json={"cidr": "192.168.253.0/30", "site": "viewer-test"},
    )
    assert blocked.status_code == 403
