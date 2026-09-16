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


def _deduplicate_api_routes() -> int:
    """Keep the first registration for each method/path pair.

    Modular v0.4 routers are included before the old inline notification and
    maintenance definitions in ``legacy_main``, so preserving the first route
    selects the modular implementation (encrypted notification config and
    maintenance-aware availability) while removing the stale duplicate route.
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
