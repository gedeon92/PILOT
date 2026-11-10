"""Étape F1 (cahier V2) : sections, nouveaux statuts, priorité, date de début, reports."""

from conftest import create_space, invite_and_join, register


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


def _sections(client, base, project):
    return client.get(f"{base}/projects/{project['id']}/sections").json()


def test_sections_are_created_ordered_renamed_and_hold_tasks(make_client):
    owner, space, base, portfolio, project = _setup(make_client)
    reader = make_client()
    invite_and_join(owner, reader, space["id"], "lecteur@exemple.com", "reader")
    url = f"{base}/projects/{project['id']}/sections"

    # Sans section, rien ne change : la liste reste vide.
    assert _sections(owner, base, project) == []
    defaults = owner.post(f"{url}/defaults")
    assert defaults.status_code == 201, defaults.text
    titles = [s["title"] for s in defaults.json()]
    assert titles == [
        "Cadrage",
        "Préparation",
        "Exécution",
        "Décisions et blocages",
        "Contrôle et validation",
        "Bilan et suites",
    ]
    assert owner.post(f"{url}/defaults").status_code == 409
    assert reader.post(url, json={"title": "Intrus"}).status_code == 403

    extra = owner.post(url, json={"title": "Logistique"}).json()
    renamed = owner.patch(
        f"{base}/sections/{extra['id']}", json={"version": extra["version"], "title": "Transport"}
    )
    assert renamed.json()["title"] == "Transport"

    ids = [s["id"] for s in _sections(owner, base, project)]
    new_order = [ids[-1], *ids[:-1]]
    ordered = owner.put(f"{url}/order", json={"ids": new_order})
    assert ordered.status_code == 200, ordered.text
    assert [s["title"] for s in ordered.json()][:2] == ["Transport", "Cadrage"]
    # Une liste incomplète est refusée (quelqu'un a pu ajouter une section entre-temps).
    assert owner.put(f"{url}/order", json={"ids": new_order[:-1]}).status_code == 409

    cadrage = next(s for s in ordered.json() if s["title"] == "Cadrage")
    task = _task(owner, base, project, "Fixer l'objectif", section_id=cadrage["id"])
    assert task["section_id"] == cadrage["id"]
    # Une section d'un autre projet ou une sous-tâche rangée à part : refusées.
    other = owner.post(
        f"{base}/projects", json={"title": "Autre", "portfolio_id": portfolio["id"]}
    ).json()
    bad = owner.post(
        f"{base}/projects/{other['id']}/tasks", json={"title": "X", "section_id": cadrage["id"]}
    )
    assert bad.status_code == 422
    sub = owner.post(
        f"{base}/tasks/{task['id']}/subtasks", json={"title": "Sous", "section_id": cadrage["id"]}
    )
    assert sub.status_code == 422

    history = owner.get(f"{base}/projects/{project['id']}/history").json()
    actions = {h["action"] for h in history}
    assert {
        "section.defaults",
        "section.created",
        "section.renamed",
        "section.reordered",
    } <= actions


def test_archiving_a_section_moves_open_tasks_and_keeps_everything(make_client):
    owner, _space, base, _portfolio, project = _setup(make_client)
    url = f"{base}/projects/{project['id']}/sections"
    a = owner.post(url, json={"title": "Préparation"}).json()
    b = owner.post(url, json={"title": "Exécution"}).json()
    open_task = _task(owner, base, project, "Réserver", section_id=a["id"])
    done_task = _task(owner, base, project, "Budget", section_id=a["id"])
    owner.patch(
        f"{base}/tasks/{done_task['id']}", json={"version": done_task["version"], "status": "done"}
    )

    archived = owner.post(
        f"{base}/sections/{a['id']}/archive", json={"move_open_tasks_to": b["id"]}
    )
    assert archived.status_code == 200, archived.text
    assert archived.json()["archived"] is True
    tasks = {t["title"]: t for t in owner.get(f"{base}/projects/{project['id']}/tasks").json()}
    assert tasks["Réserver"]["section_id"] == b["id"]
    # Les tâches clôturées restent dans la section archivée (rien n'est perdu).
    assert tasks["Budget"]["section_id"] == a["id"]
    assert (
        owner.patch(
            f"{base}/tasks/{open_task['id']}",
            json={"version": tasks["Réserver"]["version"], "section_id": a["id"]},
        ).status_code
        == 422
    )
    assert {s["id"]: s["archived"] for s in _sections(owner, base, project)} == {
        a["id"]: True,
        b["id"]: False,
    }
    restored = owner.post(f"{base}/sections/{a['id']}/restore").json()
    assert restored["archived"] is False
    history = owner.get(f"{base}/projects/{project['id']}/history").json()
    entry = next(h for h in history if h["action"] == "section.archived")
    assert entry["after"]["tasks_moved"] == 1 and entry["after"]["moved_to"] == "Exécution"


def test_new_statuses_and_validation_by_the_project_owner(make_client):
    owner, space, base, _portfolio, project = _setup(make_client)
    contributor = make_client()
    invite_and_join(owner, contributor, space["id"], "contrib@exemple.com", "contributor")
    task = _task(contributor, base, project, "Valider l'affiche", status="to_qualify")
    assert task["status"] == "to_qualify"
    for status in ("blocked", "awaiting_validation"):
        r = contributor.patch(
            f"{base}/tasks/{task['id']}", json={"version": task["version"], "status": status}
        )
        assert r.status_code == 200, r.text
        task = r.json()
    refused = contributor.patch(
        f"{base}/tasks/{task['id']}", json={"version": task["version"], "status": "done"}
    )
    assert refused.status_code == 403
    assert "validation" in refused.json()["detail"]
    # Renvoyer la tâche en cours reste possible ; le propriétaire peut valider.
    back = contributor.patch(
        f"{base}/tasks/{task['id']}", json={"version": task["version"], "status": "in_progress"}
    ).json()
    sent = contributor.patch(
        f"{base}/tasks/{back['id']}",
        json={"version": back["version"], "status": "awaiting_validation"},
    ).json()
    done = owner.patch(
        f"{base}/tasks/{sent['id']}", json={"version": sent["version"], "status": "done"}
    )
    assert done.status_code == 200 and done.json()["status"] == "done"


def test_priority_start_date_and_postponements_keep_the_first_due_date(make_client):
    owner, _space, base, _portfolio, project = _setup(make_client)
    bad = owner.post(
        f"{base}/projects/{project['id']}/tasks",
        json={"title": "X", "start_date": "2026-12-05", "due_date": "2026-12-01"},
    )
    assert bad.status_code == 422
    task = _task(
        owner,
        base,
        project,
        "Imprimer",
        priority="high",
        start_date="2026-11-20",
        due_date="2026-12-01",
    )
    assert task["priority"] == "high" and task["postpone_count"] == 0
    assert task["original_due_date"] is None

    later = owner.patch(
        f"{base}/tasks/{task['id']}",
        json={
            "version": task["version"],
            "due_date": "2026-12-08",
            "postpone_reason": "Devis tardif",
        },
    ).json()
    assert later["original_due_date"] == "2026-12-01" and later["postpone_count"] == 1
    again = owner.patch(
        f"{base}/tasks/{task['id']}", json={"version": later["version"], "due_date": "2026-12-15"}
    ).json()
    assert again["original_due_date"] == "2026-12-01" and again["postpone_count"] == 2
    # Avancer l'échéance n'est pas un report.
    sooner = owner.patch(
        f"{base}/tasks/{task['id']}", json={"version": again["version"], "due_date": "2026-12-10"}
    ).json()
    assert sooner["postpone_count"] == 2

    history = owner.get(f"{base}/projects/{project['id']}/history").json()
    postponed = [h for h in history if (h["after"] or {}).get("postpone_reason")]
    assert postponed[0]["after"]["postponed_from"] == "2026-12-01"
    assert postponed[0]["after"]["postpone_reason"] == "Devis tardif"


def test_sections_follow_templates_and_export_import(make_client):
    owner, _space, base, portfolio, project = _setup(make_client)
    url = f"{base}/projects/{project['id']}/sections"
    prep = owner.post(url, json={"title": "Préparation"}).json()
    owner.post(url, json={"title": "Bilan"})
    _task(owner, base, project, "Réserver", section_id=prep["id"], priority="urgent")
    template = owner.post(
        f"{base}/templates", json={"project_id": project["id"], "name": "Salon type"}
    ).json()
    assert template["sections"] == ["Préparation", "Bilan"]

    created = owner.post(
        f"{base}/projects",
        json={
            "title": "Salon 2027",
            "portfolio_id": portfolio["id"],
            "template_id": template["id"],
        },
    ).json()
    sections = owner.get(f"{base}/projects/{created['id']}/sections").json()
    assert [s["title"] for s in sections] == ["Préparation", "Bilan"]
    task = owner.get(f"{base}/projects/{created['id']}/tasks").json()[0]
    assert task["section_id"] == sections[0]["id"] and task["priority"] == "urgent"

    report = owner.post(
        "/api/space-imports",
        files={"file": ("e.zip", owner.get(f"{base}/export").content, "application/zip")},
    ).json()
    assert report["counts"]["project_sections"] == 4
    new = f"/api/spaces/{report['space_id']}"
    imported = next(p for p in owner.get(f"{new}/projects").json() if p["title"] == "Salon Agri")
    new_sections = owner.get(f"{new}/projects/{imported['id']}/sections").json()
    new_task = owner.get(f"{new}/projects/{imported['id']}/tasks").json()[0]
    assert new_task["section_id"] == new_sections[0]["id"]
    assert new_sections[0]["id"] != prep["id"]
    templates = owner.get(f"{new}/templates").json()
    assert templates[0]["sections"] == ["Préparation", "Bilan"]
