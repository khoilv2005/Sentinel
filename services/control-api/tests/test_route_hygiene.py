from fastapi.routing import APIRoute

from app.main import app


def test_api_method_path_pairs_are_unique():
    seen = set()
    duplicates = []
    for route in app.router.routes:
        if not isinstance(route, APIRoute):
            continue
        key = (route.path, tuple(sorted(route.methods or ())))
        if key in seen:
            duplicates.append(key)
        seen.add(key)

    assert duplicates == []


def test_modular_notification_and_maintenance_routes_are_effective():
    endpoints = {
        (route.path, tuple(sorted(route.methods or ()))): f"{route.endpoint.__module__}.{route.endpoint.__name__}"
        for route in app.router.routes
        if isinstance(route, APIRoute)
    }

    notification = endpoints[("/api/v1/notification-channels", ("POST",))]
    maintenance = endpoints[("/api/v1/maintenance", ("POST",))]
    availability = endpoints[("/api/v1/availability", ("GET",))]

    assert notification.startswith("app.notification_api.")
    assert maintenance.startswith("app.maintenance_api.")
    assert availability.startswith("app.maintenance_api.")
