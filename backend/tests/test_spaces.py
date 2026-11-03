from conftest import create_space, invite_and_join, register
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from pilot_api.models import AuditLog


def test_creator_becomes_owner(make_client):
    client = make_client()
    register(client, "proprio@exemple.com")

    space = create_space(client)

    assert space["role"] == "owner"
    assert space["timezone"] == "Africa/Dakar"
    me = client.get("/api/auth/me").json()
    assert [s["name"] for s in me["spaces"]] == ["Groupe Horizon"]


def test_unknown_timezone_is_rejected(make_client):
    client = make_client()
    register(client, "a@exemple.com")
    response = client.post("/api/spaces", json={"name": "X", "timezone": "Mars/Olympus"})
    assert response.status_code == 422


def test_spaces_are_isolated(make_client):
    """Un utilisateur de l'espace A ne peut rien lire de l'espace B, même en forgeant la requête."""
    alice, bob = make_client(), make_client()
    register(alice, "alice@exemple.com")
    register(bob, "bob@exemple.com")
    space_b = create_space(bob, "Espace de Bob")

    for path in ("", "/members"):
        response = alice.get(f"/api/spaces/{space_b['id']}{path}")
        assert response.status_code == 404
    renamed = alice.patch(f"/api/spaces/{space_b['id']}", json={"version": 1, "name": "Piraté"})
    assert renamed.status_code == 404
    assert alice.get("/api/auth/me").json()["spaces"] == []


def test_owner_renames_space_with_version_check(make_client):
    client = make_client()
    register(client, "a@exemple.com")
    space = create_space(client)
    url = f"/api/spaces/{space['id']}"

    renamed = client.patch(url, json={"version": 1, "name": "Groupe Horizon SA"})
    assert renamed.status_code == 200
    assert renamed.json()["version"] == 2

    stale = client.patch(url, json={"version": 1, "name": "Ancienne version"})
    assert stale.status_code == 409
    assert client.get(url).json()["name"] == "Groupe Horizon SA"


def test_reader_cannot_write_through_the_api(make_client):
    """ACC01 : un lecteur tente une écriture directe ; refus serveur, aucune donnée modifiée."""
    owner, reader = make_client(), make_client()
    register(owner, "proprio@exemple.com")
    space = create_space(owner)
    invite_and_join(owner, reader, space["id"], "lecteur@exemple.com", "reader")

    response = reader.patch(f"/api/spaces/{space['id']}", json={"version": 1, "name": "Modifié"})

    assert response.status_code == 403
    assert owner.get(f"/api/spaces/{space['id']}").json()["name"] == "Groupe Horizon"


def test_contributor_cannot_manage_access(make_client):
    """ACC02 : un contributeur ne gère ni la structure ni les accès, même par requête forgée."""
    owner, contributor = make_client(), make_client()
    register(owner, "proprio@exemple.com")
    space = create_space(owner)
    me = invite_and_join(owner, contributor, space["id"], "contrib@exemple.com", "contributor")
    base = f"/api/spaces/{space['id']}"
    owner_member = next(m for m in owner.get(f"{base}/members").json() if m["role"] == "owner")

    assert (
        contributor.post(
            f"{base}/invitations", json={"email": "x@exemple.com", "role": "reader"}
        ).status_code
        == 403
    )
    assert (
        contributor.patch(
            f"{base}/members/{me['id']}", json={"version": 2, "role": "contributor"}
        ).status_code
        == 403
    )
    assert contributor.delete(f"{base}/members/{owner_member['id']}").status_code == 403
    assert contributor.patch(base, json={"version": 1, "name": "X"}).status_code == 403


def test_nobody_can_grant_the_owner_role(make_client):
    owner, member = make_client(), make_client()
    register(owner, "proprio@exemple.com")
    space = create_space(owner)
    joined = invite_and_join(owner, member, space["id"], "m@exemple.com", "reader")
    base = f"/api/spaces/{space['id']}"

    invite = owner.post(f"{base}/invitations", json={"email": "y@exemple.com", "role": "owner"})
    promote = owner.patch(f"{base}/members/{joined['id']}", json={"version": 2, "role": "owner"})

    assert invite.status_code == 422
    assert promote.status_code == 422


def test_owner_role_cannot_be_removed(make_client):
    owner = make_client()
    register(owner, "proprio@exemple.com")
    space = create_space(owner)
    base = f"/api/spaces/{space['id']}"
    owner_member = owner.get(f"{base}/members").json()[0]

    assert owner.delete(f"{base}/members/{owner_member['id']}").status_code == 400
    assert (
        owner.patch(
            f"{base}/members/{owner_member['id']}", json={"version": 1, "role": "reader"}
        ).status_code
        == 400
    )


def test_space_creation_is_journaled(make_client, engine):
    client = make_client()
    register(client, "a@exemple.com")
    space = create_space(client)

    with Session(engine) as db:
        actions = db.scalars(select(AuditLog.action).where(AuditLog.space_id == space["id"])).all()
    assert actions == ["space.created"]


def test_database_schema_is_isolated_for_tests(engine):
    with engine.connect() as conn:
        schema = conn.execute(text("select current_schema()")).scalar()
    assert schema.startswith("test_")
