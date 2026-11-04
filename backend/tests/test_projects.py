import uuid
from datetime import date, timedelta

from conftest import create_space, invite_and_join, register


def _setup(make_client):
    owner = make_client()
    register(owner, "proprio@exemple.com", "Aïcha Ndiaye")
    space = create_space(owner)
    base = f"/api/spaces/{space['id']}"
    portfolio = owner.post(f"{base}/portfolios", json={"name": "Événements"}).json()
    return owner, space, base, portfolio


def _create(client, base, portfolio, **fields):
    response = client.post(
        f"{base}/projects", json={"title": "Atlas", "portfolio_id": portfolio["id"], **fields}
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_default_event_type_has_event_kind(make_client):
    owner, _, base, _ = _setup(make_client)
    kinds = {t["name"]: t["kind"] for t in owner.get(f"{base}/project-types").json()}
    assert kinds == {
        "Autre": "standard",
        "Événement": "event",
        "Mission": "standard",
        "Produit": "standard",
    }


def test_project_is_saved_and_reopened_elsewhere(make_client):
    """PRJ01 : un projet créé puis rouvert sur un autre appareil garde données et rattachements."""
    owner, _, base, portfolio = _setup(make_client)
    entity = owner.post(f"{base}/entities", json={"name": "Horizon Events"}).json()
    created = _create(
        owner,
        base,
        portfolio,
        entity_id=entity["id"],
        situation="Lieu confirmé",
        next_step="Valider le budget",
        due_date="2026-11-12",
        date_certainty="confirmed",
    )

    other_device = make_client()
    other_device.post(
        "/api/auth/login", json={"email": "proprio@exemple.com", "password": "mot-de-passe-solide"}
    )
    reopened = other_device.get(f"{base}/projects/{created['id']}").json()

    assert reopened["title"] == "Atlas"
    assert reopened["status"] == "to_frame"
    assert reopened["portfolio"]["name"] == "Événements"
    assert reopened["entity"]["name"] == "Horizon Events"
    assert reopened["next_step"] == "Valider le budget"
    assert reopened["due_date"] == "2026-11-12"
    assert reopened["situation_updated_at"] is not None


def test_unknown_information_stays_empty(make_client):
    owner, _, base, portfolio = _setup(make_client)
    project = _create(owner, base, portfolio)
    assert project["progress"] is None
    assert project["due_date"] is None
    assert project["owner"] == {"member_id": None, "name": None, "has_account": False}


def test_owner_attribution_member_or_free_name(make_client):
    """PRJ02 : attribution à la propriétaire puis à « Mon assistante » ; droits inchangés."""
    owner, space, base, portfolio = _setup(make_client)
    project = _create(owner, base, portfolio)
    me = next(m for m in owner.get(f"{base}/members").json() if m["is_me"])

    to_me = owner.patch(
        f"{base}/projects/{project['id']}", json={"version": 1, "owner_member_id": me["id"]}
    ).json()
    assert to_me["owner"] == {"member_id": me["id"], "name": "Aïcha Ndiaye", "has_account": True}

    to_assistant = owner.patch(
        f"{base}/projects/{project['id']}", json={"version": 2, "owner_label": "Mon assistante"}
    ).json()
    assert to_assistant["owner"] == {
        "member_id": None,
        "name": "Mon assistante",
        "has_account": False,
    }
    # Aucun compte ni droit créé pour « Mon assistante ».
    assert [m["email"] for m in owner.get(f"{base}/members").json()] == ["proprio@exemple.com"]

    history = owner.get(f"{base}/projects/{project['id']}/history").json()
    assert history[0]["action"] == "project.updated"
    assert history[0]["after"]["owner_label"] == "Mon assistante"


def test_owner_must_be_a_member_of_the_space(make_client):
    owner, _, base, portfolio = _setup(make_client)
    project = _create(owner, base, portfolio)
    response = owner.patch(
        f"{base}/projects/{project['id']}",
        json={"version": 1, "owner_member_id": str(uuid.uuid4())},
    )
    assert response.status_code == 422


def test_concurrent_edits_are_detected(make_client):
    """PRJ03 : deux personnes enregistrent depuis la même version : conflit explicite."""
    owner, space, base, portfolio = _setup(make_client)
    contributor = make_client()
    invite_and_join(owner, contributor, space["id"], "c@exemple.com", "contributor")
    project = _create(owner, base, portfolio)

    first = owner.patch(f"{base}/projects/{project['id']}", json={"version": 1, "next_step": "A"})
    second = contributor.patch(
        f"{base}/projects/{project['id']}", json={"version": 1, "next_step": "B"}
    )

    assert first.status_code == 200
    assert second.status_code == 409
    assert owner.get(f"{base}/projects/{project['id']}").json()["next_step"] == "A"


def test_retry_does_not_create_a_second_project(make_client):
    owner, _, base, portfolio = _setup(make_client)
    request_id = str(uuid.uuid4())

    first = _create(owner, base, portfolio, client_request_id=request_id)
    again = _create(owner, base, portfolio, client_request_id=request_id)

    assert again["id"] == first["id"]
    assert len(owner.get(f"{base}/projects").json()) == 1


def test_contributor_writes_reader_only_reads(make_client):
    owner, space, base, portfolio = _setup(make_client)
    contributor, reader = make_client(), make_client()
    invite_and_join(owner, contributor, space["id"], "c@exemple.com", "contributor")
    invite_and_join(owner, reader, space["id"], "r@exemple.com", "reader")

    project = _create(contributor, base, portfolio)
    refused = reader.post(f"{base}/projects", json={"title": "X", "portfolio_id": portfolio["id"]})
    edit = reader.patch(f"{base}/projects/{project['id']}", json={"version": 1, "title": "X"})
    task = reader.post(f"{base}/projects/{project['id']}/tasks", json={"title": "X"})

    assert refused.status_code == edit.status_code == task.status_code == 403
    assert reader.get(f"{base}/projects/{project['id']}").json()["title"] == "Atlas"


def test_references_must_be_active_and_in_the_space(make_client):
    owner, _, base, portfolio = _setup(make_client)
    archived = owner.post(f"{base}/portfolios", json={"name": "Ancien"}).json()
    owner.patch(f"{base}/portfolios/{archived['id']}", json={"version": 1, "archived": True})
    other = make_client()
    register(other, "autre@exemple.com")
    other_base = f"/api/spaces/{create_space(other, 'Autre')['id']}"
    foreign = other.post(f"{other_base}/portfolios", json={"name": "Étranger"}).json()

    on_archived = owner.post(
        f"{base}/projects", json={"title": "X", "portfolio_id": archived["id"]}
    )
    on_foreign = owner.post(f"{base}/projects", json={"title": "X", "portfolio_id": foreign["id"]})

    assert on_archived.status_code == on_foreign.status_code == 422


def test_projects_are_isolated_between_spaces(make_client):
    owner, _, base, portfolio = _setup(make_client)
    project = _create(owner, base, portfolio)
    other = make_client()
    register(other, "autre@exemple.com")
    other_base = f"/api/spaces/{create_space(other, 'Autre')['id']}"

    assert other.get(f"{base}/projects/{project['id']}").status_code == 404
    assert other.get(f"{other_base}/projects/{project['id']}").status_code == 404
    forged = other.patch(
        f"{other_base}/projects/{project['id']}", json={"version": 1, "title": "X"}
    )
    assert forged.status_code == 404


def test_date_rules(make_client):
    owner, _, base, portfolio = _setup(make_client)
    reversed_dates = owner.post(
        f"{base}/projects",
        json={
            "title": "X",
            "portfolio_id": portfolio["id"],
            "start_date": "2026-12-10",
            "end_date": "2026-12-01",
        },
    )
    half_window = owner.post(
        f"{base}/projects",
        json={"title": "X", "portfolio_id": portfolio["id"], "window_start": "2026-12-01"},
    )
    window = _create(owner, base, portfolio, window_start="2026-12-01", window_end="2026-12-31")

    assert reversed_dates.status_code == half_window.status_code == 422
    assert window["window_end"] == "2026-12-31"
    assert window["due_date"] is None  # une période n'invente pas de date exacte (CAL01)


def test_done_requires_an_outcome(make_client):
    owner, _, base, portfolio = _setup(make_client)
    project = _create(owner, base, portfolio)
    url = f"{base}/projects/{project['id']}/status"

    missing = owner.post(url, json={"version": 1, "status": "done"})
    done = owner.post(url, json={"version": 1, "status": "done", "outcome": "Objectif atteint"})

    assert missing.status_code == 422
    assert done.status_code == 200
    assert done.json()["outcome"] == "Objectif atteint"


def test_cancel_requires_reason_and_closes_open_tasks(make_client):
    owner, _, base, portfolio = _setup(make_client)
    project = _create(owner, base, portfolio)
    tasks_url = f"{base}/projects/{project['id']}/tasks"
    finished = owner.post(tasks_url, json={"title": "Réserver la salle"}).json()
    owner.patch(f"{base}/tasks/{finished['id']}", json={"version": 1, "status": "done"})
    owner.post(tasks_url, json={"title": "Envoyer les invitations"})
    url = f"{base}/projects/{project['id']}/status"

    assert owner.post(url, json={"version": 1, "status": "cancelled"}).status_code == 422
    cancelled = owner.post(url, json={"version": 1, "status": "cancelled", "reason": "Report"})

    assert cancelled.status_code == 200
    statuses = {t["title"]: t["status"] for t in owner.get(tasks_url).json()}
    # Les tâches déjà terminées restent terminées ; les autres sont annulées (CDC §12, §22).
    assert statuses == {"Réserver la salle": "done", "Envoyer les invitations": "cancelled"}
    assert owner.post(tasks_url, json={"title": "Nouvelle"}).status_code == 400


def test_reopening_is_journaled(make_client):
    owner, _, base, portfolio = _setup(make_client)
    project = _create(owner, base, portfolio)
    url = f"{base}/projects/{project['id']}/status"
    owner.post(url, json={"version": 1, "status": "done", "outcome": "Bilan"})

    reopened = owner.post(url, json={"version": 2, "status": "in_progress"})

    assert reopened.json()["status"] == "in_progress"
    history = owner.get(f"{base}/projects/{project['id']}/history").json()
    assert [h["action"] for h in history][:2] == ["project.reopened", "project.status_changed"]


def test_tasks_lifecycle_and_late_flag(make_client):
    owner, _, base, portfolio = _setup(make_client)
    project = _create(owner, base, portfolio)
    tasks_url = f"{base}/projects/{project['id']}/tasks"
    yesterday = (date.today() - timedelta(days=2)).isoformat()

    late = owner.post(
        tasks_url,
        json={
            "title": "Devis traiteur",
            "due_date": yesterday,
            "due_certainty": "confirmed",
            "assignee_label": "Moussa Sow",
            "deliverable": "Devis signé",
        },
    ).json()
    owner.post(tasks_url, json={"title": "Sans date"})

    assert late["late"] is True
    assert late["assignee"]["name"] == "Moussa Sow"
    summary = owner.get(f"{base}/projects/{project['id']}").json()
    assert (summary["open_tasks"], summary["late_tasks"]) == (2, 1)

    done = owner.patch(f"{base}/tasks/{late['id']}", json={"version": 1, "status": "done"}).json()
    assert done["late"] is False
    assert done["closed_at"] is not None
    summary = owner.get(f"{base}/projects/{project['id']}").json()
    assert (summary["open_tasks"], summary["late_tasks"]) == (1, 0)

    stale = owner.patch(f"{base}/tasks/{late['id']}", json={"version": 1, "title": "X"})
    assert stale.status_code == 409


def test_tasks_are_isolated_between_spaces(make_client):
    owner, _, base, portfolio = _setup(make_client)
    project = _create(owner, base, portfolio)
    task = owner.post(f"{base}/projects/{project['id']}/tasks", json={"title": "Secret"}).json()
    other = make_client()
    register(other, "autre@exemple.com")
    other_base = f"/api/spaces/{create_space(other, 'Autre')['id']}"

    forged = other.patch(f"{other_base}/tasks/{task['id']}", json={"version": 1, "title": "X"})

    assert forged.status_code == 404


def test_project_list_filters(make_client):
    owner, _, base, portfolio = _setup(make_client)
    other_portfolio = owner.post(f"{base}/portfolios", json={"name": "Groupe"}).json()
    _create(owner, base, portfolio, title="Salon Dakar")
    _create(owner, base, other_portfolio, title="Refonte du site", status="blocked")

    by_portfolio = owner.get(f"{base}/projects", params={"portfolio_id": portfolio["id"]}).json()
    by_status = owner.get(f"{base}/projects", params={"status": "blocked"}).json()
    by_text = owner.get(f"{base}/projects", params={"q": "salon"}).json()

    assert [p["title"] for p in by_portfolio] == ["Salon Dakar"]
    assert [p["title"] for p in by_status] == ["Refonte du site"]
    assert [p["title"] for p in by_text] == ["Salon Dakar"]


def test_space_task_list_shows_open_tasks_only(make_client):
    owner, _, base, portfolio = _setup(make_client)
    project = _create(owner, base, portfolio)
    tasks_url = f"{base}/projects/{project['id']}/tasks"
    open_task = owner.post(tasks_url, json={"title": "Ouverte", "due_date": "2026-11-20"}).json()
    done = owner.post(tasks_url, json={"title": "Faite"}).json()
    owner.patch(f"{base}/tasks/{done['id']}", json={"version": 1, "status": "done"})

    listed = owner.get(f"{base}/tasks").json()
    everything = owner.get(f"{base}/tasks", params={"include_closed": True}).json()

    assert [t["id"] for t in listed] == [open_task["id"]]
    assert listed[0]["project_id"] == project["id"]
    assert len(everything) == 2
