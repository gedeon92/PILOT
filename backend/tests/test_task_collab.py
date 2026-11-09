"""Tâches complètes (lot A) : sous-tâches, commentaires et mentions, abonnés, dépendances,
notifications, journal, export/import. Rien de ce qui existait ne change de comportement."""

from conftest import create_space, invite_and_join, register


def _setup(make_client):
    owner = make_client()
    register(owner, "proprio@exemple.com", "Aïcha Ndiaye")
    space = create_space(owner, "Groupe Horizon")
    base = f"/api/spaces/{space['id']}"
    portfolio = owner.post(f"{base}/portfolios", json={"name": "Événements"}).json()
    project = owner.post(
        f"{base}/projects", json={"title": "Salon Agri", "portfolio_id": portfolio["id"]}
    ).json()
    return owner, space, base, project


def _task(client, base, project, title, **fields):
    response = client.post(
        f"{base}/projects/{project['id']}/tasks", json={"title": title, **fields}
    )
    assert response.status_code == 201, response.text
    return response.json()


def _alerts(client, base, rule):
    return [a for a in client.get(f"{base}/alerts").json()["items"] if a["rule"] == rule]


def test_subtasks_are_counted_and_one_level_only(make_client):
    owner, _, base, project = _setup(make_client)
    parent = _task(owner, base, project, "Préparer la logistique")

    first = owner.post(f"{base}/tasks/{parent['id']}/subtasks", json={"title": "Réserver la salle"})
    assert first.status_code == 201, first.text
    sub = first.json()
    assert sub["parent_id"] == parent["id"] and sub["project_id"] == project["id"]
    owner.post(f"{base}/tasks/{parent['id']}/subtasks", json={"title": "Commander les chaises"})
    owner.patch(f"{base}/tasks/{sub['id']}", json={"version": sub["version"], "status": "done"})

    listed = {t["title"]: t for t in owner.get(f"{base}/projects/{project['id']}/tasks").json()}
    assert listed["Préparer la logistique"]["subtasks_total"] == 2
    assert listed["Préparer la logistique"]["subtasks_done"] == 1

    detail = owner.get(f"{base}/tasks/{parent['id']}").json()
    assert [s["title"] for s in detail["subtasks"]] == [
        "Réserver la salle",
        "Commander les chaises",
    ]
    assert detail["project_title"] == "Salon Agri"
    sub_detail = owner.get(f"{base}/tasks/{sub['id']}").json()
    assert sub_detail["parent"]["title"] == "Préparer la logistique"

    # Pas de sous-sous-tâche.
    deeper = owner.post(f"{base}/tasks/{sub['id']}/subtasks", json={"title": "Trop loin"})
    assert deeper.status_code == 422


def test_comments_mentions_and_followers_are_notified(make_client):
    owner, space, base, project = _setup(make_client)
    moussa_client, fatou_client = make_client(), make_client()
    moussa = invite_and_join(owner, moussa_client, space["id"], "moussa@exemple.com", "contributor")
    invite_and_join(owner, fatou_client, space["id"], "fatou@exemple.com", "reader")

    task = _task(owner, base, project, "Envoyer les invitations", assignee_member_id=moussa["id"])
    # Moussa, responsable, suit la tâche et a été prévenu qu'on la lui a confiée.
    assert any(
        "vous a confié" in a["detail"] for a in _alerts(moussa_client, base, "task_activity")
    )

    # Fatou (lectrice) peut suivre la tâche, mais pas commenter.
    assert fatou_client.post(f"{base}/tasks/{task['id']}/follow").json()["following"] is True
    refused = fatou_client.post(f"{base}/tasks/{task['id']}/comments", json={"body": "Bonjour"})
    assert refused.status_code == 403

    detail = owner.post(
        f"{base}/tasks/{task['id']}/comments",
        json={"body": "@Moussa peux-tu relancer l'imprimeur ?", "mentions": [moussa["id"]]},
    ).json()
    assert detail["comments"][0]["mentions"] == [
        {"member_id": moussa["id"], "name": "Utilisateur Test"}
    ]
    assert detail["task"]["comments_count"] == 1

    mention = _alerts(moussa_client, base, "mention")
    assert len(mention) == 1 and "vous a mentionné" in mention[0]["detail"]
    assert mention[0]["target_id"] == task["id"] and mention[0]["target_type"] == "task"
    activity = _alerts(fatou_client, base, "task_activity")
    assert len(activity) == 1 and "a commenté" in activity[0]["detail"]
    # L'auteur n'est jamais prévenu de sa propre action.
    assert _alerts(owner, base, "task_activity") == []

    # Un second commentaire met à jour la même alerte (pas d'avalanche) et la remet en non lue.
    fatou_client.post(f"{base}/alerts/{activity[0]['id']}/read")
    owner.post(f"{base}/tasks/{task['id']}/comments", json={"body": "Merci d'avance"})
    again = _alerts(fatou_client, base, "task_activity")
    assert len(again) == 1 and again[0]["read"] is False and "Merci" in again[0]["detail"]

    # Se désabonner arrête les notifications.
    assert fatou_client.delete(f"{base}/tasks/{task['id']}/follow").json()["following"] is False


def test_comment_removal_is_limited_to_author_or_owner(make_client):
    owner, space, base, project = _setup(make_client)
    moussa_client = make_client()
    invite_and_join(owner, moussa_client, space["id"], "moussa@exemple.com", "contributor")
    task = _task(owner, base, project, "Réserver la salle")
    comment = owner.post(f"{base}/tasks/{task['id']}/comments", json={"body": "Devis reçu"}).json()[
        "comments"
    ][0]
    assert comment["can_delete"] is True

    url = f"{base}/tasks/{task['id']}/comments/{comment['id']}"
    assert moussa_client.delete(url).status_code == 403
    assert owner.delete(url).status_code == 204
    assert owner.get(f"{base}/tasks/{task['id']}").json()["comments"] == []

    actions = [h["action"] for h in owner.get(f"{base}/projects/{project['id']}/history").json()]
    assert "task.commented" in actions and "task.comment_deleted" in actions


def test_dependencies_wait_refuse_loops_and_announce_unblocking(make_client):
    owner, space, base, project = _setup(make_client)
    moussa_client = make_client()
    moussa = invite_and_join(owner, moussa_client, space["id"], "moussa@exemple.com", "contributor")
    venue = _task(owner, base, project, "Signer le lieu")
    invitations = _task(
        owner, base, project, "Envoyer les invitations", assignee_member_id=moussa["id"]
    )

    detail = owner.post(
        f"{base}/tasks/{invitations['id']}/dependencies", json={"depends_on_id": venue["id"]}
    ).json()
    assert [d["title"] for d in detail["depends_on"]] == ["Signer le lieu"]
    assert detail["task"]["waiting_on"] == 1
    assert [b["title"] for b in owner.get(f"{base}/tasks/{venue['id']}").json()["blocking"]] == [
        "Envoyer les invitations"
    ]

    loop = owner.post(
        f"{base}/tasks/{venue['id']}/dependencies", json={"depends_on_id": invitations["id"]}
    )
    assert loop.status_code == 422
    itself = owner.post(
        f"{base}/tasks/{venue['id']}/dependencies", json={"depends_on_id": venue["id"]}
    )
    assert itself.status_code == 422

    # Le lieu signé : la tâche en attente n'attend plus rien, son responsable est prévenu.
    owner.patch(f"{base}/tasks/{venue['id']}", json={"version": venue["version"], "status": "done"})
    listed = {t["title"]: t for t in owner.get(f"{base}/projects/{project['id']}/tasks").json()}
    assert listed["Envoyer les invitations"]["waiting_on"] == 0
    assert any("peut avancer" in a["detail"] for a in _alerts(moussa_client, base, "task_activity"))

    removed = owner.delete(f"{base}/tasks/{invitations['id']}/dependencies/{venue['id']}").json()
    assert removed["depends_on"] == []


def test_changes_notify_followers_and_readers_cannot_modify(make_client):
    owner, space, base, project = _setup(make_client)
    moussa_client, fatou_client = make_client(), make_client()
    invite_and_join(owner, moussa_client, space["id"], "moussa@exemple.com", "contributor")
    invite_and_join(owner, fatou_client, space["id"], "fatou@exemple.com", "reader")
    task = _task(owner, base, project, "Imprimer les badges")
    moussa_client.post(f"{base}/tasks/{task['id']}/follow")

    owner.patch(
        f"{base}/tasks/{task['id']}",
        json={"version": task["version"], "status": "in_progress", "due_date": "2026-12-01"},
    )
    detail = _alerts(moussa_client, base, "task_activity")[0]["detail"]
    assert "En cours" in detail and "1 déc." in detail

    subtask = fatou_client.post(f"{base}/tasks/{task['id']}/subtasks", json={"title": "Non"})
    dependency = fatou_client.post(
        f"{base}/tasks/{task['id']}/dependencies", json={"depends_on_id": task["id"]}
    )
    assert subtask.status_code == 403 and dependency.status_code == 403


def test_subtasks_comments_and_dependencies_survive_export_and_import(make_client):
    owner, _, base, project = _setup(make_client)
    parent = _task(owner, base, project, "Logistique")
    owner.post(f"{base}/tasks/{parent['id']}/subtasks", json={"title": "Réserver la salle"})
    later = _task(owner, base, project, "Accueillir les invités")
    owner.post(f"{base}/tasks/{later['id']}/dependencies", json={"depends_on_id": parent["id"]})
    owner.post(f"{base}/tasks/{parent['id']}/comments", json={"body": "Devis à comparer"})

    report = owner.post(
        "/api/space-imports",
        files={"file": ("export.zip", owner.get(f"{base}/export").content, "application/zip")},
    ).json()
    new = f"/api/spaces/{report['space_id']}"
    tasks = {t["title"]: t for t in owner.get(f"{new}/tasks").json()}
    assert tasks["Réserver la salle"]["parent_id"] == tasks["Logistique"]["id"]
    assert tasks["Logistique"]["subtasks_total"] == 1
    assert tasks["Logistique"]["comments_count"] == 1
    detail = owner.get(f"{new}/tasks/{tasks['Accueillir les invités']['id']}").json()
    assert [d["title"] for d in detail["depends_on"]] == ["Logistique"]
    comment = owner.get(f"{new}/tasks/{tasks['Logistique']['id']}").json()["comments"][0]
    assert comment["author_name"] == "Aïcha Ndiaye" and comment["body"] == "Devis à comparer"


def test_import_refuses_a_dependency_loop_hidden_in_a_tampered_export(make_client):
    """Audit F7 : un fichier modifié ne peut pas introduire A → B → C → A."""
    import io
    import json
    import zipfile

    from pilot_api.portability import DATA_NAME

    owner, _, base, project = _setup(make_client)
    a = _task(owner, base, project, "A")
    b = _task(owner, base, project, "B")
    c = _task(owner, base, project, "C")
    owner.post(f"{base}/tasks/{a['id']}/dependencies", json={"depends_on_id": b["id"]})
    owner.post(f"{base}/tasks/{b['id']}/dependencies", json={"depends_on_id": c["id"]})
    archive = zipfile.ZipFile(io.BytesIO(owner.get(f"{base}/export").content))
    data = json.loads(archive.read(DATA_NAME))
    data["task_dependencies"].append(
        {**data["task_dependencies"][0], "task_id": c["id"], "depends_on_id": a["id"]}
    )
    rebuilt = io.BytesIO()
    with zipfile.ZipFile(rebuilt, "w") as out:
        for name in archive.namelist():
            out.writestr(name, archive.read(name) if name != DATA_NAME else json.dumps(data))

    report = owner.post(
        "/api/space-imports", files={"file": ("e.zip", rebuilt.getvalue(), "application/zip")}
    ).json()
    tasks = {t["title"]: t for t in owner.get(f"/api/spaces/{report['space_id']}/tasks").json()}
    assert tasks["C"]["waiting_on"] == 0  # la boucle C → A a été écartée
    assert tasks["A"]["waiting_on"] == 1 and tasks["B"]["waiting_on"] == 1
