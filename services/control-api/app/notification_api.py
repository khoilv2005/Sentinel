from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from .db import get_db
from .maintenance_api import router as maintenance_router
from .models import AuditEvent, NotificationChannel
from .notification_engine import (
    enqueue_test_delivery,
    pack_notification_config,
    process_delivery,
    redact_config,
    unpack_notification_config,
    validate_channel_config,
)
from .notification_models import NotificationDelivery
from .security import control_identity, require_write


# This router is included under the existing /api/v1 agentless router so new
# notification endpoints can be added without changing the monolithic main.py.
router = APIRouter(tags=["notifications"])


def _audit(db: Session, actor: str, action: str, object_type: str, object_id: str | None, message: str, details: dict | None = None):
    db.add(AuditEvent(
        actor=actor,
        action=action,
        object_type=object_type,
        object_id=object_id,
        message=message,
        details=details or {},
    ))


def channel_out(row: NotificationChannel) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "channel_type": row.channel_type,
        "enabled": row.enabled,
        "config": redact_config(unpack_notification_config(row.config)),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def delivery_out(row: NotificationDelivery) -> dict:
    return {
        "id": row.id,
        "channel_id": row.channel_id,
        "problem_id": row.problem_id,
        "device_id": row.device_id,
        "transition": row.transition,
        "severity": row.severity,
        "status": row.status,
        "attempts": row.attempts,
        "last_error": row.last_error,
        "next_attempt_at": row.next_attempt_at,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "sent_at": row.sent_at,
    }


@router.get("/notification-channels")
def list_notification_channels(
    identity: dict = Depends(control_identity),
    db: Session = Depends(get_db),
):
    rows = db.execute(select(NotificationChannel).order_by(NotificationChannel.name)).scalars()
    return [channel_out(row) for row in rows]


@router.post("/notification-channels")
def create_notification_channel(
    payload: dict,
    identity: dict = Depends(require_write),
    db: Session = Depends(get_db),
):
    name = str(payload.get("name") or "").strip()
    channel_type = str(payload.get("channel_type") or "webhook").strip()
    enabled = bool(payload.get("enabled", True))
    config = payload.get("config") or {}
    if not name or len(name) > 160:
        raise HTTPException(400, "notification channel name is required and must be at most 160 characters")
    if channel_type not in {"webhook", "email", "slack", "teams", "telegram"}:
        raise HTTPException(400, "unsupported notification channel type")
    if not isinstance(config, dict):
        raise HTTPException(400, "notification channel config must be an object")
    if db.execute(select(NotificationChannel).where(NotificationChannel.name == name)).scalar_one_or_none():
        raise HTTPException(409, "notification channel name already exists")
    try:
        validate_channel_config(channel_type, config)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    row = NotificationChannel(
        name=name,
        channel_type=channel_type,
        enabled=enabled,
        config=pack_notification_config(config),
    )
    db.add(row)
    db.flush()
    _audit(db, identity["username"], "create", "notification_channel", row.id, f"Created channel {row.name}", {"type": row.channel_type})
    db.commit()
    db.refresh(row)
    return channel_out(row)


@router.delete("/notification-channels/{channel_id}")
def delete_notification_channel(
    channel_id: str,
    identity: dict = Depends(require_write),
    db: Session = Depends(get_db),
):
    row = db.get(NotificationChannel, channel_id)
    if row is None:
        raise HTTPException(404, "notification channel not found")
    name = row.name
    for delivery in db.execute(select(NotificationDelivery).where(NotificationDelivery.channel_id == channel_id)).scalars():
        db.delete(delivery)
    db.delete(row)
    _audit(db, identity["username"], "delete", "notification_channel", channel_id, f"Deleted channel {name}")
    db.commit()
    return {"deleted": channel_id}


@router.get("/notification-deliveries")
def list_notification_deliveries(
    status: str | None = None,
    limit: int = Query(100, ge=1, le=1000),
    identity: dict = Depends(control_identity),
    db: Session = Depends(get_db),
):
    stmt = select(NotificationDelivery).order_by(desc(NotificationDelivery.created_at)).limit(limit)
    if status:
        stmt = stmt.where(NotificationDelivery.status == status)
    return [delivery_out(row) for row in db.execute(stmt).scalars()]


@router.post("/notification-channels/{channel_id}/test")
def test_notification_channel(
    channel_id: str,
    identity: dict = Depends(require_write),
    db: Session = Depends(get_db),
):
    channel = db.get(NotificationChannel, channel_id)
    if channel is None:
        raise HTTPException(404, "notification channel not found")
    if not channel.enabled:
        raise HTTPException(409, "notification channel is disabled")
    delivery = enqueue_test_delivery(db, channel, identity["username"])
    db.commit()
    db.refresh(delivery)
    process_delivery(db, delivery)
    return delivery_out(delivery)


router.include_router(maintenance_router)
