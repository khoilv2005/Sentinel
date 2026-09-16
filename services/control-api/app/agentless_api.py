from __future__ import annotations

import ipaddress
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .agentless_collectors import collect_target
from .db import get_db
from .models import (
    AgentlessMonitor,
    AgentlessTelemetryLatest,
    AuditEvent,
    CredentialProfile,
    Device,
)
from .monitoring_models import MonitoringTelemetryLatest
from .monitoring_telemetry import refresh_device_compat_telemetry
from .netutils import parse_private_network
from .notification_api import router as notification_router
from .secretbox import decrypt_secrets, encrypt_secrets
from .security import control_identity, require_write


router = APIRouter(prefix="/api/v1", tags=["monitoring"])


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CredentialCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    credential_type: Literal["winrm", "ssh_password", "ssh_key", "snmp_v2", "snmp_v3"]
    username: str | None = Field(default=None, max_length=255)
    secret: str | None = Field(default=None, max_length=65535)
    secondary_secret: str | None = Field(default=None, max_length=4096)
    options: dict = Field(default_factory=dict)


class BulkMonitorCreate(BaseModel):
    method: Literal["winrm", "ssh", "snmp"]
    credential_id: str
    scope: Literal["selected", "discovered", "cidr_all"] = "selected"
    cidr: str | None = None
    targets: list[str] = Field(default_factory=list, max_length=4096)
    site: str | None = Field(default=None, max_length=160)
    interval_seconds: int = Field(default=60, ge=15, le=3600)


class MonitorTest(BaseModel):
    method: Literal["winrm", "ssh", "snmp"]
    credential_id: str
    target: str


def _audit(
    db: Session,
    actor: str,
    action: str,
    object_type: str,
    object_id: str | None,
    message: str,
    details: dict | None = None,
):
    db.add(
        AuditEvent(
            actor=actor,
            action=action,
            object_type=object_type,
            object_id=object_id,
            message=message,
            details=details or {},
        )
    )


def _credential_secrets(payload: CredentialCreate) -> dict[str, str]:
    secret = payload.secret or ""
    second = payload.secondary_secret or ""
    if payload.credential_type in {"winrm", "ssh_password"}:
        if not secret:
            raise HTTPException(400, "password is required")
        return {"password": secret}
    if payload.credential_type == "ssh_key":
        if not secret:
            raise HTTPException(400, "private key is required")
        return {"private_key": secret}
    if payload.credential_type == "snmp_v2":
        if not secret:
            raise HTTPException(400, "SNMP community is required")
        return {"community": secret}
    if payload.credential_type == "snmp_v3":
        values = {"auth_password": secret}
        if second:
            values["privacy_password"] = second
        return values
    raise HTTPException(400, "unsupported credential type")


def _credential_out(row: CredentialProfile) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "credential_type": row.credential_type,
        "username": row.username,
        "options": row.options_json or {},
        "enabled": row.enabled,
        "has_secret": bool(row.secret_encrypted),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _validate_method(credential: CredentialProfile, method: str):
    allowed = {
        "winrm": {"winrm"},
        "ssh": {"ssh_password", "ssh_key"},
        "snmp": {"snmp_v2", "snmp_v3"},
    }
    if credential.credential_type not in allowed[method]:
        raise HTTPException(
            400,
            f"credential type {credential.credential_type} is not valid for {method}",
        )


def _private_ip(value: str) -> str:
    try:
        ip = ipaddress.ip_address(value)
    except ValueError as exc:
        raise HTTPException(400, f"invalid IP address: {value}") from exc
    if not (ip.is_private or ip.is_link_local or ip.is_loopback):
        raise HTTPException(400, "monitoring is limited to private/link-local targets")
    return str(ip)


def _in_network(ip_value: str, net) -> bool:
    try:
        return ipaddress.ip_address(ip_value) in net
    except ValueError:
        return False


def _ensure_inventory_targets(db: Session, targets: list[str]) -> list[str]:
    devices = {row.ip_address: row for row in db.execute(select(Device)).scalars()}
    missing = [target for target in targets if target not in devices]
    if missing:
        preview = ", ".join(missing[:5])
        suffix = "" if len(missing) <= 5 else f" (+{len(missing) - 5} more)"
        raise HTTPException(
            409,
            "monitoring can only be assigned to existing assets; "
            f"add or discover first: {preview}{suffix}",
        )
    return targets


@router.get("/credentials")
def list_credentials(
    identity: dict = Depends(control_identity),
    db: Session = Depends(get_db),
):
    return [
        _credential_out(row)
        for row in db.execute(
            select(CredentialProfile).order_by(CredentialProfile.name)
        ).scalars()
    ]


@router.post("/credentials")
def create_credential(
    payload: CredentialCreate,
    identity: dict = Depends(require_write),
    db: Session = Depends(get_db),
):
    if db.execute(
        select(CredentialProfile).where(CredentialProfile.name == payload.name)
    ).scalar_one_or_none():
        raise HTTPException(409, "credential profile name already exists")
    row = CredentialProfile(
        name=payload.name,
        credential_type=payload.credential_type,
        username=payload.username,
        secret_encrypted=encrypt_secrets(_credential_secrets(payload)),
        options_json=payload.options,
        enabled=True,
    )
    db.add(row)
    db.flush()
    _audit(
        db,
        identity["username"],
        "create",
        "credential",
        row.id,
        f"Created credential profile {row.name}",
        {"type": row.credential_type},
    )
    db.commit()
    db.refresh(row)
    return _credential_out(row)


@router.delete("/credentials/{credential_id}")
def delete_credential(
    credential_id: str,
    identity: dict = Depends(require_write),
    db: Session = Depends(get_db),
):
    row = db.get(CredentialProfile, credential_id)
    if row is None:
        raise HTTPException(404, "credential profile not found")
    if db.execute(
        select(AgentlessMonitor).where(
            AgentlessMonitor.credential_id == credential_id,
            AgentlessMonitor.enabled.is_(True),
        )
    ).scalar_one_or_none():
        raise HTTPException(409, "credential is used by an enabled monitor")
    name = row.name
    db.delete(row)
    _audit(
        db,
        identity["username"],
        "delete",
        "credential",
        credential_id,
        f"Deleted credential profile {name}",
    )
    db.commit()
    return {"deleted": credential_id}


@router.get("/agentless/candidates", deprecated=True)
@router.get("/monitoring/candidates")
def list_candidates(
    cidr: str,
    identity: dict = Depends(control_identity),
    db: Session = Depends(get_db),
):
    try:
        net = parse_private_network(cidr)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    devices = {
        d.ip_address: d
        for d in db.execute(select(Device)).scalars()
        if _in_network(d.ip_address, net)
    }
    return [
        {
            "ip_address": str(ip),
            "device_id": devices.get(str(ip)).id if devices.get(str(ip)) else None,
            "hostname": devices.get(str(ip)).hostname if devices.get(str(ip)) else None,
            "state": devices.get(str(ip)).state if devices.get(str(ip)) else "unseen",
            "discovered": str(ip) in devices,
        }
        for ip in net.hosts()
    ]


def _targets_for_request(payload: BulkMonitorCreate, db: Session) -> list[str]:
    if payload.scope == "selected":
        if not payload.targets:
            raise HTTPException(400, "select at least one target")
        return _ensure_inventory_targets(
            db,
            list(dict.fromkeys(_private_ip(value) for value in payload.targets)),
        )

    if not payload.cidr:
        raise HTTPException(400, "CIDR is required for this scope")
    try:
        net = parse_private_network(payload.cidr)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    devices = [
        d
        for d in db.execute(select(Device)).scalars()
        if _in_network(d.ip_address, net)
    ]
    targets = (
        [d.ip_address for d in devices if d.last_seen is not None]
        if payload.scope == "discovered"
        else [d.ip_address for d in devices]
    )
    if not targets:
        raise HTTPException(
            409,
            "no existing assets match this scope; discover the network or add assets first",
        )
    return targets


@router.post("/agentless/monitors/bulk", deprecated=True)
@router.post("/monitoring/assignments/bulk")
def create_monitors(
    payload: BulkMonitorCreate,
    identity: dict = Depends(require_write),
    db: Session = Depends(get_db),
):
    credential = db.get(CredentialProfile, payload.credential_id)
    if credential is None or not credential.enabled:
        raise HTTPException(404, "credential profile not found or disabled")
    _validate_method(credential, payload.method)
    targets = _targets_for_request(payload, db)
    created = 0
    updated = 0

    for ip_value in targets:
        device = db.execute(
            select(Device).where(Device.ip_address == ip_value)
        ).scalar_one_or_none()
        if device is None:
            raise HTTPException(409, f"asset {ip_value} is not in inventory")
        if payload.site and not device.site:
            device.site = payload.site

        monitor = db.execute(
            select(AgentlessMonitor).where(
                AgentlessMonitor.device_id == device.id,
                AgentlessMonitor.method == payload.method,
            )
        ).scalar_one_or_none()
        if monitor is None:
            db.add(
                AgentlessMonitor(
                    device_id=device.id,
                    method=payload.method,
                    credential_id=credential.id,
                    interval_seconds=payload.interval_seconds,
                    enabled=True,
                )
            )
            created += 1
        else:
            monitor.credential_id = credential.id
            monitor.interval_seconds = payload.interval_seconds
            monitor.enabled = True
            monitor.last_error = None
            updated += 1

    _audit(
        db,
        identity["username"],
        "bulk_enable",
        "monitoring_assignment",
        None,
        f"Enabled {payload.method} monitoring for {len(targets)} asset(s)",
        {
            "scope": payload.scope,
            "cidr": payload.cidr,
            "created": created,
            "updated": updated,
            "inventory_only": True,
        },
    )
    db.commit()
    return {"targets": len(targets), "created": created, "updated": updated}


def _monitor_out(row: AgentlessMonitor, db: Session) -> dict:
    device = db.get(Device, row.device_id)
    credential = db.get(CredentialProfile, row.credential_id)
    telemetry = db.get(MonitoringTelemetryLatest, row.id)
    if telemetry is None:
        legacy = db.get(AgentlessTelemetryLatest, row.device_id)
        telemetry = (
            legacy
            if legacy is not None and legacy.source == row.method
            else None
        )
    return {
        "id": row.id,
        "device_id": row.device_id,
        "ip_address": device.ip_address if device else None,
        "hostname": device.hostname if device else None,
        "site": device.site if device else None,
        "method": row.method,
        "credential_id": row.credential_id,
        "credential_name": credential.name if credential else None,
        "interval_seconds": row.interval_seconds,
        "enabled": row.enabled,
        "last_poll_at": row.last_poll_at,
        "last_success_at": row.last_success_at,
        "last_error": row.last_error,
        "consecutive_failures": row.consecutive_failures,
        "telemetry": None
        if telemetry is None
        else {
            "source": getattr(
                telemetry,
                "method",
                getattr(telemetry, "source", row.method),
            ),
            "collected_at": telemetry.collected_at,
            "cpu_usage_percent": telemetry.cpu_usage_percent,
            "memory_usage_percent": telemetry.memory_usage_percent,
            "uptime_seconds": telemetry.uptime_seconds,
            "process_count": telemetry.process_count,
            "disks": telemetry.disks or [],
            "interfaces": telemetry.interfaces or [],
        },
    }


@router.get("/agentless/monitors", deprecated=True)
@router.get("/monitoring/assignments")
def list_monitors(
    identity: dict = Depends(control_identity),
    db: Session = Depends(get_db),
):
    return [
        _monitor_out(row, db)
        for row in db.execute(
            select(AgentlessMonitor).order_by(AgentlessMonitor.created_at.desc())
        ).scalars()
    ]


@router.delete("/agentless/monitors/{monitor_id}", deprecated=True)
@router.delete("/monitoring/assignments/{monitor_id}")
def delete_monitor(
    monitor_id: str,
    identity: dict = Depends(require_write),
    db: Session = Depends(get_db),
):
    row = db.get(AgentlessMonitor, monitor_id)
    if row is None:
        raise HTTPException(404, "monitor not found")
    device_id = row.device_id
    telemetry = db.get(MonitoringTelemetryLatest, monitor_id)
    if telemetry is not None:
        db.delete(telemetry)
    db.delete(row)
    db.flush()
    refresh_device_compat_telemetry(db, device_id)
    _audit(
        db,
        identity["username"],
        "delete",
        "monitoring_assignment",
        monitor_id,
        "Deleted monitoring assignment",
    )
    db.commit()
    return {"deleted": monitor_id}


@router.post("/agentless/test", deprecated=True)
@router.post("/monitoring/test")
def test_monitor(
    payload: MonitorTest,
    identity: dict = Depends(require_write),
    db: Session = Depends(get_db),
):
    target = _private_ip(payload.target)
    _ensure_inventory_targets(db, [target])
    credential = db.get(CredentialProfile, payload.credential_id)
    if credential is None or not credential.enabled:
        raise HTTPException(404, "credential profile not found or disabled")
    _validate_method(credential, payload.method)
    try:
        data = collect_target(
            payload.method,
            target,
            credential.username,
            decrypt_secrets(credential.secret_encrypted),
            credential.options_json or {},
        )
    except Exception as exc:
        raise HTTPException(502, f"connection failed: {exc}") from exc
    return {
        "status": "ok",
        "target": target,
        "method": payload.method,
        "sample": data,
    }


@router.post("/agentless/monitors/{monitor_id}/poll", deprecated=True)
@router.post("/monitoring/assignments/{monitor_id}/poll")
def request_poll(
    monitor_id: str,
    identity: dict = Depends(require_write),
    db: Session = Depends(get_db),
):
    row = db.get(AgentlessMonitor, monitor_id)
    if row is None:
        raise HTTPException(404, "monitor not found")
    row.last_poll_at = None
    row.enabled = True
    db.commit()
    return {"status": "queued", "id": monitor_id}


@router.get("/targets/snmp", include_in_schema=False)
def snmp_exporter_targets(db: Session = Depends(get_db)):
    """Prometheus HTTP-SD targets derived from the monitoring model.

    A direct SNMP assignment is the canonical product object. Operators may opt
    that assignment into snmp_exporter enrichment by setting credential options:

      {"exporter_auth": "public_v2", "exporter_module": "if_mib"}

    Legacy Device.snmp_* targets remain as a compatibility fallback until their
    schema migration is complete. Secrets are never exposed in service discovery.
    """
    output: list[dict] = []
    seen_devices: set[str] = set()

    assignments = list(
        db.execute(
            select(AgentlessMonitor).where(
                AgentlessMonitor.method == "snmp",
                AgentlessMonitor.enabled.is_(True),
            )
        ).scalars()
    )
    for assignment in assignments:
        device = db.get(Device, assignment.device_id)
        credential = db.get(CredentialProfile, assignment.credential_id)
        if device is None or credential is None or not credential.enabled:
            continue
        options = credential.options_json or {}
        exporter_auth = str(options.get("exporter_auth") or "").strip()
        if not exporter_auth:
            continue
        exporter_module = str(options.get("exporter_module") or "if_mib").strip()
        output.append(
            {
                "targets": [device.ip_address],
                "labels": {
                    "host_id": device.id,
                    "hostname": device.hostname or device.ip_address,
                    "site": device.site or "default",
                    "snmp_module": exporter_module,
                    "snmp_auth": exporter_auth,
                    "monitoring_assignment_id": assignment.id,
                    "source": "monitoring_assignment",
                },
            }
        )
        seen_devices.add(device.id)

    # Compatibility for v0.3 assets configured through the old SNMP page.
    for device in db.execute(
        select(Device).where(Device.snmp_enabled.is_(True))
    ).scalars():
        if device.id in seen_devices:
            continue
        output.append(
            {
                "targets": [device.ip_address],
                "labels": {
                    "host_id": device.id,
                    "hostname": device.hostname or device.ip_address,
                    "site": device.site or "default",
                    "snmp_module": device.snmp_module or "if_mib",
                    "snmp_auth": device.snmp_auth or "public_v2",
                    "source": "legacy_device",
                },
            }
        )
    return output


router.include_router(notification_router)
