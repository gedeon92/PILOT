"""Tâches répétées, modèles de projet et fichiers joints aux tâches (suite « Asana », n° 1 à 3).
Rien de ce qui existait ne change : une tâche sans répétition se termine comme avant."""

from datetime import date, timedelta

from conftest import create_space, invite_and_join, register

from pilot_api.models import TaskRecurrence
from pilot_api.recurrence import next_due_date


def _setup(make_client):
    owner = make_client()
    register(owner, "proprio@exemple.com", "Aïcha Ndiaye")
    space = create_space(owner, "Groupe Horizon")
    base = f"/api/spaces/{space['id']}"
    portfolio = owner.post(f"{base}/portfolios", json={"name": "Événements"}).json()
    project = owner.post(
        f"{base}/projects",
        json={"title": "Salon Agri", "portfolio_id": portfolio["id"], "start_date": "2026-12-10"},
    ).json()
    return owner, space, base, portfolio, project


def _task(client, base, project, title, **fields):
    response = client.post(
        f"{base}/projects/{project['id']}/tasks", json={"title": title, **fields}
    )
    assert response.status_code == 201, response.text
    return response.json()


def _tasks(client, base, project):
    return client.get(f"{base}/projects/{project['id']}/tasks").json()


# ---------- n° 1 : tâches répétées ----------


def test_next_due_date_keeps_the_rhythm_and_never_starts_late():
    today = date(2026, 11, 10)
    assert next_due_date(date(2026, 11, 16), TaskRecurrence.WEEKLY, today) == date(2026, 11, 23)
    # Terminée en retard : on saute les échéances passées.
    assert next_due_date(date(2026, 10, 1), TaskRecurrence.WEEKLY, today) == date(2026, 11, 12)
    assert next_due_date(date(2027, 1, 31), TaskRecurrence.MONTHLY, today) == date(2027, 2, 28)
    assert next_due_date(date(2028, 2, 29), TaskRecurrence.YEARLY, today) == date(2029, 2, 28)
    assert next_due_date(date(2026, 11, 20), TaskRecurrence.DAILY, today) == date(2026, 11, 21)


def test_a_repeated_task_creates_the_next_one_when_done_once_only(make_client):
    owner, space, base, _, project = _setup(make_client)
    moussa_client = make_client()
    moussa = invite_and_join(owner, moussa_client, space["id"], "moussa@exemple.com", "contributor")
    due = (date.today() + timedelta(days=3)).isoformat()
    task = _task(
        owner,
        base,
        project,
        "Envoyer le rapport",
        due_date=due,
        recurrence="weekly",
        assignee_member_id=moussa["id"],
    )
    assert task["recurrence"] == "weekly"
    owner.post(f"{base}/tasks/{task['id']}/subtasks", json={"title": "Relire les chiffres"})

    done = owner.patch(
        f"{base}/tasks/{task['id']}", json={"version": task["version"], "status": "done"}
    ).json()
    assert done["next_task_id"]
    listed = {t["id"]: t for t in _tasks(owner, base, project)}
    following = listed[done["next_task_id"]]
    assert following["title"] == "Envoyer le rapport" and following["status"] == "todo"
    assert following["due_date"] == (date.fromisoformat(due) + timedelta(weeks=1)).isoformat()
    assert following["recurrence"] == "weekly"
    assert following["assignee"]["member_id"] == moussa["id"]
    assert following["subtasks_total"] == 1
    # Le responsable (abonné) est prévenu de la prochaine échéance.
    alerts = moussa_client.get(f"{base}/alerts").json()["items"]
    assert any("prochaine est prévue" in a["detail"] for a in alerts)

    # Rouverte puis terminée de nouveau : pas de seconde copie.
    reopened = owner.patch(
        f"{base}/tasks/{task['id']}", json={"version": done["version"], "status": "todo"}
    ).json()
    owner.patch(
        f"{base}/tasks/{task['id']}", json={"version": reopened["version"], "status": "done"}
    )
    titles = [t["title"] for t in _tasks(owner, base, project) if t["parent_id"] is None]
    assert titles.count("Envoyer le rapport") == 2

    history = [h["action"] for h in owner.get(f"{base}/projects/{project['id']}/history").json()]
    assert "task.repeated" in history


def test_repetition_needs_a_due_date_and_is_not_for_subtasks_or_cancelled(make_client):
    owner, _, base, _, project = _setup(make_client)
    refused = owner.post(
        f"{base}/projects/{project['id']}/tasks", json={"title": "Sans date", "recurrence": "daily"}
    )
    assert refused.status_code == 422
    parent = _task(owner, base, project, "Logistique")
    sub = owner.post(f"{base}/tasks/{parent['id']}/subtasks", json={"title": "Salle"}).json()
    sub_refused = owner.patch(
        f"{base}/tasks/{sub['id']}",
        json={"version": sub["version"], "recurrence": "daily", "due_date": "2026-12-01"},
    )
    assert sub_refused.status_code == 422

    task = _task(owner, base, project, "Point d'équipe", due_date="2026-12-01", recurrence="daily")
    cancelled = owner.patch(
        f"{base}/tasks/{task['id']}", json={"version": task["version"], "status": "cancelled"}
    ).json()
    assert cancelled["next_task_id"] is None
    # Retirer l'échéance d'une tâche répétée est refusé ; retirer la répétition est permis.
    no_due = owner.patch(
        f"{base}/tasks/{task['id']}", json={"version": cancelled["version"], "due_date": None}
    )
    assert no_due.status_code == 422
    plain = owner.patch(
        f"{base}/tasks/{task['id']}", json={"version": cancelled["version"], "recurrence": None}
    )
    assert plain.status_code == 200 and plain.json()["recurrence"] is None


# ---------- n° 2 : modèles de projet ----------


def test_a_template_copies_tasks_with_dates_counted_from_the_start(make_client):
    owner, space, base, portfolio, project = _setup(make_client)
    venue = _task(owner, base, project, "Réserver la salle", due_date="2026-11-10")
    invitations = _task(owner, base, project, "Envoyer les invitations", due_date="2026-11-30")
    owner.post(f"{base}/tasks/{venue['id']}/subtasks", json={"title": "Comparer 3 devis"})
    owner.post(
        f"{base}/tasks/{invitations['id']}/dependencies", json={"depends_on_id": venue["id"]}
    )
    dropped = _task(owner, base, project, "Idée abandonnée")
    owner.patch(
        f"{base}/tasks/{dropped['id']}", json={"version": dropped["version"], "status": "cancelled"}
    )

    created = owner.post(
        f"{base}/templates", json={"project_id": project["id"], "name": "Salon type"}
    )
    assert created.status_code == 201, created.text
    template = created.json()
    assert template["tasks_count"] == 3  # la tâche annulée n'est pas reprise
    offsets = {t["title"]: t["offset_days"] for t in template["tasks"]}
    assert offsets["Réserver la salle"] == -30 and offsets["Envoyer les invitations"] == -10

    new = owner.post(
        f"{base}/projects",
        json={
            "title": "Salon Agri 2027",
            "portfolio_id": portfolio["id"],
            "start_date": "2027-03-01",
            "template_id": template["id"],
        },
    ).json()
    tasks = {t["title"]: t for t in _tasks(owner, base, new)}
    assert tasks["Réserver la salle"]["due_date"] == "2027-01-30"
    assert tasks["Envoyer les invitations"]["due_date"] == "2027-02-19"
    assert tasks["Envoyer les invitations"]["waiting_on"] == 1
    assert tasks["Comparer 3 devis"]["parent_id"] == tasks["Réserver la salle"]["id"]
    assert all(t["status"] == "todo" for t in tasks.values())

    # Sans date de début : les tâches arrivent sans échéance.
    undated = owner.post(
        f"{base}/projects",
        json={"title": "Salon ?", "portfolio_id": portfolio["id"], "template_id": template["id"]},
    ).json()
    assert all(t["due_date"] is None for t in _tasks(owner, base, undated))

    history = owner.get(f"{base}/projects/{new['id']}/history").json()
    assert history[-1]["after"]["template"] == "Salon type"


def test_only_owners_manage_templates_and_deleting_keeps_projects(make_client):
    owner, space, base, portfolio, project = _setup(make_client)
    moussa_client, fatou_client = make_client(), make_client()
    invite_and_join(owner, moussa_client, space["id"], "moussa@exemple.com", "contributor")
    invite_and_join(owner, fatou_client, space["id"], "fatou@exemple.com", "reader")
    _task(owner, base, project, "Réserver la salle")
    empty = owner.post(
        f"{base}/projects", json={"title": "Vide", "portfolio_id": portfolio["id"]}
    ).json()
    assert (
        owner.post(f"{base}/templates", json={"project_id": empty["id"], "name": "X"}).status_code
        == 422
    )

    refused = moussa_client.post(
        f"{base}/templates", json={"project_id": project["id"], "name": "Salon type"}
    )
    assert refused.status_code == 403
    template = owner.post(
        f"{base}/templates", json={"project_id": project["id"], "name": "Salon type"}
    ).json()
    # Le contributeur voit et utilise les modèles ; le lecteur ne crée pas de projet.
    assert [t["name"] for t in moussa_client.get(f"{base}/templates").json()] == ["Salon type"]
    assert fatou_client.get(f"{base}/templates").status_code == 403
    used = moussa_client.post(
        f"{base}/projects",
        json={
            "title": "Salon 2027",
            "portfolio_id": portfolio["id"],
            "template_id": template["id"],
        },
    ).json()

    renamed = owner.patch(
        f"{base}/templates/{template['id']}",
        json={"version": template["version"], "name": "Salon (modèle)"},
    ).json()
    assert renamed["name"] == "Salon (modèle)"
    assert moussa_client.delete(f"{base}/templates/{template['id']}").status_code == 403
    assert owner.delete(f"{base}/templates/{template['id']}").status_code == 204
    assert owner.get(f"{base}/templates").json() == []
    assert [t["title"] for t in _tasks(owner, base, used)] == ["Réserver la salle"]


# ---------- n° 3 : fichiers joints aux tâches ----------


def test_files_attached_to_a_task_also_belong_to_the_project(make_client):
    owner, space, base, _, project = _setup(make_client)
    fatou_client = make_client()
    invite_and_join(owner, fatou_client, space["id"], "fatou@exemple.com", "reader")
    task = _task(owner, base, project, "Réserver la salle")

    url = f"{base}/tasks/{task['id']}/documents"
    uploaded = owner.post(url, files={"file": ("devis.pdf", b"%PDF-1.4 devis", "application/pdf")})
    assert uploaded.status_code == 201, uploaded.text
    document = uploaded.json()
    assert document["task_id"] == task["id"] and document["task_title"] == "Réserver la salle"

    detail = owner.get(f"{base}/tasks/{task['id']}").json()
    assert [d["filename"] for d in detail["documents"]] == ["devis.pdf"]
    assert detail["task"]["documents_count"] == 1
    in_project = owner.get(f"{base}/projects/{project['id']}/documents").json()
    assert in_project[0]["task_title"] == "Réserver la salle"

    # Une nouvelle version reste jointe à la tâche ; retirée, elle n'est plus comptée.
    replaced = owner.post(
        f"{base}/documents/{document['id']}/replace",
        files={"file": ("devis-v2.pdf", b"%PDF-1.4 devis 2", "application/pdf")},
    ).json()
    assert replaced["task_id"] == task["id"] and replaced["revision"] == 2
    assert [d["filename"] for d in owner.get(f"{base}/tasks/{task['id']}").json()["documents"]] == [
        "devis-v2.pdf"
    ]

    # Le lecteur télécharge mais ne joint rien.
    assert fatou_client.get(f"{base}/documents/{replaced['id']}/download").status_code == 200
    refused = fatou_client.post(url, files={"file": ("x.txt", b"x", "text/plain")})
    assert refused.status_code == 403

    owner.post(f"{base}/documents/{replaced['id']}/archive")
    assert owner.get(f"{base}/tasks/{task['id']}").json()["task"]["documents_count"] == 0


def test_repeat_templates_and_attachments_survive_export_and_import(make_client):
    owner, _, base, _, project = _setup(make_client)
    task = _task(owner, base, project, "Rapport", due_date="2026-12-01", recurrence="monthly")
    owner.patch(f"{base}/tasks/{task['id']}", json={"version": task["version"], "status": "done"})
    owner.post(
        f"{base}/tasks/{task['id']}/documents",
        files={"file": ("rapport.pdf", b"%PDF rapport", "application/pdf")},
    )
    owner.post(f"{base}/templates", json={"project_id": project["id"], "name": "Suivi mensuel"})

    report = owner.post(
        "/api/space-imports",
        files={"file": ("e.zip", owner.get(f"{base}/export").content, "application/zip")},
    ).json()
    new = f"/api/spaces/{report['space_id']}"
    tasks = owner.get(f"{new}/tasks?include_closed=true").json()
    done = next(t for t in tasks if t["status"] == "done")
    open_ = next(t for t in tasks if t["status"] == "todo")
    assert done["recurrence"] == "monthly" and done["next_task_id"] == open_["id"]
    assert done["documents_count"] == 1
    templates = owner.get(f"{new}/templates").json()
    assert [t["name"] for t in templates] == ["Suivi mensuel"]
    # Le modèle ne reprend que l'occurrence la plus récente de la tâche répétée.
    assert [t["title"] for t in templates[0]["tasks"]] == ["Rapport"]
