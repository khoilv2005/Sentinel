"""SentinelView Control API entrypoint.

The v0.4 consolidation keeps the existing control-plane implementation in
``legacy_main`` temporarily while duplicate product endpoints are moved into
modular routers. Importing the legacy module preserves compatibility; this
entrypoint then removes duplicate method/path registrations so each API action
has one effective route.

New development should add focused routers/modules instead of growing the
legacy monolith further.
"""

from fastapi.routing import APIRoute

from . import legacy_main as _legacy
from .legacy_main import *  # noqa: F401,F403 - compatibility re-export

# Explicit re-exports used by tests and uvicorn.
app = _legacy.app
ensure_bootstrap_data = _legacy.ensure_bootstrap_data


def _route_priority(route: APIRoute) -> int:
    """Prefer focused v0.4 routers over equivalent legacy inline handlers."""
    module = getattr(route.endpoint, "__module__", "")
    if module.startswith((
        "app.notification_api",
        "app.maintenance_api",
        "app.agentless_api",
    )):
        return 100
    if module.startswith("app.legacy_main"):
        return 0
    return 50


def _deduplicate_api_routes() -> int:
    """Keep one effective registration for every HTTP method/path pair.

    The legacy control plane still contains inline notification and maintenance
    handlers while the v0.4 modular routers expose the maintained versions.
    Route order is not a reliable ownership signal, so duplicates are resolved
    explicitly by endpoint-module priority while preserving the first position
    of each method/path pair in the router list.
    """
    original = list(app.router.routes)
    best: dict[tuple[str, tuple[str, ...]], APIRoute] = {}
    removed = 0

    for route in original:
        if not isinstance(route, APIRoute):
            continue
        key = (route.path, tuple(sorted(route.methods or ())))
        current = best.get(key)
        if current is None:
            best[key] = route
            continue
        removed += 1
        if _route_priority(route) > _route_priority(current):
            best[key] = route

    if not removed:
        return 0

    unique_routes = []
    emitted: set[tuple[str, tuple[str, ...]]] = set()
    for route in original:
        if not isinstance(route, APIRoute):
            unique_routes.append(route)
            continue
        key = (route.path, tuple(sorted(route.methods or ())))
        if key in emitted:
            continue
        emitted.add(key)
        unique_routes.append(best[key])

    app.router.routes[:] = unique_routes
    _legacy.logger.info("removed %s duplicate API route registration(s)", removed)
    return removed


def _install_asset_aliases() -> None:
    """Expose Assets as the canonical monitored-infrastructure API.

    Existing /hosts routes remain callable for older clients but are hidden
    from OpenAPI. The aliases reuse the already tested endpoint functions and
    therefore keep the same authentication, filtering and response behavior.
    """
    for route in app.router.routes:
        if isinstance(route, APIRoute) and route.path.startswith("/api/v1/hosts"):
            route.include_in_schema = False

    app.add_api_route(
        "/api/v1/assets",
        _legacy.list_hosts,
        methods=["GET"],
        response_model=list[_legacy.HostSummaryOut],
        tags=["assets"],
        name="list_assets",
    )
    app.add_api_route(
        "/api/v1/assets/{device_id}/overview",
        _legacy.host_overview,
        methods=["GET"],
        response_model=_legacy.HostOverviewOut,
        tags=["assets"],
        name="asset_overview",
    )
    app.add_api_route(
        "/api/v1/assets/{device_id}/metrics",
        _legacy.host_metric_history,
        methods=["GET"],
        tags=["assets"],
        name="asset_metric_history",
    )


_deduplicate_api_routes()
_install_asset_aliases()
