"""Consolidated SentinelView v0.4 ASGI application.

`main.py` is still the historical monolith and contains a few legacy route
implementations that were superseded by modular routers (notifications,
maintenance/SLA and monitoring). During the staged v0.4 migration, this
entrypoint exposes one implementation per exact path+method and explicitly
prefers modular handlers over legacy `app.main` handlers.

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
from .models import Device, ManagedAgent
from .monitoring import reconcile_device_health
from .security import hash_token


def _method_key(route: APIRoute) -> tuple[str, tuple[str, ...]]:
    return route.path, tuple(sorted(route.methods or set()))


def _route_rank(route: APIRoute) -> int:
    """Prefer modular v0.4 handlers over historical monolithic handlers."""
    module = getattr(route.endpoint, "__module__", "")
    if module == "app.main" or module.endswith(".main"):
        return 0
    return 10


def consolidate_routes() -> None:
    """Expose one runtime route per path+method.

    FastAPI copies nested router entries when routers are included. During the
    migration, exact legacy duplicates can therefore appear before or after the
    modular implementation depending on import/include order. Selection must be
    semantic rather than order-dependent.
    """
    selected: dict[tuple[str, tuple[str, ...]], tuple[int, int, APIRoute]] = {}
    passthrough: list[tuple[int, object]] = []

    for index, route in enumerate(app.router.routes):
        if not isinstance(route, APIRoute):
            passthrough.append((index, route))
            continue
        key = _method_key(route)
        rank = _route_rank(route)
        current = selected.get(key)
        if current is None or rank > current[0]:
            selected[key] = (rank, index, route)

    ordered = passthrough + [
        (index, route) for _rank, index, route in selected.values()
    ]
    ordered.sort(key=lambda item: item[0])
    app.router.routes[:] = [route for _index, route in ordered]
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
    revoke_request = (
        request.method == "POST"
        and path.startswith("/api/v1/agents/")
        and path.endswith("/revoke")
    )
    if not needs_reconcile and not revoke_request:
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
            device = db.get(Device, agent.device_id)
            if device is not None:
                reconcile_device_health(db, device)
                db.commit()
    finally:
        db.close()
    return response
