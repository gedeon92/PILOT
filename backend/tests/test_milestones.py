"""Étape F2 (cahier V2, TCH04 et CAP01) : jalons, reports, revue de cadrage, risque."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from conftest import create_space, invite_and_join, register

DAKAR = ZoneInfo("Africa/Dakar")


def day(offset: int) -> str:
    return (datetime.now(DAKAR).date() + timedelta(days=offset)).isoformat()


def _setup(make_client):
    owner = make_client()
    register(owner, "proprio@exemple.com", "Aïcha Ndiaye")
    space = create_space(owner, "Groupe Horizon")
    base = f"/api/spaces/{space['id']}"
    portfolio = owner.post(f"{base}/portfolios", json={"name": "Événements"}).json()
    project = owner.post(
        f"{base}/projects",
        json={
            "title": "Salon Agri",
            "portfolio_id": portfolio["id"],
            "next_step": "Avancer",
            "owner_label": "Équipe",
        },
    ).json()
    return owner, space, base, portfolio, project


def _task(client, base, project, title, **fields):
    response = client.post(
        f"{base}/projects/{project['id']}/tasks", json={"title": title, **fields}
    )
    assert response.status_code == 201, response.text
    return response.json()


def _milestone(client, base, project, **fields):
    body = {"title": "Salle confirmée", "due_date": day(30), **fields}
    response = client.post(f"{base}/projects/{project['id']}/milestones", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def test_a_milestone_has_an_owner_a_date_a_criterion_and_linked_tasks(make_client):
    owner, space, base, portfolio, project = _setup(make_client)
    reader = make_client()
    invite_and_join(owner, reader, space["id"], "lecteur@exemple.com", "reader")
    task = _task(owner, base, project, "Réserver la salle")
    other = owner.post(
        f"{base}/projects", json={"title": "Autre", "portfolio_id": portfolio["id"]}
    ).json()
    foreign = _task(owner, base, other, "Ailleurs")

    m = _milestone(
        owner,
        base,
        project,
        criterion="Contrat de location signé",
        owner_label="Mon assistante",
        critical=True,
        task_ids=[task["id"]],
    )
    assert m["state"] == "planned" and m["critical"] is True
    assert m["owner"]["name"] == "Mon assistante" and m["criterion"] == "Contrat de location signé"
    assert [t["title"] for t in m["tasks"]] == ["Réserver la salle"]
    assert m["postpone_count"] == 0 and m["reframe_needed"] is False

    bad = owner.post(
        f"{base}/projects/{project['id']}/milestones",
        json={"title": "X", "due_date": day(5), "task_ids": [foreign["id"]]},
    )
    assert bad.status_code == 422
    assert (
        reader.post(
            f"{base}/projects/{project['id']}/milestones", json={"title": "X", "due_date": day(5)}
        ).status_code
        == 403
    )
    assert [
        x["title"] for x in reader.get(f"{base}/projects/{project['id']}/milestones").json()
    ] == ["Salle confirmée"]


def test_two_postponements_then_a_reframing_review_is_required(make_client):
    owner, _space, base, _portfolio, project = _setup(make_client)
    m = _milestone(owner, base, project, due_date=day(10))
    url = f"{base}/milestones/{m['id']}"

    no_reason = owner.patch(url, json={"version": m["version"], "due_date": day(15)})
    assert no_reason.status_code == 422
    first = owner.patch(
        url, json={"version": m["version"], "due_date": day(15), "postpone_reason": "Devis"}
    ).json()
    assert first["postpone_count"] == 1 and first["original_due_date"] == day(10)
    second = owner.patch(
        url, json={"version": first["version"], "due_date": day(20), "postpone_reason": "Salle"}
    ).json()
    assert second["postpone_count"] == 2 and second["reframe_needed"] is True
    # Le deuxième report prévient les responsables : revue de cadrage attendue.
    alerts = owner.get(f"{base}/alerts").json()["items"]
    assert any(a["rule"] == "milestone_reframe" for a in alerts)

    third = owner.patch(
        url, json={"version": second["version"], "due_date": day(25), "postpone_reason": "Encore"}
    )
    assert third.status_code == 422
    assert "revue de cadrage" in third.json()["detail"]
    reviewed = owner.patch(
        url,
        json={
            "version": second["version"],
            "due_date": day(25),
            "postpone_reason": "Encore",
            "reframe_note": "Périmètre réduit : une seule salle, date tenable",
        },
    ).json()
    assert reviewed["postpone_count"] == 3 and reviewed["original_due_date"] == day(10)
    assert reviewed["reframe_note"].startswith("Périmètre réduit")
    # Avancer la date n'est pas un report.
    sooner = owner.patch(url, json={"version": reviewed["version"], "due_date": day(22)}).json()
    assert sooner["postpone_count"] == 3

    history = owner.get(f"{base}/projects/{project['id']}/history").json()
    postponed = [h for h in history if h["action"] == "milestone.postponed"]
    assert len(postponed) == 3
    assert postponed[-1]["after"]["postpone_reason"] == "Devis"


def test_risk_within_three_weeks_and_late_milestones_raise_alerts(make_client):
    owner, _space, base, _portfolio, project = _setup(make_client)
    blocked = _task(owner, base, project, "Commander les badges", status="blocked")
    soon = _milestone(
        owner, base, project, title="Badges prêts", due_date=day(10), task_ids=[blocked["id"]]
    )
    assert soon["at_risk"] is True
    assert "1 tâche(s) liée(s) bloquée(s)" in soon["risk_reasons"]
    # Au-delà de trois semaines, pas encore d'alerte précoce.
    far = _milestone(
        owner, base, project, title="Bilan", due_date=day(40), task_ids=[blocked["id"]]
    )
    assert far["at_risk"] is False
    late = _milestone(owner, base, project, title="Programme publié", due_date=day(-2))
    assert late["late"] is True

    rules = {(a["rule"], a["title"]) for a in owner.get(f"{base}/alerts").json()["items"]}
    assert ("milestone_at_risk", "◆ Badges prêts · Salon Agri") in rules
    assert ("overdue", "◆ Programme publié · Salon Agri") in rules
    upcoming = owner.get(f"{base}/milestones").json()
    assert [m["title"] for m in upcoming] == ["Programme publié", "Badges prêts"]


def test_closing_needs_a_reason_when_missed_and_can_be_reopened(make_client):
    owner, _space, base, _portfolio, project = _setup(make_client)
    m = _milestone(owner, base, project)
    url = f"{base}/milestones/{m['id']}"
    assert (
        owner.post(f"{url}/close", json={"version": m["version"], "state": "missed"}).status_code
        == 422
    )
    reached = owner.post(
        f"{url}/close",
        json={"version": m["version"], "state": "reached", "note": "Contrat signé le 3"},
    ).json()
    assert reached["state"] == "reached" and reached["close_note"] == "Contrat signé le 3"
    assert reached["at_risk"] is False and reached["late"] is False
    locked = owner.patch(url, json={"version": reached["version"], "due_date": day(60)})
    assert locked.status_code == 400
    reopened = owner.post(f"{url}/reopen", json={"version": reached["version"]}).json()
    assert reopened["state"] == "planned" and reopened["close_note"] is None
    actions = [h["action"] for h in owner.get(f"{base}/projects/{project['id']}/history").json()]
    assert "milestone.reached" in actions and "milestone.reopened" in actions


def test_milestones_follow_templates_and_export_import(make_client):
    owner, _space, base, portfolio, project = _setup(make_client)
    owner.patch(
        f"{base}/projects/{project['id']}",
        json={"version": project["version"], "start_date": "2026-12-01"},
    )
    task = _task(owner, base, project, "Réserver", due_date="2026-12-05")
    _milestone(
        owner, base, project, title="Salle confirmée", due_date="2026-12-10", task_ids=[task["id"]]
    )
    template = owner.post(
        f"{base}/templates", json={"project_id": project["id"], "name": "Salon type"}
    ).json()
    assert template["milestones"] == [
        {"title": "Salle confirmée", "offset_days": 9, "critical": False}
    ]
    created = owner.post(
        f"{base}/projects",
        json={
            "title": "Salon 2027",
            "portfolio_id": portfolio["id"],
            "template_id": template["id"],
            "start_date": "2027-03-01",
        },
    ).json()
    copied = owner.get(f"{base}/projects/{created['id']}/milestones").json()
    assert [(m["title"], m["due_date"]) for m in copied] == [("Salle confirmée", "2027-03-10")]
    assert [t["title"] for t in copied[0]["tasks"]] == ["Réserver"]

    report = owner.post(
        "/api/space-imports",
        files={"file": ("e.zip", owner.get(f"{base}/export").content, "application/zip")},
    ).json()
    assert report["counts"]["milestones"] == 2
    new = f"/api/spaces/{report['space_id']}"
    imported = next(p for p in owner.get(f"{new}/projects").json() if p["title"] == "Salon Agri")
    milestones = owner.get(f"{new}/projects/{imported['id']}/milestones").json()
    assert [t["title"] for t in milestones[0]["tasks"]] == ["Réserver"]
    assert owner.get(f"{new}/templates").json()[0]["milestones"][0]["offset_days"] == 9
