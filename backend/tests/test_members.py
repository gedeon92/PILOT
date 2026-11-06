from datetime import timedelta

from conftest import create_space, invite_and_join, register
from sqlalchemy import update
from sqlalchemy.orm import Session

from pilot_api.models import Membership, utcnow


def _setup(make_client):
    owner = make_client()
    register(owner, "proprio@exemple.com", "Aïcha Ndiaye")
    space = create_space(owner)
    return owner, space, f"/api/spaces/{space['id']}"


def test_invitation_flow(make_client):
    owner, space, base = _setup(make_client)
    invited = owner.post(
        f"{base}/invitations", json={"email": "Fatou@Exemple.com", "role": "contributor"}
    )
    assert invited.status_code == 201
    token = invited.json()["token"]
    assert invited.json()["member"]["status"] == "invited"

    fatou = make_client()
    register(fatou, "fatou@exemple.com", "Fatou Diallo")
    info = fatou.post("/api/invitations/lookup", json={"token": token}).json()
    assert info == {
        "space_name": "Groupe Horizon",
        "role": "contributor",
        "email": "fatou@exemple.com",
        "invited_by": "Aïcha Ndiaye",
        "expired": False,
        "email_matches": True,
    }

    accepted = fatou.post("/api/invitations/accept", json={"token": token})
    assert accepted.status_code == 200
    assert accepted.json()["role"] == "contributor"
    assert fatou.get(base).status_code == 200

    # Le lien ne sert qu'une fois.
    again = fatou.post("/api/invitations/accept", json={"token": token})
    assert again.status_code == 404


def test_invitation_link_requires_the_invited_account(make_client):
    owner, _, base = _setup(make_client)
    token = owner.post(
        f"{base}/invitations", json={"email": "fatou@exemple.com", "role": "reader"}
    ).json()["token"]

    intruder = make_client()
    register(intruder, "intrus@exemple.com")
    response = intruder.post("/api/invitations/accept", json={"token": token})

    assert response.status_code == 403
    assert intruder.get(base).status_code == 404


def test_expired_invitation_is_refused(make_client, engine):
    owner, _, base = _setup(make_client)
    token = owner.post(
        f"{base}/invitations", json={"email": "fatou@exemple.com", "role": "reader"}
    ).json()["token"]
    with Session(engine) as db:
        db.execute(update(Membership).values(invite_expires_at=utcnow() - timedelta(minutes=1)))
        db.commit()

    fatou = make_client()
    register(fatou, "fatou@exemple.com")
    assert fatou.post("/api/invitations/accept", json={"token": token}).status_code == 410


def test_renewed_link_replaces_the_old_one(make_client):
    owner, _, base = _setup(make_client)
    first = owner.post(f"{base}/invitations", json={"email": "f@exemple.com", "role": "reader"})
    member_id = first.json()["member"]["id"]

    renewed = owner.post(f"{base}/members/{member_id}/invitation-link")
    assert renewed.status_code == 200

    fatou = make_client()
    register(fatou, "f@exemple.com")
    old = fatou.post("/api/invitations/accept", json={"token": first.json()["token"]})
    new = fatou.post("/api/invitations/accept", json={"token": renewed.json()["token"]})
    assert old.status_code == 404
    assert new.status_code == 200


def test_duplicate_invitation_is_refused(make_client):
    owner, _, base = _setup(make_client)
    payload = {"email": "f@exemple.com", "role": "reader"}
    assert owner.post(f"{base}/invitations", json=payload).status_code == 201
    assert owner.post(f"{base}/invitations", json=payload).status_code == 409
    own = owner.post(f"{base}/invitations", json={"email": "proprio@exemple.com", "role": "reader"})
    assert own.status_code == 409


def test_revoking_contribution_applies_on_next_request(make_client):
    """ACC03 : la propriétaire retire le droit de contribution ; la requête suivante le reflète."""
    owner, space, base = _setup(make_client)
    contributor = make_client()
    member = invite_and_join(owner, contributor, space["id"], "c@exemple.com", "contributor")
    assert contributor.get(base).json()["role"] == "contributor"

    changed = owner.patch(f"{base}/members/{member['id']}", json={"version": 2, "role": "reader"})
    assert changed.status_code == 200

    assert contributor.get(base).json()["role"] == "reader"


def test_role_change_detects_conflicts(make_client):
    owner, space, base = _setup(make_client)
    member = invite_and_join(owner, make_client(), space["id"], "c@exemple.com", "contributor")

    stale = owner.patch(f"{base}/members/{member['id']}", json={"version": 1, "role": "reader"})
    assert stale.status_code == 409


def test_removed_member_loses_access(make_client):
    owner, space, base = _setup(make_client)
    reader = make_client()
    member = invite_and_join(owner, reader, space["id"], "r@exemple.com", "reader")

    assert owner.delete(f"{base}/members/{member['id']}").status_code == 204

    assert reader.get(base).status_code == 404
    assert reader.get("/api/auth/me").json()["spaces"] == []


def test_members_list_shows_owner_first(make_client):
    owner, space, base = _setup(make_client)
    invite_and_join(owner, make_client(), space["id"], "b@exemple.com", "reader")
    owner.post(f"{base}/invitations", json={"email": "a@exemple.com", "role": "contributor"})

    members = owner.get(f"{base}/members").json()

    assert [(m["email"], m["status"]) for m in members] == [
        ("proprio@exemple.com", "active"),
        ("b@exemple.com", "active"),
        ("a@exemple.com", "invited"),
    ]
    assert members[0]["is_me"] is True


def test_invitation_is_emailed_with_the_link(make_client, monkeypatch):
    from pilot_api.routers import spaces as spaces_router

    sent: list[dict] = []
    monkeypatch.setattr(spaces_router, "mail_configured", lambda: True)
    monkeypatch.setattr(spaces_router, "send_email", lambda **message: sent.append(message))
    owner = make_client()
    register(owner, "proprio@exemple.com", "Aïcha Ndiaye")
    space = create_space(owner, "Groupe Horizon")
    base = f"/api/spaces/{space['id']}"

    real = owner.post(f"{base}/invitations", json={"email": "moussa@horizon.sn", "role": "reader"})
    trial = owner.post(f"{base}/invitations", json={"email": "essai@exemple.com", "role": "reader"})

    assert real.json()["emailed"] is True and real.json()["email_note"] is None
    assert len(sent) == 1 and sent[0]["to_email"] == "moussa@horizon.sn"
    assert f"/invitation/{real.json()['token']}" in sent[0]["text"]
    assert "Aïcha Ndiaye" in sent[0]["subject"] and "Groupe Horizon" in sent[0]["subject"]
    assert trial.json()["emailed"] is False  # adresse d'essai : jamais d'envoi

    renewed = owner.post(f"{base}/members/{real.json()['member']['id']}/invitation-link").json()
    assert renewed["emailed"] is True and f"/invitation/{renewed['token']}" in sent[1]["text"]


def test_invitation_still_works_when_email_is_off(make_client, monkeypatch):
    from pilot_api.routers import spaces as spaces_router

    monkeypatch.setattr(spaces_router, "mail_configured", lambda: False)
    owner = make_client()
    register(owner, "proprio@exemple.com")
    space = create_space(owner)

    invited = owner.post(
        f"/api/spaces/{space['id']}/invitations",
        json={"email": "moussa@horizon.sn", "role": "reader"},
    )

    assert invited.status_code == 201
    assert invited.json()["emailed"] is False
    assert "transmettez le lien" in invited.json()["email_note"]
