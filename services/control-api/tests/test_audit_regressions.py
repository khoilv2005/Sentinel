import uuid

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app, ensure_bootstrap_data
from app.models import AlertRule, LocalUser


client = TestClient(app)
ADMIN = {"X-API-Key": "change-me-now"}


def test_bootstrap_allows_multiple_rules_for_same_metric():
    name = f"QA duplicate CPU {uuid.uuid4().hex[:8]}"
    db = SessionLocal()
    try:
        row = AlertRule(
            name=name,
            metric="sentinel_cpu_usage_percent",
            operator=">",
            warning_threshold=70.0,
            critical_threshold=90.0,
            duration_seconds=0,
            enabled=True,
            match_labels={},
        )
        db.add(row)
        db.commit()
    finally:
        db.close()

    try:
        # Regression for BUG-001: this used to raise MultipleResultsFound because
        # bootstrap looked up its defaults by metric rather than rule identity.
        ensure_bootstrap_data()
        db = SessionLocal()
        try:
            cpu_rules = list(db.query(AlertRule).filter(AlertRule.metric == "sentinel_cpu_usage_percent").all())
            assert len(cpu_rules) >= 2
            assert any(rule.name == "CPU utilization" for rule in cpu_rules)
            assert any(rule.name == name for rule in cpu_rules)
        finally:
            db.close()
    finally:
        db = SessionLocal()
        try:
            row = db.query(AlertRule).filter(AlertRule.name == name).first()
            if row:
                db.delete(row)
                db.commit()
        finally:
            db.close()


def test_disabled_user_invalidates_existing_bearer_session_and_role_changes_are_live():
    username = f"qa-session-{uuid.uuid4().hex[:8]}"
    password = "qa-session-pass-123"
    created = client.post(
        "/api/v1/users",
        headers=ADMIN,
        json={"username": username, "password": password, "role": "viewer"},
    )
    assert created.status_code == 200, created.text
    user_id = created.json()["id"]

    login = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert login.status_code == 200, login.text
    bearer = {"Authorization": f"Bearer {login.json()['token']}"}
    assert client.get("/api/v1/hosts", headers=bearer).status_code == 200

    blocked = client.post(
        "/api/v1/discovery/scans",
        headers=bearer,
        json={"cidr": "192.168.246.0/30", "site": "qa-role"},
    )
    assert blocked.status_code == 403

    promoted = client.patch(f"/api/v1/users/{user_id}", headers=ADMIN, json={"role": "operator"})
    assert promoted.status_code == 200, promoted.text
    allowed = client.post(
        "/api/v1/discovery/scans",
        headers=bearer,
        json={"cidr": "192.168.246.0/30", "site": "qa-role"},
    )
    assert allowed.status_code == 200, allowed.text

    disabled = client.patch(f"/api/v1/users/{user_id}", headers=ADMIN, json={"enabled": False})
    assert disabled.status_code == 200, disabled.text
    assert client.get("/api/v1/hosts", headers=bearer).status_code == 401

    db = SessionLocal()
    try:
        user = db.query(LocalUser).filter(LocalUser.id == user_id).first()
        if user:
            db.delete(user)
            db.commit()
    finally:
        db.close()
