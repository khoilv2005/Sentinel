import uuid

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import NotificationChannel


client = TestClient(app)
ADMIN = {"X-API-Key": "change-me-now"}


def test_notification_channel_config_is_encrypted_at_rest_and_redacted_in_api():
    suffix = uuid.uuid4().hex[:8]
    secret_path = f"hook-{uuid.uuid4().hex}"
    name = f"encrypted-webhook-{suffix}"
    raw_url = f"https://notify.example.invalid/{secret_path}"

    created = client.post(
        "/api/v1/notification-channels",
        headers=ADMIN,
        json={
            "name": name,
            "channel_type": "webhook",
            "enabled": True,
            "config": {"url": raw_url, "timeout": 3},
        },
    )
    assert created.status_code == 200, created.text
    body = created.json()
    channel_id = body["id"]
    assert body["config"]["url"] == "https://notify.example.invalid/***"
    assert secret_path not in created.text

    db = SessionLocal()
    try:
        row = db.get(NotificationChannel, channel_id)
        assert row is not None
        stored = row.config or {}
        assert set(stored) == {"_encrypted"}
        assert raw_url not in str(stored)
        assert secret_path not in str(stored)
    finally:
        db.close()

    listed = client.get("/api/v1/notification-channels", headers=ADMIN)
    assert listed.status_code == 200, listed.text
    item = next(value for value in listed.json() if value["id"] == channel_id)
    assert item["config"]["url"] == "https://notify.example.invalid/***"
    assert secret_path not in listed.text

    deleted = client.delete(f"/api/v1/notification-channels/{channel_id}", headers=ADMIN)
    assert deleted.status_code == 200, deleted.text
