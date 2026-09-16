from fastapi.routing import APIRoute

from app.main import app


def _endpoint_name(route: APIRoute) -> str:
    return f"{route.endpoint.__module__}.{route.endpoint.__name__}"


def test_api_method_path_pairs_are_unique():
    seen = set()
    duplicates = []
    for route in app.router.routes:
        if not isinstance(route, APIRoute):
            continue
        key = (route.path, tuple(sorted(route.methods or ())))
        if key in seen:
            duplicates.append((key, _endpoint_name(route)))
        seen.add(key)

    assert duplicates == []


def test_modular_notification_and_maintenance_routes_are_effective():
    routes = [route for route in app.router.routes if isinstance(route, APIRoute)]
    endpoints = {
        (route.path, tuple(sorted(route.methods or ()))): _endpoint_name(route)
        for route in routes
    }
    operations = [
        (route.path, tuple(sorted(route.methods or ())), _endpoint_name(route))
        for route in routes
        if any(token in route.path for token in ("notification", "maintenance", "availability"))
    ]

    notification_key = ("/api/v1/notification-channels", ("POST",))
    maintenance_key = ("/api/v1/maintenance", ("POST",))
    availability_key = ("/api/v1/availability", ("GET",))

    assert notification_key in endpoints, operations
    assert maintenance_key in endpoints, operations
    assert availability_key in endpoints, operations

    assert endpoints[notification_key].startswith("app.notification_api."), operations
    assert endpoints[maintenance_key].startswith("app.maintenance_api."), operations
    assert endpoints[availability_key].startswith("app.maintenance_api."), operations
