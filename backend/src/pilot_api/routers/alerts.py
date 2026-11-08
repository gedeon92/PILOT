"""Alertes dans l'application, préférences, et déclenchement planifié des rappels (phase 7)."""

import hmac
import uuid
from datetime import timedelta

from fastapi import APIRouter, Header, HTTPException
from sqlalchemy import select, update

from pilot_api.alerts import (
    RULES,
    compute_alerts,
    digest_email,
    local_now,
    preference_for,
    run_daily,
    todays_alerts,
)
from pilot_api.config import get_settings
from pilot_api.deps import CurrentMembership, CurrentUser, DbSession
from pilot_api.mailer import MailError, mail_configured, send_email
from pilot_api.models import Alert, AlertRule, utcnow
from pilot_api.schemas import (
    AlertList,
    AlertOut,
    AlertPreferenceIn,
    AlertPreferenceOut,
    TestEmailResult,
)

router = APIRouter(prefix="/api/spaces/{space_id}", tags=["alertes"])
cron_router = APIRouter(prefix="/api/cron", tags=["système"])

HISTORY_DAYS = 14


def _out(alert: Alert) -> AlertOut:
    return AlertOut(
        id=alert.id,
        rule=alert.rule.value,
        rule_label=RULES[alert.rule],
        target_type=alert.target_type,
        target_id=alert.target_id,
        project_id=alert.project_id,
        alert_date=alert.alert_date,
        title=alert.title,
        detail=alert.detail,
        read=alert.read_at is not None,
    )


@router.get("/alerts")
def list_alerts(membership: CurrentMembership, user: CurrentUser, db: DbSession) -> AlertList:
    space = membership.space
    today = local_now(space).date()
    # Calcul à la demande : les alertes existent même avant le passage de la tâche planifiée.
    compute_alerts(db, space, today)
    pref = preference_for(db, user.id, space.id)
    db.commit()
    alerts = db.scalars(
        select(Alert)
        .where(
            Alert.user_id == user.id,
            Alert.space_id == space.id,
            Alert.alert_date >= today - timedelta(days=HISTORY_DAYS),
        )
        .order_by(Alert.alert_date.desc(), Alert.created_at)
    ).all()
    visible = [a for a in alerts if a.rule.value not in (pref.disabled_rules or [])]
    items = [_out(a) for a in visible]
    return AlertList(unread=sum(1 for a in visible if a.read_at is None), items=items)


@router.post("/alerts/{alert_id}/read")
def mark_read(
    alert_id: uuid.UUID, membership: CurrentMembership, user: CurrentUser, db: DbSession
) -> AlertOut:
    alert = db.scalar(
        select(Alert).where(
            Alert.id == alert_id, Alert.user_id == user.id, Alert.space_id == membership.space_id
        )
    )
    if alert is None:
        raise HTTPException(404, "Alerte introuvable.")
    if alert.read_at is None:
        alert.read_at = utcnow()
        db.commit()
    return _out(alert)


@router.post("/alerts/read-all", status_code=204)
def mark_all_read(membership: CurrentMembership, user: CurrentUser, db: DbSession) -> None:
    db.execute(
        update(Alert)
        .where(
            Alert.user_id == user.id, Alert.space_id == membership.space_id, Alert.read_at.is_(None)
        )
        .values(read_at=utcnow())
    )
    db.commit()


def _pref_out(pref) -> AlertPreferenceOut:
    return AlertPreferenceOut(
        disabled_rules=list(pref.disabled_rules or []),
        email_digest=pref.email_digest,
        digest_hour=pref.digest_hour,
        email_available=mail_configured(),
        rules={rule.value: label for rule, label in RULES.items()},
    )


@router.get("/alert-preferences")
def get_preferences(
    membership: CurrentMembership, user: CurrentUser, db: DbSession
) -> AlertPreferenceOut:
    pref = preference_for(db, user.id, membership.space_id)
    db.commit()
    return _pref_out(pref)


@router.put("/alert-preferences")
def update_preferences(
    body: AlertPreferenceIn, membership: CurrentMembership, user: CurrentUser, db: DbSession
) -> AlertPreferenceOut:
    known = {rule.value for rule in AlertRule}
    unknown = set(body.disabled_rules) - known
    if unknown:
        raise HTTPException(422, f"Règle inconnue : {', '.join(sorted(unknown))}.")
    pref = preference_for(db, user.id, membership.space_id)
    pref.disabled_rules = sorted(set(body.disabled_rules))
    pref.email_digest = body.email_digest
    pref.digest_hour = body.digest_hour
    db.commit()
    return _pref_out(pref)


@router.post("/alert-preferences/test-email")
def send_test_email(
    membership: CurrentMembership, user: CurrentUser, db: DbSession
) -> TestEmailResult:
    """Envoie tout de suite un aperçu du récapitulatif du jour à la personne connectée."""
    space = membership.space
    today = local_now(space).date()
    compute_alerts(db, space, today)
    pref = preference_for(db, user.id, space.id)
    db.commit()
    alerts = todays_alerts(db, user.id, space, today, pref)
    subject, page, text = digest_email(user, space, alerts, today)
    try:
        send_email(
            to_email=user.email,
            to_name=user.display_name,
            subject=f"Aperçu · {subject}",
            html=page,
            text=text,
        )
    except MailError as error:
        return TestEmailResult(sent=False, message=str(error))
    return TestEmailResult(
        sent=True,
        message=(
            f"Aperçu envoyé à {user.email}. Il arrive en général en moins d'une minute ; "
            "pensez à regarder dans les courriers indésirables."
        ),
    )


@cron_router.post("/daily")
def cron_daily(db: DbSession, x_cron_secret: str | None = Header(default=None)) -> dict:
    """Déclenché chaque heure par GitHub Actions. Protégé par une clé partagée."""
    secret = get_settings().cron_secret
    if not secret:
        raise HTTPException(503, "Tâche planifiée non configurée.")
    if not x_cron_secret or not hmac.compare_digest(x_cron_secret, secret):
        raise HTTPException(403, "Clé de tâche planifiée invalide.")
    return run_daily(db)
