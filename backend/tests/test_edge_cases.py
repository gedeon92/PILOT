"""Cas limites (CDC §19) : titres longs, accents, doublons de noms, session expirée,
listes longues, contenu piégé."""

from datetime import timedelta

from conftest import create_space, register
from sqlalchemy import update
from sqlalchemy.orm import Session

from pilot_api.models import AuthSession, utcnow


def _setup(make_client):
    owner = make_client()
    register(owner, "proprio@exemple.com", "Aïcha Ndiaye")
    space = create_space(owner)
    base = f"/api/spaces/{space['id']}"
    portfolio = owner.post(f"{base}/portfolios", json={"name": "Projets groupe"}).json()
    return owner, base, portfolio


def test_long_titles_accents_and_symbols_are_kept_exactly(make_client):
    owner, base, portfolio = _setup(make_client)
    title = ("Salon « Économie & Agriculture » — édition n°3 ✨ " * 5)[:200]

    created = owner.post(f"{base}/projects", json={"title": title, "portfolio_id": portfolio["id"]})
    too_long = owner.post(
        f"{base}/projects", json={"title": "x" * 201, "portfolio_id": portfolio["id"]}
    )

    assert created.status_code == 201
    assert owner.get(f"{base}/projects/{created.json()['id']}").json()["title"] == title
    assert too_long.status_code == 422


def test_html_is_stored_as_text_never_interpreted(make_client):
    owner, base, portfolio = _setup(make_client)
    payload = '<img src=x onerror="alert(1)"><script>alert(2)</script>'

    created = owner.post(
        f"{base}/projects",
        json={"title": payload, "portfolio_id": portfolio["id"], "situation": payload},
    ).json()

    # L'API renvoie le texte tel quel (JSON) ; l'interface React l'affiche comme du texte.
    assert created["title"] == payload
    assert created["situation"] == payload


def test_duplicate_names_differing_by_case_or_spaces(make_client):
    owner, base, portfolio = _setup(make_client)
    again = owner.post(f"{base}/portfolios", json={"name": "  projets GROUPE "})
    # Deux projets peuvent porter le même titre : ce sont deux fiches distinctes.
    first = owner.post(f"{base}/projects", json={"title": "Atlas", "portfolio_id": portfolio["id"]})
    second = owner.post(
        f"{base}/projects", json={"title": "Atlas", "portfolio_id": portfolio["id"]}
    )

    assert again.status_code == 409
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] != second.json()["id"]


def test_expired_session_is_refused(make_client, engine):
    client = make_client()
    register(client, "a@exemple.com")
    assert client.get("/api/auth/me").status_code == 200

    with Session(engine) as db:
        db.execute(update(AuthSession).values(expires_at=utcnow() - timedelta(minutes=1)))
        db.commit()

    assert client.get("/api/auth/me").status_code == 401
    assert client.post("/api/spaces", json={"name": "X", "timezone": "UTC"}).status_code == 401


def test_documents_list_is_paginated(make_client):
    owner, base, portfolio = _setup(make_client)
    project = owner.post(
        f"{base}/projects", json={"title": "Atlas", "portfolio_id": portfolio["id"]}
    ).json()
    for i in range(5):
        owner.post(
            f"{base}/projects/{project['id']}/documents",
            files={"file": (f"piece-{i}.txt", f"contenu {i}".encode(), "text/plain")},
        )

    first = owner.get(f"{base}/documents?limit=2").json()
    second = owner.get(f"{base}/documents?limit=2&offset=2").json()
    last = owner.get(f"{base}/documents?limit=2&offset=4").json()
    too_big = owner.get(f"{base}/documents?limit=5000")

    names = [d["filename"] for d in first + second + last]
    assert len(names) == len(set(names)) == 5
    assert too_big.status_code == 422


def test_uploaded_html_is_always_downloaded_not_displayed(make_client):
    owner, base, portfolio = _setup(make_client)
    project = owner.post(
        f"{base}/projects", json={"title": "Atlas", "portfolio_id": portfolio["id"]}
    ).json()
    document = owner.post(
        f"{base}/projects/{project['id']}/documents",
        files={"file": ("../../piege.html", b"<script>alert(1)</script>", "text/html")},
    ).json()

    response = owner.get(f"{base}/documents/{document['id']}/download")

    assert document["filename"] == "piege.html"
    assert response.headers["content-disposition"].startswith("attachment")
    assert response.headers["x-content-type-options"] == "nosniff"
