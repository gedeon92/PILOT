"""Suppression définitive de projets (propriétaire, mot « SUPPRIMER »)."""

from datetime import UTC, datetime

from conftest import create_space, invite_and_join, register
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from pilot_api.models import AuditLog, Decision, Meeting, StoredFile, Task


def test_owner_purges_test_projects_and_everything_inside(make_client, engine):
    owner = make_client()
    register(owner, "proprio@exemple.com")
    space = create_space(owner)
    b = f"/api/spaces/{space['id']}"
    contributor = make_client()
    invite_and_join(owner, contributor, space["id"], "contrib@exemple.com", "contributor")
    pf = owner.post(f"{b}/portfolios", json={"name": "Essais"}).json()
    trial = owner.post(
        f"{b}/projects", json={"title": "Projet d'essai", "portfolio_id": pf["id"]}
    ).json()
    keep = owner.post(
        f"{b}/projects", json={"title": "Vrai projet", "portfolio_id": pf["id"]}
    ).json()

    section = owner.post(
        f"{b}/projects/{trial['id']}/sections", json={"title": "Préparation"}
    ).json()
    task = owner.post(
        f"{b}/projects/{trial['id']}/tasks", json={"title": "Réserver", "section_id": section["id"]}
    ).json()
    owner.post(f"{b}/tasks/{task['id']}/subtasks", json={"title": "Devis"})
    owner.post(f"{b}/tasks/{task['id']}/comments", json={"body": "Note"})
    owner.post(
        f"{b}/tasks/{task['id']}/documents",
        files={"file": ("devis.pdf", b"%PDF devis", "application/pdf")},
    )
    owner.post(
        f"{b}/projects/{trial['id']}/milestones",
        json={"title": "Salle", "due_date": "2027-01-10", "task_ids": [task["id"]]},
    )
    meeting = owner.post(
        f"{b}/meetings",
        json={
            "title": "Comité",
            "ended_at": datetime.now(UTC).isoformat(),
            "project_id": trial["id"],
        },
    ).json()
    owner.post(f"{b}/decisions", json={"statement": "Choisir la salle", "project_id": trial["id"]})
    owner.post(f"{b}/projects/{keep['id']}/links", json={"project_id": trial["id"]})
    kept_task = owner.post(f"{b}/projects/{keep['id']}/tasks", json={"title": "À garder"}).json()

    url = f"{b}/projects/purge"
    body = {"project_ids": [trial["id"]], "confirm": "SUPPRIMER"}
    assert contributor.post(url, json=body).status_code == 403
    assert owner.post(url, json={**body, "confirm": "oui"}).status_code == 422

    done = owner.post(url, json=body)
    assert done.status_code == 200, done.text
    assert done.json() == {"deleted": 1, "titles": ["Projet d'essai"]}

    assert owner.get(f"{b}/projects/{trial['id']}").status_code == 404
    assert [p["title"] for p in owner.get(f"{b}/projects").json()] == ["Vrai projet"]
    assert owner.get(f"{b}/projects/{keep['id']}/links").json() == []
    assert [t["title"] for t in owner.get(f"{b}/projects/{keep['id']}/tasks").json()] == [
        "À garder"
    ]
    assert owner.get(f"{b}/tasks/{kept_task['id']}").status_code == 200
    assert owner.get(f"{b}/decisions").json() == []
    meetings = owner.get(f"{b}/meetings").json()
    assert meetings[0]["id"] == meeting["id"] and meetings[0]["project"] is None
    assert owner.get(f"{b}/documents").json() == []

    with Session(engine) as db:
        assert db.scalar(select(func.count(Task.id)).where(Task.project_id == trial["id"])) == 0
        assert db.scalar(select(func.count(Decision.id))) == 0
        assert db.scalar(select(func.count(StoredFile.key))) == 0
        assert db.get(Meeting, meeting["id"]) is not None
        logs = db.scalars(select(AuditLog).where(AuditLog.target_id == str(trial["id"]))).all()
        assert logs == []
        summary = db.scalars(select(AuditLog).where(AuditLog.action == "projects.purged")).all()
        assert len(summary) == 1 and summary[0].after["titles"] == ["Projet d'essai"]
