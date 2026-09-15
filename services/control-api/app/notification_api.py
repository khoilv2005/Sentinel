from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from .db import get_db
from .models import NotificationChannel
from .notification_engine import enqueue_test_delivery, process_delivery
from .notification_models import NotificationDelivery
from .security import control_identity, require_write


router = APIRouter(prefix="/api/v1", tags=["notifications"])


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
