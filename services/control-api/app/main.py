"""SentinelView Control API entrypoint.

The v0.4 consolidation keeps the existing control-plane implementation in
``legacy_main`` temporarily while product endpoints move into focused routers.
This entrypoint preserves backward compatibility while making route ownership
explicit and preventing stale inline handlers from competing with maintained
modular implementations.

New development should add focused routers/modules instead of growing the
legacy monolith further.
"""

from fastapi.routing import APIRoute

from . import legacy_main as _legacy
from .legacy_main import *  # noqa: F401,F403 - compatibility re-export
from .notification_api import router as notification_router

# Explicit re-exports used by tests and uvicorn.
app = _legacy.app
ensure_bootstrap_data = _legacy.ensure_bootstrap_data


def _deduplicate_api_routes() -> int:
    """Keep one registration for every HTTP method/path pair.

    This generic pass removes accidental duplicate registrations. Operations
    routes that have both legacy and modular implementations are re-installed
    explicitly by ``_install_modular_operations_routes`` below, so this pass
    does not need to infer ownership from route ordering.
    """
    unique_routes = []
    seen: set[tuple[str, tuple[str, ...]]] = set()
    removed = 0

    for route in app.router.routes:
        if isinstance(route, APIRoute):
            key = (route.path, tuple(sorted(route.methods or ())))
            if key in seen:
                removed += 1
                continue
            seen.add(key)
        unique_routes.append(route)

    if removed:
        app.router.routes[:] = unique_routes
        _legacy.logger.info("removed %s duplicate API route registration(s)", removed)
    return removed


_MODULAR_OPERATIONS_PATHS = {
    "/api/v1/notification-channels",
    "/api/v1/notification-channels/{channel_id}",
    "/api/v1/notification-channels/{channel_id}/test",
    "/api/v1/notification-deliveries",
    "/api/v1/maintenance",
    "/api/v1/maintenance/{window_id}",
    "/api/v1/availability",
}


def _install_modular_operations_routes() -> None:
    """Make modular notification/maintenance implementations authoritative.

    ``legacy_main`` still contains historical inline handlers during the v0.4
    migration. Remove every registration for the migrated operations paths and
    include the maintained notification router once. That router already
    includes the maintenance/availability router.
    """
    app.router.routes[:] = [
        route
        for route in app.router.routes
        if not (isinstance(route, APIRoute) and route.path in _MODULAR_OPERATIONS_PATHS)
    ]
    app.include_router(notification_router, prefix="/api/v1")


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
_install_modular_operations_routes()
_install_asset_aliases()
_deduplicate_api_routes()
