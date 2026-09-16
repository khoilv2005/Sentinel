from collections import Counter

from fastapi.routing import APIRoute

from app.application import app


def test_consolidated_application_has_no_duplicate_path_method_routes():
    keys = []
    for route in app.router.routes:
        if isinstance(route, APIRoute):
            keys.append((route.path, tuple(sorted(route.methods or set()))))
    duplicates = [key for key, count in Counter(keys).items() if count > 1]
    assert duplicates == []


def test_modular_notification_and_maintenance_routes_are_active():
    routes = {
        (route.path, tuple(sorted(route.methods or set()))): route
        for route in app.router.routes
        if isinstance(route, APIRoute)
    }

    notification = routes[("/api/v1/notification-channels", ("POST",))]
    maintenance = routes[("/api/v1/maintenance", ("POST",))]
    availability = routes[("/api/v1/availability", ("GET",))]
    snmp_targets = routes[("/api/v1/targets/snmp", ("GET",))]

    assert notification.endpoint.__module__.endswith("notification_api")
    assert maintenance.endpoint.__module__.endswith("maintenance_api")
    assert availability.endpoint.__module__.endswith("maintenance_api")
    assert snmp_targets.endpoint.__module__.endswith("agentless_api")
