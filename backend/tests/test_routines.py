"""Routines de pilotage et « Ma journée / Ma semaine » (étape F5, cahier V2 RIT01–RIT07, VIS01)."""

from datetime import UTC, date, datetime, timedelta

from conftest import create_space, invite_and_join, register
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from pilot_api.models import Routine, RoutineFrequency, RoutineOccurrence
from pilot_api.routine_rules import dates_between


def _routine(**kw) -> Routine:
    base = {
        "title": "R",
        "frequency": RoutineFrequency.WEEKLY,
        "weekdays": [],
        "month_days": [],
        "nth_weekday": None,
        "workdays_only": True,
        "start_date": date(2026, 11, 2),  # un lundi
    }
    return Routine(**{**base, **kw})


def test_recurrence_rules_are_distinct():
    start, end = date(2026, 11, 1), date(2026, 12, 31)
    # Toutes les deux semaines : un lundi sur deux à partir du début.
    biweekly = dates_between(
        _routine(frequency=RoutineFrequency.BIWEEKLY, weekdays=[0]), start, end
    )
    assert biweekly[:3] == [date(2026, 11, 2), date(2026, 11, 16), date(2026, 11, 30)]
    # Deux fois par mois : le 1er et le 15 (le 1er nov. 2026 est un dimanche, avant le début).
    twice = dates_between(
        _routine(frequency=RoutineFrequency.TWICE_MONTHLY, month_days=[1, 15]), start, end
    )
    # 15 nov. 2026 = dimanche → vendredi 13 ; 1er déc. ; 15 déc.
    assert twice == [date(2026, 11, 13), date(2026, 12, 1), date(2026, 12, 15)]
    # Mensuelle au premier lundi, et au dernier vendredi.
    first_monday = dates_between(
        _routine(frequency=RoutineFrequency.MONTHLY, nth_weekday={"n": 1, "weekday": 0}),
        start,
        end,
    )
    assert first_monday == [date(2026, 11, 2), date(2026, 12, 7)]
    last_friday = dates_between(
        _routine(frequency=RoutineFrequency.MONTHLY, nth_weekday={"n": -1, "weekday": 4}),
        start,
        end,
    )
    assert last_friday == [date(2026, 11, 27), date(2026, 12, 25)]
    # Trimestrielle : tous les trois mois à partir du mois de début ; 31 → dernier jour.
    quarterly = dates_between(
        _routine(
            frequency=RoutineFrequency.QUARTERLY, month_days=[31], start_date=date(2026, 1, 1)
        ),
        date(2026, 1, 1),
        date(2026, 12, 31),
    )
    # 31 janv. = samedi → 30 ; 30 avr. ; 31 juil. ; 31 oct. = samedi → 30.
    assert quarterly == [
        date(2026, 1, 30),
        date(2026, 4, 30),
        date(2026, 7, 31),
        date(2026, 10, 30),
    ]


def _setup(make_client):
    owner = make_client()
    register(owner, "proprio@exemple.com", "Raissa Proprio")
    space = create_space(owner)
    b = f"/api/spaces/{space['id']}"
    reader = make_client()
    invite_and_join(owner, reader, space["id"], "lecteur@exemple.com", "reader")
    return owner, reader, b


def test_occurrences_generated_once_postponed_alone_and_closed_with_checks(make_client, engine):
    owner, reader, b = _setup(make_client)
    today = datetime.now(UTC).date()
    body = {
        "title": "Revoir les jalons",
        "frequency": "daily",
        "weekdays": [0, 1, 2, 3, 4, 5, 6],
        "start_date": today.isoformat(),
        "checklist": [
            {"label": "Jalons à risque revus", "mandatory": True},
            {"label": "Vérification terrain", "mandatory": False},
        ],
    }
    assert reader.post(f"{b}/routines", json=body).status_code == 403
    assert (
        owner.post(f"{b}/routines", json={**body, "frequency": "twice_monthly"}).status_code == 422
    )
    routine = owner.post(f"{b}/routines", json=body)
    assert routine.status_code == 201, routine.text
    routine = routine.json()
    assert routine["next_date"] == today.isoformat()

    # Relancer le générateur sur la même période : aucune occurrence en double (RIT01).
    period = {"start": today.isoformat(), "end": (today + timedelta(days=6)).isoformat()}
    first = owner.get(f"{b}/routine-occurrences", params=period).json()
    again = owner.get(f"{b}/routine-occurrences", params=period).json()
    owner.get(f"{b}/routines")
    assert len(first) == len(again) == 7
    with Session(engine) as db:
        dates = db.scalars(
            select(RoutineOccurrence.scheduled_date).where(
                RoutineOccurrence.routine_id == routine["id"]
            )
        ).all()
        assert len(dates) == len(set(dates))
        total = db.scalar(select(func.count(RoutineOccurrence.id)))

    # Reporter une seule occurrence : les autres ne bougent pas (RIT02), motif exigé.
    occ = first[1]
    url = f"{b}/routine-occurrences/{occ['id']}"
    later = (today + timedelta(days=3)).isoformat()
    assert owner.patch(url, json={"version": occ["version"], "due_date": later}).status_code == 422
    moved = owner.patch(
        url, json={"version": occ["version"], "due_date": later, "postpone_reason": "Salle prise"}
    ).json()
    assert moved["due_date"] == later and moved["scheduled_date"] == occ["scheduled_date"]
    assert moved["postponed"] is True
    after = owner.get(f"{b}/routine-occurrences", params=period).json()
    others = {o["id"]: o["due_date"] for o in after if o["id"] != occ["id"]}
    assert others == {o["id"]: o["due_date"] for o in first if o["id"] != occ["id"]}
    with Session(engine) as db:
        assert db.scalar(select(func.count(RoutineOccurrence.id))) == total

    # Clôturer comme faite exige les contrôles obligatoires, ou une exception motivée.
    today_occ = first[0]
    close = f"{b}/routine-occurrences/{today_occ['id']}/close"
    refused = owner.post(close, json={"version": today_occ["version"], "state": "done"})
    assert refused.status_code == 422 and "Jalons à risque revus" in refused.json()["detail"]
    assert (
        reader.post(close, json={"version": today_occ["version"], "state": "done"}).status_code
        == 403
    )
    chk = today_occ["checklist"][0]["id"]
    checked = owner.patch(
        f"{b}/routine-occurrences/{today_occ['id']}",
        json={"version": today_occ["version"], "checks": {chk: True}},
    ).json()
    assert checked["missing_mandatory"] == []
    done = owner.post(
        close, json={"version": checked["version"], "state": "done", "result": "RAS"}
    ).json()
    assert done["state"] == "done" and done["exception_reason"] is None

    # Exception motivée visible.
    third = after[2] if after[2]["id"] != occ["id"] else after[3]
    excepted = owner.post(
        f"{b}/routine-occurrences/{third['id']}/close",
        json={"version": third["version"], "state": "done", "exception_reason": "Terrain fermé"},
    ).json()
    assert excepted["exception_reason"] == "Terrain fermé"
    # Annuler demande un motif.
    cancel = owner.post(
        f"{b}/routine-occurrences/{moved['id']}/close",
        json={"version": moved["version"], "state": "cancelled"},
    )
    assert cancel.status_code == 422


def test_follow_ups_profiles_pause_and_series_scope(make_client):
    owner, reader, b = _setup(make_client)
    today = datetime.now(UTC).date()
    pf = owner.post(f"{b}/portfolios", json={"name": "Général"}).json()
    project = owner.post(f"{b}/projects", json={"title": "Atlas", "portfolio_id": pf["id"]}).json()

    profiles = owner.get(f"{b}/routines/profiles").json()
    assert {"preparer_journee", "point_dirigeant", "synthese_execution"} <= {
        p["key"] for p in profiles
    }
    added = owner.post(f"{b}/routines/profiles", json={"keys": ["point_dirigeant"]}).json()
    assert added[0]["title"] == "Préparer le point dirigeant"
    assert added[0]["duration_minutes"] == 45 and added[0]["weekdays"] == [0]
    # Ajouter deux fois la même routine type ne la duplique pas.
    assert owner.post(f"{b}/routines/profiles", json={"keys": ["point_dirigeant"]}).json() == []

    routine = owner.post(
        f"{b}/routines",
        json={"title": "Tour", "frequency": "daily", "weekdays": [0, 1, 2, 3, 4, 5, 6]},
    ).json()
    occs = owner.get(f"{b}/routine-occurrences", params={"routine_id": routine["id"]}).json()
    occ = occs[0]
    # Un constat devient une tâche du projet, liée à l'occurrence.
    follow = owner.post(
        f"{b}/routine-occurrences/{occ['id']}/follow-ups",
        json={"kind": "task", "project_id": project["id"], "title": "Relancer le traiteur"},
    )
    assert follow.status_code == 201, follow.text
    assert follow.json()["links"][0]["title"] == "Relancer le traiteur"
    tasks = owner.get(f"{b}/projects/{project['id']}/tasks").json()
    assert [t["title"] for t in tasks] == ["Relancer le traiteur"]
    decision = owner.post(
        f"{b}/routine-occurrences/{occ['id']}/follow-ups",
        json={"kind": "decision", "title": "Choisir le traiteur"},
    ).json()
    assert [link["kind"] for link in decision["links"]] == ["task", "decision"]

    # Modifier la série « pour les suivantes » : les occurrences touchées restent.
    count_before = len(
        owner.get(f"{b}/routine-occurrences", params={"routine_id": routine["id"]}).json()
    )
    updated = owner.patch(
        f"{b}/routines/{routine['id']}",
        json={"version": routine["version"], "weekdays": [0], "scope": "following"},
    ).json()
    remaining = owner.get(
        f"{b}/routine-occurrences",
        params={
            "routine_id": routine["id"],
            "start": today.isoformat(),
            "end": (today + timedelta(days=13)).isoformat(),
        },
    ).json()
    assert occ["id"] in {o["id"] for o in remaining}  # liée : gardée
    assert all(
        date.fromisoformat(o["scheduled_date"]).weekday() == 0
        for o in remaining
        if o["id"] != occ["id"]
    )
    assert len(remaining) < count_before

    # Pause puis reprise : la période de pause n'est pas rattrapée.
    paused = owner.post(f"{b}/routines/{routine['id']}/pause").json()
    assert paused["paused"] is True
    resumed = owner.post(f"{b}/routines/{routine['id']}/resume").json()
    assert resumed["paused"] is False and resumed["version"] > updated["version"]
    # Annulation motivée de la série.
    assert (
        owner.post(f"{b}/routines/{routine['id']}/archive", json={"reason": ""}).status_code == 422
    )
    archived = owner.post(
        f"{b}/routines/{routine['id']}/archive", json={"reason": "Remplacée par le point lundi"}
    ).json()
    assert archived["archived"] is True and archived["next_date"] is None
    # Un lecteur consulte.
    assert reader.get(f"{b}/routines").status_code == 200


def test_my_day_and_week(make_client):
    owner, reader, b = _setup(make_client)
    today = datetime.now(UTC).date()
    pf = owner.post(f"{b}/portfolios", json={"name": "Général"}).json()
    project = owner.post(f"{b}/projects", json={"title": "Atlas", "portfolio_id": pf["id"]}).json()
    me = next(m for m in owner.get(f"{b}/members").json() if m["is_me"])
    yesterday = (today - timedelta(days=1)).isoformat()
    in_three = (today + timedelta(days=3)).isoformat()
    owner.post(
        f"{b}/projects/{project['id']}/tasks",
        json={"title": "Devis en retard", "due_date": yesterday, "assignee_member_id": me["id"]},
    )
    owner.post(
        f"{b}/projects/{project['id']}/tasks",
        json={"title": "Pas à moi", "due_date": today.isoformat()},
    )
    owner.post(
        f"{b}/projects/{project['id']}/tasks",
        json={"title": "Plus tard", "due_date": in_three, "assignee_member_id": me["id"]},
    )
    owner.post(
        f"{b}/decisions",
        json={
            "statement": "Choisir la salle",
            "executor_member_id": me["id"],
            "due_date": in_three,
        },
    )
    owner.post(
        f"{b}/projects/{project['id']}/milestones",
        json={"title": "Salle confirmée", "due_date": in_three, "owner_member_id": me["id"]},
    )
    owner.post(
        f"{b}/routines",
        json={"title": "Clore ma journée", "frequency": "daily", "weekdays": [0, 1, 2, 3, 4, 5, 6]},
    )

    day = owner.get(f"{b}/agenda").json()
    assert [i["title"] for i in day["items"]] == ["Devis en retard"]
    assert day["items"][0]["late"] is True
    assert [o["routine_title"] for o in day["occurrences"]] == ["Clore ma journée"]

    week = owner.get(
        f"{b}/agenda",
        params={"start": today.isoformat(), "end": (today + timedelta(days=6)).isoformat()},
    ).json()
    kinds = {(i["kind"], i["title"]) for i in week["items"]}
    assert kinds == {
        ("task", "Devis en retard"),
        ("task", "Plus tard"),
        ("decision", "Choisir la salle"),
        ("milestone", "Salle confirmée"),
    }
    assert len(week["occurrences"]) == 7
    # Le lecteur n'a rien d'assigné : sa journée ne montre que les routines sans responsable.
    assert reader.get(f"{b}/agenda").json()["items"] == []


def test_routines_survive_export_and_import(make_client):
    owner, _reader, b = _setup(make_client)
    routine = owner.post(
        f"{b}/routines",
        json={
            "title": "Boucler la semaine",
            "frequency": "weekly",
            "weekdays": [4],
            "checklist": [{"label": "Relevés diffusés"}],
        },
    ).json()
    occ = owner.get(f"{b}/routine-occurrences", params={"routine_id": routine["id"]}).json()[0]
    owner.patch(
        f"{b}/routine-occurrences/{occ['id']}",
        json={"version": occ["version"], "checks": {routine["checklist"][0]["id"]: True}},
    )
    report = owner.post(
        "/api/space-imports",
        files={"file": ("export.zip", owner.get(f"{b}/export").content, "application/zip")},
    ).json()
    assert report["counts"]["routines"] == 1
    new = f"/api/spaces/{report['space_id']}"
    copied = owner.get(f"{new}/routines").json()
    assert [(r["title"], r["weekdays"]) for r in copied] == [("Boucler la semaine", [4])]
    occs = owner.get(f"{new}/routine-occurrences", params={"routine_id": copied[0]["id"]}).json()
    first = next(o for o in occs if o["scheduled_date"] == occ["scheduled_date"])
    assert first["missing_mandatory"] == []
