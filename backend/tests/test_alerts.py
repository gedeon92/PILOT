from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from conftest import create_space, invite_and_join, register
from sqlalchemy import update
from sqlalchemy.orm import Session

from pilot_api import alerts as alerts_module
from pilot_api.config import get_settings
from pilot_api.models import AlertPreference, Project

DAKAR = ZoneInfo("Africa/Dakar")  # fuseau de l'espace créé par conftest.create_space


def day(offset: int) -> str:
    return (datetime.now(DAKAR).date() + timedelta(days=offset)).isoformat()


def _setup(make_client):
    owner = make_client()
    register(owner, "proprio@exemple.com", "Aïcha Ndiaye")
    space = create_space(owner)
    base = f"/api/spaces/{space['id']}"
    portfolio = owner.post(f"{base}/portfolios", json={"name": "Événements"}).json()
    contributor = make_client()
    member = invite_and_join(owner, contributor, space["id"], "moussa@exemple.com", "contributor")
    return owner, contributor, member, space, base, portfolio


def _project(client, base, portfolio, **fields):
    # Responsable et prochaine étape renseignés : pas d'alerte « information manquante » parasite.
    body = {
        "title": "Salon",
        "portfolio_id": portfolio["id"],
        "next_step": "Avancer",
        "owner_label": "Équipe événements",
        **fields,
    }
    response = client.post(f"{base}/projects", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def _rules(client, base):
    return sorted((a["rule"], a["title"]) for a in client.get(f"{base}/alerts").json()["items"])


def test_due_soon_alerts_the_responsible_member_only(make_client):
    owner, contributor, member, _, base, portfolio = _setup(make_client)
    _project(owner, base, portfolio, title="Salon", due_date=day(3), owner_member_id=member["id"])

    assert _rules(contributor, base) == [("due_soon", "Salon")]
    assert _rules(owner, base) == []
    detail = contributor.get(f"{base}/alerts").json()["items"][0]["detail"]
    assert detail.startswith("Échéance dans 3 jours")


def test_free_name_responsible_gets_no_reminder(make_client):
    owner, contributor, _, _, base, portfolio = _setup(make_client)
    _project(owner, base, portfolio, due_date=day(1), owner_label="Mon assistante")

    assert _rules(owner, base) == []
    assert _rules(contributor, base) == []


def test_overdue_and_blocked_alert_responsible_and_owner(make_client):
    owner, contributor, member, _, base, portfolio = _setup(make_client)
    _project(owner, base, portfolio, title="Retard", due_date=day(-2), owner_member_id=member["id"])
    _project(owner, base, portfolio, title="Bloqué", status="blocked", owner_member_id=member["id"])

    expected = [("blocked", "Bloqué"), ("overdue", "Retard")]
    assert _rules(contributor, base) == expected
    assert _rules(owner, base) == expected


def test_missing_information_alerts_the_owner(make_client):
    owner, contributor, _, _, base, portfolio = _setup(make_client)
    owner.post(f"{base}/projects", json={"title": "Sans suivi", "portfolio_id": portfolio["id"]})

    assert _rules(owner, base) == [("missing_info", "Sans suivi")]
    assert _rules(contributor, base) == []


def test_task_due_today_alerts_assignee_and_responsible(make_client):
    owner, contributor, member, _, base, portfolio = _setup(make_client)
    me = next(m for m in owner.get(f"{base}/members").json() if m["is_me"])
    project = _project(owner, base, portfolio, owner_member_id=me["id"])
    owner.post(
        f"{base}/projects/{project['id']}/tasks",
        json={"title": "Devis", "due_date": day(0), "assignee_member_id": member["id"]},
    )

    assert _rules(contributor, base) == [("due_soon", "Devis · Salon")]
    assert _rules(owner, base) == [("due_soon", "Devis · Salon")]


def test_stale_and_decision_pending(make_client, engine):
    owner, _, _, _, base, portfolio = _setup(make_client)
    me = next(m for m in owner.get(f"{base}/members").json() if m["is_me"])
    project = _project(
        owner, base, portfolio, owner_member_id=me["id"], decision_needed="Changer de traiteur ?"
    )
    with Session(engine) as db:
        db.execute(
            update(Project)
            .where(Project.id == project["id"])
            .values(updated_at=datetime.now(DAKAR) - timedelta(days=15))
        )
        db.commit()

    assert _rules(owner, base) == [("decision_pending", "Salon"), ("stale", "Salon")]


def test_no_duplicate_alerts_on_refresh(make_client):
    owner, _, _, _, base, portfolio = _setup(make_client)
    _project(owner, base, portfolio, due_date=day(-1))

    first = owner.get(f"{base}/alerts").json()
    second = owner.get(f"{base}/alerts").json()

    assert len(first["items"]) == len(second["items"]) == 1
    assert second["unread"] == 1


def test_read_and_disabled_rules(make_client):
    owner, _, _, _, base, portfolio = _setup(make_client)
    _project(owner, base, portfolio, title="A", due_date=day(-1))
    _project(owner, base, portfolio, title="B", status="blocked")
    items = owner.get(f"{base}/alerts").json()["items"]

    read = owner.post(f"{base}/alerts/{items[0]['id']}/read")
    assert read.json()["read"] is True
    assert owner.get(f"{base}/alerts").json()["unread"] == 1

    prefs = owner.put(
        f"{base}/alert-preferences",
        json={"disabled_rules": ["blocked"], "email_digest": False, "digest_hour": 8},
    ).json()
    assert prefs["disabled_rules"] == ["blocked"]
    assert [a["rule"] for a in owner.get(f"{base}/alerts").json()["items"]] == ["overdue"]

    assert owner.post(f"{base}/alerts/read-all").status_code == 204
    assert owner.get(f"{base}/alerts").json()["unread"] == 0


def test_unknown_rule_in_preferences_is_refused(make_client):
    owner, _, _, _, base, _ = _setup(make_client)
    response = owner.put(
        f"{base}/alert-preferences",
        json={"disabled_rules": ["inconnue"], "email_digest": True, "digest_hour": 7},
    )
    assert response.status_code == 422


def test_alerts_are_private(make_client):
    owner, contributor, _, _, base, portfolio = _setup(make_client)
    _project(owner, base, portfolio, due_date=day(-1))
    alert = owner.get(f"{base}/alerts").json()["items"][0]

    assert contributor.post(f"{base}/alerts/{alert['id']}/read").status_code == 404
    other = make_client()
    register(other, "autre@exemple.com")
    assert other.get(f"{base}/alerts").status_code == 404


def test_cron_endpoint_is_protected(make_client, monkeypatch):
    client = make_client()
    monkeypatch.setenv("CRON_SECRET", "")
    get_settings.cache_clear()
    assert client.post("/api/cron/daily").status_code == 503

    monkeypatch.setenv("CRON_SECRET", "secret-de-test")
    get_settings.cache_clear()
    assert client.post("/api/cron/daily", headers={"X-Cron-Secret": "faux"}).status_code == 403
    ok = client.post("/api/cron/daily", headers={"X-Cron-Secret": "secret-de-test"})
    assert ok.status_code == 200
    assert set(ok.json()) == {"spaces", "alerts_created", "digests_sent", "digest_errors"}
    get_settings.cache_clear()


def test_daily_digest_is_sent_once_at_the_chosen_hour(make_client, engine):
    owner, _, _, space, base, portfolio = _setup(make_client)
    _project(owner, base, portfolio, title="En retard", due_date=day(-1))
    sent: list[dict] = []

    def fake_send(**message):
        sent.append(message)

    now_hour = datetime.now(DAKAR).hour
    with Session(engine) as db:
        # Heure du récapitulatif pas encore atteinte : rien n'est envoyé.
        if now_hour < 23:
            alerts_module.preference_for(db, _user_id(db), space["id"]).digest_hour = now_hour + 1
            db.commit()
            alerts_module.run_daily(db, send=fake_send)
            assert sent == []
        # Heure atteinte : un envoi, puis plus rien le même jour.
        db.execute(update(AlertPreference).values(digest_hour=0, last_digest_date=None))
        db.commit()
        alerts_module.run_daily(db, send=fake_send)
        alerts_module.run_daily(db, send=fake_send)

    proprio = [m for m in sent if m["to_email"] == "proprio@exemple.com"]
    assert proprio == []  # domaine de test : aucun envoi réel
    with Session(engine) as db:
        from pilot_api.models import User

        db.execute(
            update(User)
            .where(User.email == "proprio@exemple.com")
            .values(email="proprio@pilot.app")
        )
        db.execute(update(AlertPreference).values(last_digest_date=None, digest_hour=0))
        db.commit()
        alerts_module.run_daily(db, send=fake_send)
        alerts_module.run_daily(db, send=fake_send)
    proprio = [m for m in sent if m["to_email"] == "proprio@pilot.app"]
    assert len(proprio) == 1
    assert "En retard" in proprio[0]["text"]
    assert "1 rappel" in proprio[0]["subject"]


def _user_id(db):
    from sqlalchemy import select

    from pilot_api.models import User

    return db.scalar(select(User.id).where(User.email == "proprio@exemple.com"))


def test_no_digest_to_reserved_test_domains():
    assert alerts_module.is_test_address("verif@exemple.com")
    assert alerts_module.is_test_address("a@example.org")
    assert alerts_module.is_test_address("a@pilot.test")
    assert not alerts_module.is_test_address("contact@datatym.com")
