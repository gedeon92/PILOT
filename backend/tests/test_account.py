import re

import pytest
from conftest import PASSWORD, create_space, register

from pilot_api.routers import auth as auth_router


@pytest.fixture
def mailbox(monkeypatch):
    """Remplace l'envoi Brevo : les e-mails sont gardés en mémoire."""
    sent: list[dict] = []
    monkeypatch.setattr(auth_router, "mail_configured", lambda: True)
    monkeypatch.setattr(auth_router, "send_email", lambda **message: sent.append(message))
    return sent


def _token(message: dict) -> str:
    return re.search(r"jeton=([\w-]+)", message["text"]).group(1)


def test_rename_display_name(make_client):
    client = make_client()
    register(client, "gedeon@exemple.com", "gedeon")

    me = client.patch("/api/auth/me", json={"display_name": "Gédéon Baroki"}).json()

    assert me["user"]["display_name"] == "Gédéon Baroki"


def test_change_password_requires_current_and_closes_other_sessions(make_client):
    laptop = make_client()
    register(laptop, "gedeon@exemple.com")
    phone = make_client()
    phone.post("/api/auth/login", json={"email": "gedeon@exemple.com", "password": PASSWORD})

    wrong = laptop.post(
        "/api/auth/password",
        json={"current_password": "faux", "new_password": "nouveau-mot-de-passe"},
    )
    ok = laptop.post(
        "/api/auth/password",
        json={"current_password": PASSWORD, "new_password": "nouveau-mot-de-passe"},
    )

    assert wrong.status_code == 400
    assert ok.status_code == 204
    assert laptop.get("/api/auth/me").status_code == 200
    assert phone.get("/api/auth/me").status_code == 401
    login = make_client().post(
        "/api/auth/login", json={"email": "gedeon@exemple.com", "password": "nouveau-mot-de-passe"}
    )
    assert login.status_code == 200


def test_email_change_is_confirmed_by_a_link_sent_to_the_new_address(make_client, mailbox):
    client = make_client()
    register(client, "gedeon@exemple.com", "Gédéon")
    space = create_space(client)

    asked = client.post(
        "/api/auth/email-change",
        json={"new_email": "Contact@Nouveau-Exemple.com", "password": PASSWORD},
    )
    assert asked.status_code == 200
    assert asked.json()["sent_to"] == "contact@nouveau-exemple.com"
    assert mailbox[0]["to_email"] == "contact@nouveau-exemple.com"
    # Rien ne change avant la confirmation.
    assert client.get("/api/auth/me").json()["user"]["email"] == "gedeon@exemple.com"

    confirmed = client.post("/api/auth/email-change/confirm", json={"token": _token(mailbox[0])})
    assert confirmed.status_code == 200
    assert confirmed.json()["user"]["email"] == "contact@nouveau-exemple.com"

    members = client.get(f"/api/spaces/{space['id']}/members").json()
    assert members[0]["email"] == "contact@nouveau-exemple.com"
    login = make_client().post(
        "/api/auth/login", json={"email": "contact@nouveau-exemple.com", "password": PASSWORD}
    )
    assert login.status_code == 200
    # Le lien ne sert qu'une fois.
    again = client.post("/api/auth/email-change/confirm", json={"token": _token(mailbox[0])})
    assert again.status_code == 404


def test_email_change_refusals(make_client, mailbox):
    client = make_client()
    register(client, "a@exemple.com")
    register(make_client(), "pris@exemple.com")

    wrong_password = client.post(
        "/api/auth/email-change", json={"new_email": "b@exemple.com", "password": "faux"}
    )
    taken = client.post(
        "/api/auth/email-change", json={"new_email": "pris@exemple.com", "password": PASSWORD}
    )
    same = client.post(
        "/api/auth/email-change", json={"new_email": "a@exemple.com", "password": PASSWORD}
    )

    assert wrong_password.status_code == 400
    assert taken.status_code == 409
    assert same.status_code == 400
    assert mailbox == []


def test_confirmation_link_only_works_for_its_own_account(make_client, mailbox):
    owner = make_client()
    register(owner, "a@exemple.com")
    owner.post(
        "/api/auth/email-change", json={"new_email": "nouvelle@exemple.com", "password": PASSWORD}
    )
    intruder = make_client()
    register(intruder, "intrus@exemple.com")

    response = intruder.post("/api/auth/email-change/confirm", json={"token": _token(mailbox[0])})

    assert response.status_code == 404
    assert intruder.get("/api/auth/me").json()["user"]["email"] == "intrus@exemple.com"


def test_email_change_needs_mail_sending(make_client, monkeypatch):
    monkeypatch.setattr(auth_router, "mail_configured", lambda: False)
    client = make_client()
    register(client, "a@exemple.com")

    response = client.post(
        "/api/auth/email-change", json={"new_email": "b@exemple.com", "password": PASSWORD}
    )

    assert response.status_code == 503
