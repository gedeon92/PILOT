import pytest
from conftest import create_space, invite_and_join, register

RESOURCES = ["portfolios", "entities", "project-types"]


def _owner_space(make_client):
    owner = make_client()
    register(owner, "proprio@exemple.com")
    space = create_space(owner)
    return owner, space, f"/api/spaces/{space['id']}"


def test_new_space_gets_default_project_types(make_client):
    owner, _, base = _owner_space(make_client)

    names = [t["name"] for t in owner.get(f"{base}/project-types").json()]

    assert names == ["Autre", "Événement", "Mission", "Produit"]


def test_owner_creates_portfolio_and_entity(make_client):
    owner, _, base = _owner_space(make_client)

    portfolio = owner.post(
        f"{base}/portfolios",
        json={"name": "Événements", "description": "Salons et séminaires", "color": "blue"},
    )
    entity = owner.post(f"{base}/entities", json={"name": "Horizon Events", "country": "Sénégal"})

    assert portfolio.status_code == 201
    assert portfolio.json()["color"] == "blue"
    assert portfolio.json()["archived"] is False
    assert entity.status_code == 201
    assert entity.json()["country"] == "Sénégal"
    assert [p["name"] for p in owner.get(f"{base}/portfolios").json()] == ["Événements"]


@pytest.mark.parametrize("resource", RESOURCES)
def test_rename_keeps_the_same_identifier(make_client, resource):
    owner, _, base = _owner_space(make_client)
    created = owner.post(f"{base}/{resource}", json={"name": "Ancien nom"}).json()

    renamed = owner.patch(
        f"{base}/{resource}/{created['id']}", json={"version": 1, "name": "Nouveau nom"}
    )

    assert renamed.status_code == 200
    assert renamed.json()["id"] == created["id"]
    assert renamed.json()["version"] == 2


@pytest.mark.parametrize("resource", RESOURCES)
def test_names_are_unique_ignoring_case(make_client, resource):
    owner, _, base = _owner_space(make_client)
    owner.post(f"{base}/{resource}", json={"name": "Projets groupe"})

    duplicate = owner.post(f"{base}/{resource}", json={"name": "projets GROUPE"})

    assert duplicate.status_code == 409


def test_archive_hides_and_restore_brings_back(make_client):
    owner, _, base = _owner_space(make_client)
    item = owner.post(f"{base}/portfolios", json={"name": "Missions"}).json()

    archived = owner.patch(f"{base}/portfolios/{item['id']}", json={"version": 1, "archived": True})
    assert archived.json()["archived"] is True
    assert owner.get(f"{base}/portfolios").json() == []
    all_items = owner.get(f"{base}/portfolios", params={"include_archived": True}).json()
    assert [(i["name"], i["archived"]) for i in all_items] == [("Missions", True)]

    restored = owner.patch(
        f"{base}/portfolios/{item['id']}", json={"version": 2, "archived": False}
    )
    assert restored.json()["archived"] is False
    assert len(owner.get(f"{base}/portfolios").json()) == 1


def test_archived_name_stays_reserved(make_client):
    owner, _, base = _owner_space(make_client)
    item = owner.post(f"{base}/entities", json={"name": "Horizon Retail"}).json()
    owner.patch(f"{base}/entities/{item['id']}", json={"version": 1, "archived": True})

    assert owner.post(f"{base}/entities", json={"name": "Horizon Retail"}).status_code == 409


def test_update_detects_conflicts(make_client):
    owner, _, base = _owner_space(make_client)
    item = owner.post(f"{base}/portfolios", json={"name": "A"}).json()
    owner.patch(f"{base}/portfolios/{item['id']}", json={"version": 1, "name": "B"})

    stale = owner.patch(f"{base}/portfolios/{item['id']}", json={"version": 1, "name": "C"})

    assert stale.status_code == 409


def test_clearing_optional_fields(make_client):
    owner, _, base = _owner_space(make_client)
    item = owner.post(
        f"{base}/portfolios", json={"name": "A", "description": "Texte", "color": "green"}
    ).json()

    cleared = owner.patch(
        f"{base}/portfolios/{item['id']}", json={"version": 1, "description": "", "color": None}
    ).json()

    assert cleared["description"] is None
    assert cleared["color"] == "green"


def test_unknown_color_is_rejected(make_client):
    owner, _, base = _owner_space(make_client)
    response = owner.post(f"{base}/portfolios", json={"name": "A", "color": "fuchsia"})
    assert response.status_code == 422


@pytest.mark.parametrize("role", ["reader", "contributor"])
def test_only_owner_changes_the_structure(make_client, role):
    owner, space, base = _owner_space(make_client)
    member = make_client()
    invite_and_join(owner, member, space["id"], "membre@exemple.com", role)
    item = owner.post(f"{base}/portfolios", json={"name": "Événements"}).json()

    assert member.get(f"{base}/portfolios").status_code == 200
    assert member.post(f"{base}/portfolios", json={"name": "X"}).status_code == 403
    patched = member.patch(f"{base}/portfolios/{item['id']}", json={"version": 1, "name": "X"})
    assert patched.status_code == 403
    assert owner.get(f"{base}/portfolios").json()[0]["name"] == "Événements"


def test_structure_is_isolated_between_spaces(make_client):
    owner, _, base = _owner_space(make_client)
    item = owner.post(f"{base}/portfolios", json={"name": "Secret"}).json()

    other = make_client()
    register(other, "autre@exemple.com")
    other_space = create_space(other, "Autre espace")

    assert other.get(f"{base}/portfolios").status_code == 404
    # Même avec l'identifiant, impossible de modifier l'élément depuis son propre espace.
    forged = other.patch(
        f"/api/spaces/{other_space['id']}/portfolios/{item['id']}",
        json={"version": 1, "name": "Piraté"},
    )
    assert forged.status_code == 404
    assert owner.get(f"{base}/portfolios").json()[0]["name"] == "Secret"
