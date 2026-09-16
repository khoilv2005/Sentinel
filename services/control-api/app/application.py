"""Consolidated SentinelView v0.4 ASGI application.

`main.py` is still the historical monolith and contains a few legacy route
implementations that were superseded by modular routers (notifications,
maintenance/SLA and monitoring). During the staged v0.4 migration, modular
routers are registered first. This entrypoint removes later exact duplicates so
the running API and OpenAPI document expose one implementation per
path+method.

It also reconciles Asset health after managed-agent check-in/telemetry. The
legacy managed-agent handlers still optimistically write `Device.state = up`;
v0.4 immediately derives the final state from all configured monitoring methods
so a healthy agent plus a failed remote collector becomes DEGRADED instead of
oscillating between UP and DOWN.
"""

from fastapi import Request
from fastapi.routing import APIRoute
from sqlalchemy import select

from .db import SessionLocal
from .main import app
from .models import ManagedAgent
from .monitoring import reconcile_device_health
from .security import hash_token


def _method_key(route: APIRoute) -> tuple[str, tuple[str, ...]]:
    return route.path, tuple(sorted(route.methods or set()))


def consolidate_routes() -> None:
    seen: set[tuple[str, tuple[str, ...]]] = set()
    consolidated = []
    for route in app.router.routes:
        if not isinstance(route, APIRoute):
            consolidated.append(route)
            continue
        key = _method_key(route)
        if key in seen:
            # Modular routes are intentionally registered before historical
            # monolithic fallbacks. Keep the first implementation.
            continue
        seen.add(key)
        consolidated.append(route)
    app.router.routes[:] = consolidated
    app.openapi_schema = None


consolidate_routes()


def _agent_from_request(request: Request, db):
    authorization = request.headers.get("authorization") or ""
    if not authorization.lower().startswith("bearer "):
        return None
    raw = authorization.split(" ", 1)[1].strip()
    if not raw:
        return None
    return db.execute(
        select(ManagedAgent).where(
            ManagedAgent.credential_hash == hash_token(raw),
            ManagedAgent.revoked.is_(False),
        )
    ).scalar_one_or_none()


@app.middleware("http")
async def reconcile_managed_agent_health(request: Request, call_next):
    response = await call_next(request)
    if response.status_code >= 400:
        return response

    path = request.url.path
    needs_reconcile = (
        request.method == "POST"
        and path in {"/api/v1/agents/checkin", "/api/v1/agents/telemetry"}
    )
    revoke_prefix = request.method == "POST" and path.startswith("/api/v1/agents/") and path.endswith("/revoke")
    if not needs_reconcile and not revoke_prefix:
        return response

    db = SessionLocal()
    try:
        if needs_reconcile:
            agent = _agent_from_request(request, db)
        else:
            parts = path.strip("/").split("/")
            agent_id = parts[-2] if len(parts) >= 2 else ""
            agent = db.get(ManagedAgent, agent_id) if agent_id else None
        if agent is not None:
            device = db.get(__import__("app.models", fromlist=["Device"]).Device, agent.device_id)
            if device is not None:
                reconcile_device_health(db, device)
                db.commit()
    finally:
        db.close()
    return response
