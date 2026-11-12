"""Pilotage (étape F6) : indicateurs, charge et capacité, contrôles d'événement, dossier
d'arbitrage, rencontres et relations."""

from datetime import UTC, date, datetime, timedelta

from conftest import create_space, invite_and_join, register

from pilot_api.routers.pilotage import add_workdays


def _setup(make_client):
    owner = make_client()
    register(owner, "proprio@exemple.com", "Raissa Proprio")
    space = create_space(owner)
    b = f"/api/spaces/{space['id']}"
    contributor = make_client()
    invite_and_join(owner, contributor, space["id"], "contrib@exemple.com", "contributor")
    reader = make_client()
    invite_and_join(owner, reader, space["id"], "lecteur@exemple.com", "reader")
    pf = owner.post(f"{b}/portfolios", json={"name": "Général"}).json()
    project = owner.post(f"{b}/projects", json={"title": "Atlas", "portfolio_id": pf["id"]}).json()
    members = {m["email"]: m for m in owner.get(f"{b}/members").json()}
    return owner, contributor, reader, b, pf, project, members


def _today() -> date:
    return datetime.now(UTC).date()


def test_add_workdays_skips_weekends():
    assert add_workdays(date(2026, 11, 13), 5) == date(2026, 11, 20)  # vendredi → vendredi


def test_indicators_are_transparent(make_client):
    owner, contributor, reader, b, _pf, project, members = _setup(make_client)
    today = _today()
    me = members["proprio@exemple.com"]["id"]
    owner.post(
        f"{b}/decisions",
        json={
            "statement": "Choisir le traiteur",
            "executor_member_id": me,
            "due_date": today.isoformat(),
            "criterion": "Contrat signé",
        },
    )
    owner.post(f"{b}/decisions", json={"statement": "Améliorer la coordination"})

    on_time = owner.post(
        f"{b}/projects/{project['id']}/milestones",
        json={"title": "Salle", "due_date": today.isoformat()},
    ).json()
    owner.post(
        f"{b}/milestones/{on_time['id']}/close",
        json={"version": on_time["version"], "state": "reached"},
    )
    late = owner.post(
        f"{b}/projects/{project['id']}/milestones",
        json={"title": "Programme", "due_date": (today - timedelta(days=5)).isoformat()},
    ).json()
    moved = owner.patch(
        f"{b}/milestones/{late['id']}",
        json={
            "version": late["version"],
            "due_date": (today + timedelta(days=10)).isoformat(),
            "postpone_reason": "Intervenant absent",
        },
    ).json()
    owner.post(
        f"{b}/milestones/{late['id']}/close", json={"version": moved["version"], "state": "reached"}
    )
    dropped = owner.post(
        f"{b}/projects/{project['id']}/milestones",
        json={"title": "Annulé", "due_date": (today - timedelta(days=1)).isoformat()},
    ).json()
    owner.post(
        f"{b}/milestones/{dropped['id']}/close",
        json={"version": dropped["version"], "state": "cancelled", "note": "Hors périmètre"},
    )

    data = owner.get(f"{b}/indicators").json()
    by_key = {i["key"]: i for i in data["indicators"]}
    assert data["scope"] == "Tout l'espace" and data["computed_at"]
    complete = by_key["decisions_complete"]
    assert (complete["numerator"], complete["denominator"], complete["value"]) == (1, 2, 50.0)
    assert complete["status"] == "below" and complete["target"] == 100
    # Le jalon reporté puis atteint n'est pas « à l'heure » ; l'annulé est compté à part.
    milestones = by_key["milestones_on_time"]
    assert (milestones["numerator"], milestones["denominator"], milestones["cancelled"]) == (
        1,
        2,
        1,
    )
    # Aucun cas : non calculable, pas 100 %.
    assert by_key["minutes_24h"]["status"] == "na" and by_key["minutes_24h"]["value"] is None
    assert by_key["strategic_time"]["na_reason"].startswith("Non mesuré")
    assert by_key["monthly_report"]["status"] == "na"
    assert by_key["orphan_subjects"]["value"] == 0 and by_key["orphan_subjects"]["status"] == "ok"

    # Cibles : propriétaire seulement.
    targets = {"targets": {"decisions_complete": 50}}
    assert contributor.put(f"{b}/indicators/targets", json=targets).status_code == 403
    changed = owner.put(f"{b}/indicators/targets", json=targets).json()
    adjusted = next(i for i in changed["indicators"] if i["key"] == "decisions_complete")
    assert adjusted["target"] == 50 and adjusted["status"] == "ok"
    assert reader.get(f"{b}/indicators").json()["scope"].startswith("Projets et décisions")


def test_capacity_needs_estimates_and_declared_capacity(make_client):
    owner, contributor, reader, b, _pf, project, members = _setup(make_client)
    today = _today()
    contrib = members["contrib@exemple.com"]["id"]
    for title, hours in (("Devis", 30), ("Salle", 15), ("Badge", None)):
        body = {"title": title, "assignee_member_id": contrib, "due_date": today.isoformat()}
        if hours:
            body["estimate_hours"] = hours
        r = owner.post(f"{b}/projects/{project['id']}/tasks", json=body)
        assert r.status_code == 201, r.text
    assert r.json()["estimate_hours"] is None

    data = owner.get(f"{b}/capacity").json()
    person = next(p for p in data["people"] if p["member_id"] == contrib)
    week = person["weeks"][0]
    assert (week["hours"], week["unestimated"], week["tasks"]) == (45, 1, 3)
    assert person["capacity"] is None and week["over"] is None  # capacité à vérifier

    # Un contributeur saisit sa propre capacité, pas celle des autres.
    owner_id = members["proprio@exemple.com"]["id"]
    assert (
        contributor.put(f"{b}/capacity/{owner_id}", json={"hours_per_week": 10}).status_code == 403
    )
    data = contributor.put(f"{b}/capacity/{contrib}", json={"hours_per_week": 35}).json()
    person = next(p for p in data["people"] if p["member_id"] == contrib)
    assert person["capacity"] == 35 and person["weeks"][0]["over"] is True
    assert person["weeks"][1]["over"] is False
    assert reader.put(f"{b}/capacity/{contrib}", json={"hours_per_week": 1}).status_code == 403


def test_event_controls_and_arbitration_dossier(make_client):
    owner, contributor, _reader, b, pf, _project, _members = _setup(make_client)
    today = _today()
    event_type = next(t for t in owner.get(f"{b}/project-types").json() if t["kind"] == "event")
    start = today + timedelta(days=10)
    event = owner.post(
        f"{b}/projects",
        json={
            "title": "Salon Agri",
            "portfolio_id": pf["id"],
            "project_type_id": event_type["id"],
            "start_date": start.isoformat(),
            "end_date": (start + timedelta(days=1)).isoformat(),
        },
    ).json()
    controls = owner.get(f"{b}/projects/{event['id']}/event-controls").json()
    by_key = {c["key"]: c for c in controls}
    assert by_key["targets_j10"]["due_date"] == today.isoformat()
    assert by_key["rehearsal_j1"]["due_date"] == (start - timedelta(days=1)).isoformat()
    assert (
        by_key["contacts_5"]["due_date"] == add_workdays(start + timedelta(days=1), 5).isoformat()
    )
    assert by_key["report_10"]["due_date"] == (start + timedelta(days=11)).isoformat()
    alerts = owner.get(f"{b}/alerts").json()["items"]
    assert any(a["rule"] == "event_control" for a in alerts)
    done = contributor.put(
        f"{b}/projects/{event['id']}/event-controls/targets_j10",
        json={"done": True, "note": "12 cibles sur 15 confirmées"},
    ).json()
    first = next(c for c in done if c["key"] == "targets_j10")
    assert first["done_at"] and first["note"] == "12 cibles sur 15 confirmées"
    assert owner.get(f"{b}/projects/{_project['id']}/event-controls").status_code == 404

    decision = owner.post(f"{b}/decisions", json={"statement": "Choisir la salle"}).json()
    url = f"{b}/decisions/{decision['id']}/arbitration"
    partial = {"version": decision["version"], "context": "Deux salles possibles", "submit": True}
    refused = owner.put(url, json=partial)
    assert refused.status_code == 422 and "au moins deux options" in refused.json()["detail"]
    saved = owner.put(url, json={**partial, "submit": False}).json()
    assert saved["arbitration"]["context"] == "Deux salles possibles"
    assert saved["arbitration_submitted_at"] is None
    full = {
        "version": saved["version"],
        "context": "Deux salles possibles",
        "facts": "Devis reçus",
        "impact_cost": "+2 000 € pour la grande salle",
        "options": [
            {"label": "Grande salle", "consequence": "Plus cher"},
            {"label": "Petite salle", "consequence": "Moins de places"},
        ],
        "recommendation": "Grande salle",
        "risks": "Dépassement de budget",
        "expected_decision": "Choisir avant vendredi",
        "submit": True,
    }
    submitted = owner.put(url, json=full).json()
    assert submitted["arbitration_submitted_at"] is not None
    assert len(submitted["arbitration"]["options"]) == 2


def test_encounters_need_a_follow_up_and_private_ones_stay_private(make_client):
    owner, contributor, reader, b, _pf, _project, members = _setup(make_client)
    today = _today()
    relation = contributor.post(
        f"{b}/relations",
        json={
            "name": "Awa Diop",
            "organization": "Banque Sahel",
            "kind": "partner",
            "potential": "high",
            "crm_ref": "CRM-1042",
            "partnership": {"value_proposition": "Financement des stands"},
        },
    )
    assert relation.status_code == 201, relation.text
    relation = relation.json()
    assert reader.post(f"{b}/relations", json={"name": "X"}).status_code == 403

    meeting = contributor.post(
        f"{b}/encounters",
        json={
            "title": "Rendez-vous Banque Sahel",
            "relation_id": relation["id"],
            "starts_on": (today - timedelta(days=1)).isoformat(),
            "objective": "Obtenir un accord de principe",
        },
    ).json()
    assert meeting["triage"] == "to_triage"
    url = f"{b}/encounters/{meeting['id']}"
    refuse = contributor.patch(url, json={"version": meeting["version"], "triage": "refuse"})
    assert refuse.status_code == 422
    accepted = contributor.patch(
        url, json={"version": meeting["version"], "triage": "accept"}
    ).json()
    assert accepted["without_follow_up"] is True
    no_objective = contributor.patch(
        url, json={"version": accepted["version"], "dossier_ready": True}
    )
    assert no_objective.status_code == 422
    # Clôturer sans suite exige un motif.
    close = f"{url}/close"
    assert contributor.post(close, json={"version": accepted["version"]}).status_code == 422
    followed = contributor.patch(
        url,
        json={
            "version": accepted["version"],
            "report": "Accord de principe obtenu",
            "follow_owner_member_id": members["contrib@exemple.com"]["id"],
            "next_action": "Envoyer la proposition",
            "next_action_date": (today + timedelta(days=3)).isoformat(),
        },
    ).json()
    assert followed["without_follow_up"] is False
    closed = contributor.post(close, json={"version": followed["version"]}).json()
    assert closed["closed_at"] is not None
    relations = owner.get(f"{b}/relations").json()
    assert relations[0]["last_contact"] == (today - timedelta(days=1)).isoformat()
    assert relations[0]["encounters"] == 1

    contributor.post(f"{b}/encounters", json={"title": "Entretien individuel", "private": True})
    assert [e["title"] for e in reader.get(f"{b}/encounters").json()] == [
        "Rendez-vous Banque Sahel"
    ]
    assert len(owner.get(f"{b}/encounters").json()) == 2


def test_relations_and_encounters_survive_export_and_import(make_client):
    owner, _contributor, _reader, b, _pf, _project, members = _setup(make_client)
    relation = owner.post(f"{b}/relations", json={"name": "Awa Diop", "kind": "partner"}).json()
    owner.post(
        f"{b}/encounters",
        json={"title": "Rendez-vous", "relation_id": relation["id"], "objective": "Accord"},
    )
    owner.put(f"{b}/capacity/{members['proprio@exemple.com']['id']}", json={"hours_per_week": 30})
    report = owner.post(
        "/api/space-imports",
        files={"file": ("export.zip", owner.get(f"{b}/export").content, "application/zip")},
    ).json()
    assert report["counts"]["relations"] == 1 and report["counts"]["encounters"] == 1
    new = f"/api/spaces/{report['space_id']}"
    encounters = owner.get(f"{new}/encounters").json()
    assert encounters[0]["relation"]["name"] == "Awa Diop"
    me = next(p for p in owner.get(f"{new}/capacity").json()["people"] if p["capacity"])
    assert me["capacity"] == 30
