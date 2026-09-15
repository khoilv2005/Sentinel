from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from .db import get_db
from .maintenance_engine import availability_for_device
from .models import AuditEvent, Device, MaintenanceWindow, SlaDefinition
from .monitoring import sync_problems
from .security import control_identity, require_write


router = APIRouter(tags=["maintenance"])


def _audit(db: Session, actor: str, action: str, object_type: str, object_id: str | None, message: str, details: dict | None = None):
    db.add(AuditEvent(
        actor=actor,
        action=action,
        object_type=object_type,
        object_id=object_id,
        message=message,
        details=details or {},
    ))


def maintenance_out(row: MaintenanceWindow) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "device_id": row.device_id,
        "site": row.site,
        "starts_at": row.starts_at,
        "ends_at": row.ends_at,
        "suppress_notifications": row.suppress_notifications,
        "exclude_from_sla": row.exclude_from_sla,
        "created_by": row.created_by,
        "created_at": row.created_at,
    }


@router.get("/maintenance")
def list_maintenance(
    identity: dict = Depends(control_identity),
    db: Session = Depends(get_db),
):
    return [maintenance_out(row) for row in db.execute(
        select(MaintenanceWindow).order_by(desc(MaintenanceWindow.starts_at))
    ).scalars()]


@router.post("/maintenance")
def create_maintenance(
    payload: dict,
    identity: dict = Depends(require_write),
    db: Session = Depends(get_db),
):
    name = str(payload.get("name") or "").strip()
    if not name or len(name) > 255:
        raise HTTPException(400, "maintenance name is required and must be at most 255 characters")
    try:
        starts_at = datetime.fromisoformat(str(payload.get("starts_at") or "").replace("Z", "+00:00"))
        ends_at = datetime.fromisoformat(str(payload.get("ends_at") or "").replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(400, "starts_at and ends_at must be ISO-8601 datetimes") from exc
    if starts_at.tzinfo is None:
        starts_at = starts_at.replace(tzinfo=timezone.utc)
    if ends_at.tzinfo is None:
        ends_at = ends_at.replace(tzinfo=timezone.utc)
    if ends_at <= starts_at:
        raise HTTPException(400, "ends_at must be after starts_at")

    device_id = payload.get("device_id") or None
    site = str(payload.get("site") or "").strip() or None
    if device_id and db.get(Device, str(device_id)) is None:
        raise HTTPException(404, "maintenance target device not found")

    row = MaintenanceWindow(
        name=name,
        device_id=str(device_id) if device_id else None,
        site=site,
        starts_at=starts_at,
        ends_at=ends_at,
        suppress_notifications=bool(payload.get("suppress_notifications", True)),
        exclude_from_sla=bool(payload.get("exclude_from_sla", True)),
        created_by=identity["username"],
    )
    db.add(row)
    db.flush()
    _audit(db, identity["username"], "create", "maintenance", row.id, f"Created maintenance {row.name}")
    db.commit()
    db.refresh(row)
    sync_problems(db)
    return maintenance_out(row)


@router.delete("/maintenance/{window_id}")
def delete_maintenance(
    window_id: str,
    identity: dict = Depends(require_write),
    db: Session = Depends(get_db),
):
    row = db.get(MaintenanceWindow, window_id)
    if row is None:
        raise HTTPException(404, "maintenance window not found")
    name = row.name
    db.delete(row)
    _audit(db, identity["username"], "delete", "maintenance", window_id, f"Deleted maintenance {name}")
    db.commit()
    sync_problems(db)
    return {"deleted": window_id}


@router.get("/availability")
def availability(
    identity: dict = Depends(control_identity),
    db: Session = Depends(get_db),
):
    rows = []
    for device in db.execute(select(Device).order_by(Device.hostname, Device.ip_address)).scalars():
        rows.append({
            "device_id": device.id,
            "hostname": device.hostname or device.ip_address,
            "ip_address": device.ip_address,
            "site": device.site,
            "state": device.state,
            "availability_24h": availability_for_device(db, device, 24),
            "availability_7d": availability_for_device(db, device, 24 * 7),
            "availability_30d": availability_for_device(db, device, 24 * 30),
        })

    slas = []
    for sla in db.execute(select(SlaDefinition).where(SlaDefinition.enabled.is_(True))).scalars():
        targets = [
            row for row in rows
            if (sla.device_id is None or row["device_id"] == sla.device_id)
            and (sla.site is None or row["site"] == sla.site)
        ]
        values = [row["availability_30d"] for row in targets if row["availability_30d"] is not None]
        current = round(sum(values) / len(values), 4) if values else None
        slas.append({
            "id": sla.id,
            "name": sla.name,
            "target_percent": sla.target_percent,
            "current_percent": current,
            "status": "pass" if current is not None and current >= sla.target_percent else "fail" if current is not None else "unknown",
        })

    return {
        "hosts": rows,
        "slas": slas,
        "history_note": "Availability is calculated from state-change events. Maintenance windows marked exclude_from_sla are removed from the eligible SLA denominator.",
    }
