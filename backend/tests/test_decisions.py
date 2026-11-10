"""Étape F3 (cahier V2, DEC01–DEC05) : registre des décisions et relevés de réunion."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from conftest import create_space, invite_and_join, register
from sqlalchemy import update
from sqlalchemy.orm import Session

from pilot_api.models import Decision

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
    contributor = make_client()
    member = invite_and_join(owner, contributor, space["id"], "moussa@exemple.com", "contributor")
    return owner, contributor, member, space, base, project


COMPLETE = {
    "statement": "Envoyer le devis au client",
    "executor_label": "Mon assistante",
    "criterion": "Devis envoyé et accusé de réception",
}


def test_a_decision_stays_a_draft_until_it_has_an_owner_a_date_and_a_criterion(make_client):
    owner, _contributor, _member, space, base, project = _setup(make_client)
    reader = make_client()
    invite_and_join(owner, reader, space["id"], "lecteur@exemple.com", "reader")
    assert reader.post(f"{base}/decisions", json={"statement": "X"}).status_code == 403

    draft = owner.post(
        f"{base}/decisions",
        json={"statement": "Améliorer la coordination", "executor_label": "L'équipe"},
    ).json()
    assert draft["state"] == "draft"
    assert draft["missing"] == [
        "un responsable nommé (« L'équipe » ne désigne personne)",
        "une échéance datée",
        "un critère observable (ce qui prouvera l'exécution)",
    ]
    refused = owner.post(
        f"{base}/decisions/{draft['id']}/validate", json={"version": draft["version"]}
    )
    assert refused.status_code == 422 and "il manque" in refused.json()["detail"]

    fixed = owner.patch(
        f"{base}/decisions/{draft['id']}",
        json={
            "version": draft["version"],
            "executor_label": "Mon assistante",
            "due_date": day(10),
            "criterion": "Point d'équipe hebdomadaire tenu 4 semaines",
        },
    ).json()
    assert fixed["missing"] == []
    valid = owner.post(
        f"{base}/decisions/{draft['id']}/validate", json={"version": fixed["version"]}
    )
    assert valid.status_code == 200 and valid.json()["state"] == "open"

    direct = owner.post(
        f"{base}/decisions",
        json={**COMPLETE, "due_date": day(5), "project_id": project["id"], "validate_now": True},
    ).json()
    assert direct["state"] == "open" and direct["project"]["name"] == "Salon Agri"
    # Une décision validée ne peut pas perdre son critère.
    assert (
        owner.patch(
            f"{base}/decisions/{direct['id']}", json={"version": direct["version"], "criterion": ""}
        ).status_code
        == 422
    )


def test_the_executor_accepts_and_orphans_are_flagged_at_thirty_days(make_client, engine):
    owner, contributor, member, _space, base, _project = _setup(make_client)
    d = owner.post(
        f"{base}/decisions",
        json={
            **COMPLETE,
            "executor_label": None,
            "executor_member_id": member["id"],
            "due_date": day(40),
        },
    ).json()
    assert d["executor_accepted"] is False and d["orphan_days"] == 0
    assert (
        owner.post(f"{base}/decisions/{d['id']}/accept", json={"version": d["version"]}).status_code
        == 403
    )
    with Session(engine) as db:
        db.execute(
            update(Decision)
            .where(Decision.id == d["id"])
            .values(created_at=datetime.now(UTC) - timedelta(days=31))
        )
        db.commit()
    alerts = owner.get(f"{base}/alerts").json()["items"]
    orphan = [a for a in alerts if a["rule"] == "orphan_subject"]
    assert orphan and "31 jours" in orphan[0]["detail"]

    accepted = contributor.post(
        f"{base}/decisions/{d['id']}/accept", json={"version": d["version"]}
    )
    assert accepted.status_code == 200
    body = accepted.json()
    assert body["executor_accepted"] is True and body["orphan_days"] is None and body["is_executor"]
    # Changer de porteur : il doit accepter à son tour ; l'ancienneté n'est pas remise à zéro.
    changed = owner.patch(
        f"{base}/decisions/{d['id']}",
        json={"version": body["version"], "executor_member_id": None, "executor_label": "Awa"},
    ).json()
    assert changed["executor_accepted"] is True  # nom libre : désignation déclarée


def test_mid_term_reminder_once_and_overdue_decisions_to_escalate(make_client, engine):
    owner, contributor, member, _space, base, _project = _setup(make_client)
    d = owner.post(
        f"{base}/decisions",
        json={
            **COMPLETE,
            "executor_label": None,
            "executor_member_id": member["id"],
            "due_date": day(4),
            "validate_now": True,
        },
    ).json()
    with Session(engine) as db:
        db.execute(
            update(Decision)
            .where(Decision.id == d["id"])
            .values(validated_at=datetime.now(UTC) - timedelta(days=6))
        )
        db.commit()
    rules = [a["rule"] for a in contributor.get(f"{base}/alerts").json()["items"]]
    assert rules.count("decision_reminder") == 1
    with Session(engine) as db:
        assert db.get(Decision, d["id"]).reminded_on is not None

    late = owner.post(
        f"{base}/decisions",
        json={**COMPLETE, "statement": "Signer le bail", "due_date": day(-1), "validate_now": True},
    ).json()
    assert late["late"] is True
    overdue = [
        a
        for a in owner.get(f"{base}/alerts").json()["items"]
        if a["rule"] == "overdue" and a["title"].startswith("⚖")
    ]
    assert overdue and "escalader" in overdue[0]["detail"]


def test_closing_needs_proof_or_a_formal_cancellation_and_tasks_keep_the_link(make_client):
    owner, _contributor, member, _space, base, project = _setup(make_client)
    draft = owner.post(f"{base}/decisions", json={"statement": "Choisir le traiteur"}).json()
    early = owner.post(
        f"{base}/decisions/{draft['id']}/close",
        json={"version": draft["version"], "state": "done", "note": "fait"},
    )
    assert early.status_code == 400
    d = owner.post(
        f"{base}/decisions",
        json={
            **COMPLETE,
            "executor_label": None,
            "executor_member_id": member["id"],
            "due_date": day(7),
            "project_id": project["id"],
            "validate_now": True,
        },
    ).json()
    with_task = owner.post(f"{base}/decisions/{d['id']}/tasks", json={"version": d["version"]})
    assert with_task.status_code == 201, with_task.text
    task = with_task.json()["tasks"][0]
    assert task["title"] == "Envoyer le devis au client"
    tasks = owner.get(f"{base}/projects/{project['id']}/tasks").json()
    assert tasks[0]["assignee"]["member_id"] == member["id"] and tasks[0]["due_date"] == day(7)

    current = with_task.json()
    done = owner.post(
        f"{base}/decisions/{d['id']}/close",
        json={
            "version": current["version"],
            "state": "done",
            "note": "Devis envoyé le 12, AR reçu",
        },
    ).json()
    assert done["state"] == "done" and done["proof"].startswith("Devis envoyé")
    reopened = owner.post(
        f"{base}/decisions/{d['id']}/reopen", json={"version": done["version"]}
    ).json()
    assert reopened["state"] == "open" and reopened["proof"] is None
    cancelled = owner.post(
        f"{base}/decisions/{d['id']}/close",
        json={"version": reopened["version"], "state": "cancelled", "note": "Client parti"},
    ).json()
    assert cancelled["state"] == "cancelled" and cancelled["cancel_reason"] == "Client parti"
    history = [h["action"] for h in owner.get(f"{base}/projects/{project['id']}/history").json()]
    assert {
        "decision.created",
        "decision.task_created",
        "decision.done",
        "decision.cancelled",
    } <= set(history)


def test_private_decisions_stay_with_their_actors(make_client):
    owner, contributor, member, space, base, _project = _setup(make_client)
    other = make_client()
    invite_and_join(owner, other, space["id"], "awa@exemple.com", "contributor")
    owner.post(
        f"{base}/decisions",
        json={
            **COMPLETE,
            "statement": "Entretien individuel : objectifs",
            "private": True,
            "executor_label": None,
            "executor_member_id": member["id"],
        },
    )
    assert [d["statement"] for d in contributor.get(f"{base}/decisions").json()] == [
        "Entretien individuel : objectifs"
    ]
    assert other.get(f"{base}/decisions").json() == []


def test_meeting_minutes_must_be_sent_within_24_hours(make_client):
    owner, _contributor, _member, _space, base, _project = _setup(make_client)
    ended = (datetime.now(UTC) - timedelta(hours=30)).isoformat()
    meeting = owner.post(
        f"{base}/meetings", json={"title": "Comité du lundi", "ended_at": ended}
    ).json()
    assert meeting["minutes_state"] == "to_write" and meeting["minutes_late"] is True
    owner.post(
        f"{base}/decisions",
        json={**COMPLETE, "meeting_id": meeting["id"]},
    )
    alerts = owner.get(f"{base}/alerts").json()["items"]
    assert any(a["rule"] == "minutes_overdue" and a["title"] == "Comité du lundi" for a in alerts)

    sent = owner.patch(
        f"{base}/meetings/{meeting['id']}",
        json={
            "version": meeting["version"],
            "minutes_state": "sent",
            "minutes_channel": "E-mail",
            "minutes_recipients": "Comité de direction",
        },
    ).json()
    assert sent["minutes_state"] == "sent" and sent["minutes_late"] is False
    assert sent["minutes_sent_at"] is not None and sent["decisions_count"] == 1
    from_meeting = owner.get(f"{base}/decisions?meeting_id={meeting['id']}").json()
    assert [d["meeting"]["name"] for d in from_meeting] == ["Comité du lundi"]


def test_decisions_and_meetings_survive_export_and_import(make_client):
    owner, _contributor, _member, _space, base, project = _setup(make_client)
    meeting = owner.post(
        f"{base}/meetings", json={"title": "Comité", "ended_at": datetime.now(UTC).isoformat()}
    ).json()
    d = owner.post(
        f"{base}/decisions",
        json={
            **COMPLETE,
            "due_date": day(5),
            "project_id": project["id"],
            "meeting_id": meeting["id"],
            "validate_now": True,
        },
    ).json()
    owner.post(f"{base}/decisions/{d['id']}/tasks", json={"version": d["version"]})
    report = owner.post(
        "/api/space-imports",
        files={"file": ("e.zip", owner.get(f"{base}/export").content, "application/zip")},
    ).json()
    assert report["counts"]["decisions"] == 1 and report["counts"]["meetings"] == 1
    new = f"/api/spaces/{report['space_id']}"
    imported = owner.get(f"{new}/decisions").json()[0]
    assert imported["meeting"]["name"] == "Comité" and imported["project"]["name"] == "Salon Agri"
    assert [t["title"] for t in imported["tasks"]] == ["Envoyer le devis au client"]
