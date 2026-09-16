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


_deduplicate_api_routes()
