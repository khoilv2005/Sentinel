"""Consolidated SentinelView v0.4 ASGI application.

`main.py` is still the historical monolith and contains a few legacy route
implementations that were superseded by modular routers (notifications,
maintenance/SLA and monitoring). During the staged v0.4 migration, modular
routers are registered first. This entrypoint removes later exact duplicates so
the running API and OpenAPI document expose one implementation per
path+method.

The source-level legacy handlers can then be removed safely in the final
migration phase without changing runtime behavior.
"""

from fastapi.routing import APIRoute

from .main import app


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
    # Route topology changed before serving requests; force OpenAPI to rebuild
    # if something imported main.app and generated a schema earlier.
    app.openapi_schema = None


consolidate_routes()
