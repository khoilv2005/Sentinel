from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
ADMIN = {"X-API-Key": "change-me-now"}


def test_assets_api_matches_legacy_hosts_view():
    assets = client.get("/api/v1/assets", headers=ADMIN)
    hosts = client.get("/api/v1/hosts", headers=ADMIN)

    assert assets.status_code == 200, assets.text
    assert hosts.status_code == 200, hosts.text
    assert {row["id"] for row in assets.json()} == {row["id"] for row in hosts.json()}


def test_openapi_prefers_assets_and_unified_monitoring_names():
    schema = client.get("/openapi.json").json()
    paths = schema["paths"]

    assert "/api/v1/assets" in paths
    assert "/api/v1/assets/{device_id}/overview" in paths
    assert "/api/v1/assets/{device_id}/metrics" in paths
    assert "/api/v1/monitoring/assignments" in paths

    assert "/api/v1/hosts" not in paths
    assert "/api/v1/agentless/monitors" not in paths
