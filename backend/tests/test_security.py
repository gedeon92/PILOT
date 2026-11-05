"""Revue de sécurité automatisée : chaque route d'un espace vérifie l'appartenance,
chaque écriture exige l'en-tête anti-CSRF."""

from fastapi.routing import APIRoute

from pilot_api.deps import get_membership, require_csrf_header
from pilot_api.main import app


def _dependencies(dependant) -> set:
    found = {dependant.call}
    for sub in dependant.dependencies:
        found |= _dependencies(sub)
    return found


def test_every_space_route_checks_membership():
    unchecked = [
        f"{sorted(route.methods)} {route.path}"
        for route in app.routes
        if isinstance(route, APIRoute)
        and "{space_id}" in route.path
        and get_membership not in _dependencies(route.dependant)
    ]
    assert unchecked == []


def test_csrf_header_is_required_application_wide():
    assert any(d.dependency is require_csrf_header for d in app.router.dependencies) or any(
        getattr(d, "dependency", None) is require_csrf_header
        for d in getattr(app, "dependencies", [])
    )
