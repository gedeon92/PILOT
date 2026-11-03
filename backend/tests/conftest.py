import os
import uuid
from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from pilot_api import models  # noqa: F401  (enregistre les tables)
from pilot_api.config import get_settings
from pilot_api.db import Base, get_db, to_sqlalchemy_url
from pilot_api.deps import CSRF_HEADER
from pilot_api.main import app

PASSWORD = "mot-de-passe-solide"


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    """Chaque exécution des tests travaille dans un schéma PostgreSQL temporaire,
    supprimé à la fin : les données de la base de développement ne sont jamais touchées."""
    url = os.environ.get("TEST_DATABASE_URL") or get_settings().database_url
    if not url:
        pytest.skip("Aucune base pour les tests (TEST_DATABASE_URL ou DATABASE_URL).")
    # Le pooler de Neon ne conserve pas les réglages de session (search_path) : connexion directe.
    url = to_sqlalchemy_url(url).replace("-pooler.", ".")
    schema = f"test_{uuid.uuid4().hex[:12]}"

    # pool_pre_ping : la connexion reste inactive pendant les tests et Neon peut la fermer.
    admin = create_engine(url, pool_pre_ping=True)
    with admin.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))

    test_engine = create_engine(url, pool_pre_ping=True)

    @event.listens_for(test_engine, "connect")
    def _use_schema(dbapi_conn, _record):  # noqa: ANN001
        dbapi_conn.autocommit = True
        with dbapi_conn.cursor() as cursor:
            cursor.execute(f'SET search_path TO "{schema}"')
        dbapi_conn.autocommit = False

    Base.metadata.create_all(test_engine)
    yield test_engine

    test_engine.dispose()
    with admin.begin() as conn:
        conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    admin.dispose()


@pytest.fixture
def make_client(engine: Engine) -> Iterator[Callable[[], TestClient]]:
    """Fabrique de clients : un client = un navigateur, avec ses propres cookies."""
    factory = sessionmaker(engine, expire_on_commit=False)

    def _get_db() -> Iterator[Session]:
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = _get_db
    clients: list[TestClient] = []

    def _make() -> TestClient:
        client = TestClient(app, headers={CSRF_HEADER: "1"})
        clients.append(client)
        return client

    yield _make

    for client in clients:
        client.close()
    app.dependency_overrides.pop(get_db, None)
    tables = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} CASCADE"))


def register(client: TestClient, email: str, name: str = "Utilisateur Test") -> dict:
    response = client.post(
        "/api/auth/register", json={"email": email, "password": PASSWORD, "display_name": name}
    )
    assert response.status_code == 201, response.text
    return response.json()


def create_space(client: TestClient, name: str = "Groupe Horizon") -> dict:
    response = client.post("/api/spaces", json={"name": name, "timezone": "Africa/Dakar"})
    assert response.status_code == 201, response.text
    return response.json()


def invite_and_join(
    owner: TestClient, member: TestClient, space_id: str, email: str, role: str
) -> dict:
    invited = owner.post(f"/api/spaces/{space_id}/invitations", json={"email": email, "role": role})
    assert invited.status_code == 201, invited.text
    register(member, email)
    accepted = member.post("/api/invitations/accept", json={"token": invited.json()["token"]})
    assert accepted.status_code == 200, accepted.text
    return invited.json()["member"]
