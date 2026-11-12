"""Jours fériés de l'espace et temps déclaré (« temps stratégique »)."""

from datetime import UTC, date, datetime, timedelta

from conftest import create_space, invite_and_join, register

from pilot_api.holidays import add_workdays, easter, presets
from pilot_api.models import Routine, RoutineFrequency
from pilot_api.routine_rules import dates_between


def test_easter_and_country_presets():
    assert easter(2026) == date(2026, 4, 5)
    assert easter(2027) == date(2027, 3, 28)
    fr = {h["date"]: h["label"] for h in presets("FR", 2026)}
    assert fr["2026-04-06"] == "Lundi de Pâques" and fr["2026-05-14"] == "Ascension"
    assert fr["2026-07-14"] == "Fête nationale" and len(fr) == 11
    sn = {h["date"]: h["label"] for h in presets("SN", 2026)}
    assert sn["2026-04-04"] == "Fête de l'Indépendance" and "2026-07-14" not in sn


def test_holidays_shift_routines_and_workday_deadlines():
    holidays = frozenset({date(2026, 12, 25), date(2026, 11, 11)})
    # Vendredi 25 déc. férié : 5 jours ouvrés après le jeudi 24 → 28, 29, 30, 31 déc., 1er janv.
    assert add_workdays(date(2026, 12, 24), 5, holidays) == date(2027, 1, 1)
    weekly = Routine(
        title="Boucler la semaine",
        frequency=RoutineFrequency.WEEKLY,
        weekdays=[4],
        month_days=[],
        workdays_only=True,
        start_date=date(2026, 12, 1),
    )
    fridays = dates_between(weekly, date(2026, 12, 1), date(2026, 12, 31), holidays)
    assert date(2026, 12, 25) not in fridays and date(2026, 12, 18) in fridays
    monthly = Routine(
        title="Synthèse",
        frequency=RoutineFrequency.MONTHLY,
        weekdays=[],
        month_days=[11],
        workdays_only=True,
        start_date=date(2026, 11, 1),
    )
    # Le 11 nov. 2026 (mercredi) est férié : la routine passe au mardi 10.
    assert dates_between(monthly, date(2026, 11, 1), date(2026, 11, 30), holidays) == [
        date(2026, 11, 10)
    ]


def test_space_holidays_and_declared_time(make_client):
    owner = make_client()
    register(owner, "proprio@exemple.com", "Raissa")
    space = create_space(owner)
    b = f"/api/spaces/{space['id']}"
    contributor = make_client()
    invite_and_join(owner, contributor, space["id"], "contrib@exemple.com", "contributor")
    today = datetime.now(UTC).date()

    preset = owner.get(f"{b}/holidays/presets", params={"country": "SN", "year": 2027}).json()
    assert preset["note"].startswith("À ajouter à la main")
    tomorrow = today + timedelta(days=1)
    body = {"holidays": [*preset["holidays"], {"date": tomorrow.isoformat(), "label": "Korité"}]}
    assert contributor.put(f"{b}/holidays", json=body).status_code == 403
    saved = owner.put(f"{b}/holidays", json=body).json()
    assert {"date": tomorrow.isoformat(), "label": "Korité"} in saved["holidays"]
    # Une routine quotidienne en jours ouvrés n'a pas d'occurrence le jour férié.
    routine = owner.post(
        f"{b}/routines",
        json={"title": "Tour", "frequency": "daily", "weekdays": [0, 1, 2, 3, 4, 5, 6]},
    ).json()
    occs = owner.get(
        f"{b}/routine-occurrences",
        params={
            "routine_id": routine["id"],
            "start": today.isoformat(),
            "end": tomorrow.isoformat(),
        },
    ).json()
    assert tomorrow.isoformat() not in {o["scheduled_date"] for o in occs}

    # Temps déclaré : pas dans le futur, pas plus de 24 h par jour, détail personnel.
    url = f"{b}/time-entries"
    assert (
        owner.post(
            url, json={"day": tomorrow.isoformat(), "minutes": 60, "category": "strategic"}
        ).status_code
        == 422
    )
    owner.post(url, json={"day": today.isoformat(), "minutes": 180, "category": "strategic"})
    owner.post(url, json={"day": today.isoformat(), "minutes": 60, "category": "operational"})
    mine = contributor.post(
        url, json={"day": today.isoformat(), "minutes": 120, "category": "coordination"}
    ).json()
    assert (
        contributor.post(
            url, json={"day": today.isoformat(), "minutes": 1400, "category": "admin"}
        ).status_code
        == 422
    )
    assert owner.get(url).json()["total_minutes"] == 240
    assert owner.delete(f"{url}/{mine['entries'][0]['id']}").status_code == 404

    own = next(
        i for i in owner.get(f"{b}/indicators").json()["indicators"] if i["key"] == "strategic_time"
    )
    # Propriétaire : 180 min stratégiques sur 360 min déclarées dans l'espace.
    assert own["value"] == 50.0 and own["status"] == "below" and "2 personne(s)" in own["note"]
    theirs = next(
        i
        for i in contributor.get(f"{b}/indicators").json()["indicators"]
        if i["key"] == "strategic_time"
    )
    assert theirs["value"] == 0.0
    assert contributor.delete(f"{url}/{mine['entries'][0]['id']}").json()["total_minutes"] == 0
