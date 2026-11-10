"""Mode simple / mode complet (décision du 10 nov. 2026) : réglage de l'espace, propriétaire."""

from conftest import create_space, invite_and_join, register


def test_spaces_start_in_simple_mode_and_only_owners_switch(make_client):
    owner = make_client()
    register(owner, "proprio@exemple.com")
    space = create_space(owner)
    base = f"/api/spaces/{space['id']}"
    assert space["advanced_mode"] is False
    contributor = make_client()
    invite_and_join(owner, contributor, space["id"], "contrib@exemple.com", "contributor")
    assert (
        contributor.patch(
            base, json={"version": space["version"], "advanced_mode": True}
        ).status_code
        == 403
    )
    switched = owner.patch(base, json={"version": space["version"], "advanced_mode": True}).json()
    assert switched["advanced_mode"] is True
    assert contributor.get(base).json()["advanced_mode"] is True
    back = owner.patch(base, json={"version": switched["version"], "advanced_mode": False}).json()
    assert back["advanced_mode"] is False
