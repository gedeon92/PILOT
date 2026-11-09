"""Compléments du cahier des charges : contributeurs (§21), liens entre projets (§5), tâches du
suivi général, source de la situation (§21), origine du besoin (§6), options de décision (§7),
emoji de portefeuille (§13)."""

import io
import json
import zipfile
from zoneinfo import ZoneInfo

from conftest import create_space, invite_and_join, register

from pilot_api.portability import DATA_NAME

DAKAR = ZoneInfo("Africa/Dakar")


def _setup(make_client):
    owner = make_client()
    register(owner, "proprio@exemple.com", "Aïcha Ndiaye")
    space = create_space(owner, "Groupe Horizon")
    base = f"/api/spaces/{space['id']}"
    portfolio = owner.post(f"{base}/portfolios", json={"name": "Événements", "emoji": "🎪"}).json()
    return owner, space, base, portfolio


def _project(client, base, portfolio, title, **fields):
    response = client.post(
        f"{base}/projects", json={"title": title, "portfolio_id": portfolio["id"], **fields}
    )
    assert response.status_code == 201, response.text
    return response.json()


def _history(client, base, project):
    return client.get(f"{base}/projects/{project['id']}/history").json()


def test_contributors_are_distinct_from_the_responsible(make_client):
    owner, space, base, portfolio = _setup(make_client)
    helper = make_client()
    member = invite_and_join(owner, helper, space["id"], "moussa@exemple.com", "reader")

    project = _project(
        owner,
        base,
        portfolio,
        "Salon Agri",
        owner_label="Mon assistante",
        contributors=[
            {"member_id": member["id"]},
            {"label": "Agence Lumière"},
            {"label": "agence lumière"},  # doublon ignoré
            {"label": ""},  # vide ignoré
        ],
    )

    assert project["owner"]["name"] == "Mon assistante"
    assert [(c["name"], c["has_account"]) for c in project["contributors"]] == [
        ("Utilisateur Test", True),
        ("Agence Lumière", False),
    ]
    # Être contributeur d'un projet ne donne aucun droit : le lecteur reste lecteur.
    assert (
        helper.patch(
            f"{base}/projects/{project['id']}", json={"version": 1, "next_step": "x"}
        ).status_code
        == 403
    )

    updated = owner.patch(
        f"{base}/projects/{project['id']}",
        json={"version": project["version"], "contributors": [{"label": "Agence Lumière"}]},
    ).json()
    assert [c["name"] for c in updated["contributors"]] == ["Agence Lumière"]
    change = _history(owner, base, project)[0]
    assert change["before"]["contributors"] == ["Utilisateur Test", "Agence Lumière"]
    assert change["after"]["contributors"] == ["Agence Lumière"]


def test_origin_and_decision_options_are_kept(make_client):
    owner, _, base, portfolio = _setup(make_client)
    project = _project(
        owner,
        base,
        portfolio,
        "Nouveau salon",
        origin="Demandé par la direction générale, réunion du 3 novembre",
        decision_needed="Choisir le lieu",
        decision_maker="Directrice générale",
        decision_options=[
            {"label": "CICAD", "consequence": "Plus cher, plus grand"},
            {"label": "Hôtel", "consequence": None},
        ],
    )

    assert project["origin"].startswith("Demandé par la direction")
    assert [o["label"] for o in project["decision_options"]] == ["CICAD", "Hôtel"]
    too_many = owner.patch(
        f"{base}/projects/{project['id']}",
        json={"version": 1, "decision_options": [{"label": str(i)} for i in range(4)]},
    )
    assert too_many.status_code == 422
    cleared = owner.patch(
        f"{base}/projects/{project['id']}", json={"version": 1, "decision_options": []}
    ).json()
    assert cleared["decision_options"] == []


def test_situation_source_says_where_it_comes_from(make_client):
    owner, _, base, portfolio = _setup(make_client)
    project = _project(owner, base, portfolio, "Atlas", situation="Lieu réservé")

    assert project["situation_source"] == "manual"
    assert project["situation_updated_by"] == "Aïcha Ndiaye"

    request = owner.post(
        f"{base}/updates",
        data={"message": "Projet Atlas — Situation : devis signé"},
        files={"files": ("point.txt", b"Projet Atlas - Situation : devis signe", "text/plain")},
    ).json()
    proposal = next(p for p in request["proposals"] if p["project"])
    applied = owner.post(
        f"{base}/proposals/{proposal['id']}/apply",
        json={"fields": ["situation"], "base_version": proposal["base_version"]},
    )
    assert applied.status_code == 200, applied.text

    after = owner.get(f"{base}/projects/{project['id']}").json()
    assert after["situation_source"] == "update"
    assert after["situation_source_label"] == proposal["source_label"]
    assert after["situation_updated_by"] == "Aïcha Ndiaye"


def test_tasks_always_belong_to_a_project(make_client):
    """Décision du 9 nov. 2026 : plus de tâche du « suivi général » sans projet."""
    owner, space, base, portfolio = _setup(make_client)
    project = _project(owner, base, portfolio, "Atlas")

    without = owner.post(f"{base}/tasks", json={"title": "Préparer le comité"})
    in_project = owner.post(f"{base}/tasks", json={"title": "Devis", "project_id": project["id"]})
    reader = make_client()
    invite_and_join(owner, reader, space["id"], "lecteur@exemple.com", "reader")
    refused = reader.post(f"{base}/tasks", json={"title": "Non", "project_id": project["id"]})

    assert without.status_code == 422
    assert in_project.status_code == 201 and in_project.json()["project_id"] == project["id"]
    assert refused.status_code == 403
    assert [t["title"] for t in owner.get(f"{base}/tasks").json()] == ["Devis"]


def test_project_links_are_symmetric_and_journaled(make_client):
    owner, _, base, portfolio = _setup(make_client)
    salon = _project(owner, base, portfolio, "Salon Agri")
    campagne = _project(owner, base, portfolio, "Campagne radio")

    created = owner.post(
        f"{base}/projects/{salon['id']}/links",
        json={"project_id": campagne["id"], "note": "Même audience"},
    )
    duplicate = owner.post(
        f"{base}/projects/{campagne['id']}/links", json={"project_id": salon["id"]}
    )
    itself = owner.post(f"{base}/projects/{salon['id']}/links", json={"project_id": salon["id"]})

    assert created.status_code == 201, created.text
    assert duplicate.status_code == 409 and itself.status_code == 422
    seen_from_other = owner.get(f"{base}/projects/{campagne['id']}/links").json()
    assert [(lk["project"]["title"], lk["note"]) for lk in seen_from_other] == [
        ("Salon Agri", "Même audience")
    ]
    assert seen_from_other[0]["project"]["portfolio"]["emoji"] == "🎪"
    assert _history(owner, base, campagne)[0]["action"] == "project.linked"

    removed = owner.delete(f"{base}/projects/{campagne['id']}/links/{salon['id']}")
    assert removed.status_code == 204
    assert owner.get(f"{base}/projects/{salon['id']}/links").json() == []
    assert _history(owner, base, salon)[0]["action"] == "project.unlinked"


def test_complements_survive_export_and_import(make_client):
    owner, _, base, portfolio = _setup(make_client)
    salon = _project(
        owner,
        base,
        portfolio,
        "Salon Agri",
        origin="Comité de direction",
        contributors=[{"label": "Agence Lumière"}],
        decision_options=[{"label": "Reporter"}],
    )
    campagne = _project(owner, base, portfolio, "Campagne radio")
    owner.post(f"{base}/projects/{salon['id']}/links", json={"project_id": campagne["id"]})
    owner.post(f"{base}/tasks", json={"title": "Préparer le comité", "project_id": salon["id"]})
    # Un ancien export peut contenir des tâches sans projet : on en fabrique une.
    archive = zipfile.ZipFile(io.BytesIO(owner.get(f"{base}/export").content))
    data = json.loads(archive.read(DATA_NAME))
    data["tasks"][0]["project_id"] = None
    rebuilt = io.BytesIO()
    with zipfile.ZipFile(rebuilt, "w") as out:
        for name in archive.namelist():
            out.writestr(name, archive.read(name) if name != DATA_NAME else json.dumps(data))

    report = owner.post(
        "/api/space-imports", files={"file": ("e.zip", rebuilt.getvalue(), "application/zip")}
    ).json()

    new = f"/api/spaces/{report['space_id']}"
    projects = {p["title"]: p for p in owner.get(f"{new}/projects").json()}
    imported = projects["Salon Agri"]
    assert imported["origin"] == "Comité de direction"
    assert [c["name"] for c in imported["contributors"]] == ["Agence Lumière"]
    assert [o["label"] for o in imported["decision_options"]] == ["Reporter"]
    assert imported["portfolio"]["emoji"] == "🎪"
    links = owner.get(f"{new}/projects/{imported['id']}/links").json()
    assert [lk["project"]["title"] for lk in links] == ["Campagne radio"]
    # La tâche sans projet de l'ancien export est rangée dans « Suivi général ».
    general = projects["Suivi général"]
    tasks = owner.get(f"{new}/tasks").json()
    assert [(t["title"], t["project_id"]) for t in tasks] == [("Préparer le comité", general["id"])]
    assert any("Suivi général" in w for w in report["warnings"])
