"""Calcul des alertes et récapitulatif quotidien (WORKFLOW phase 7, CDC §16, §19).

Une alerte invite à vérifier une situation ; elle ne déclare jamais un projet en échec.
Seuls les membres ayant un compte reçoivent des alertes :
un responsable saisi en nom libre n'en reçoit pas.
"""

import html
import uuid
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from pilot_api.config import get_settings
from pilot_api.mailer import MailError, mail_configured, send_email
from pilot_api.models import (
    CLOSED_PROJECT_STATUSES,
    CLOSED_TASK_STATUSES,
    Alert,
    AlertPreference,
    AlertRule,
    Membership,
    MembershipStatus,
    Project,
    ProjectStatus,
    Role,
    Space,
    Task,
    User,
    utcnow,
)

DUE_SOON_DAYS = {7, 3, 1, 0}
DECISION_DAYS = 7
STALE_DAYS = 14

RULES: dict[AlertRule, str] = {
    AlertRule.OVERDUE: "En retard",
    AlertRule.BLOCKED: "Bloqué",
    AlertRule.DUE_SOON: "Échéance proche",
    AlertRule.DECISION_PENDING: "Décision en attente",
    AlertRule.STALE: "Suivi non actualisé",
    AlertRule.MISSING_INFO: "Information manquante",
}
RULE_ORDER = list(RULES)

MONTHS = [
    "janv.",
    "févr.",
    "mars",
    "avr.",
    "mai",
    "juin",
    "juil.",
    "août",
    "sept.",
    "oct.",
    "nov.",
    "déc.",
]


def short_date(day: date) -> str:
    return f"{day.day} {MONTHS[day.month - 1]}"


def local_now(space: Space) -> datetime:
    return utcnow().astimezone(ZoneInfo(space.timezone))


def _local_day(moment: datetime, space: Space) -> date:
    return moment.astimezone(ZoneInfo(space.timezone)).date()


def _due_detail(due: date, today: date) -> str:
    days = (due - today).days
    if days == 0:
        return f"Échéance aujourd'hui ({short_date(due)})"
    return f"Échéance dans {days} jour{'s' if days > 1 else ''} ({short_date(due)})"


def compute_alerts(db: Session, space: Space, today: date) -> int:
    """Crée les alertes du jour pour l'espace. Peut être relancé sans créer de doublon."""
    memberships = db.scalars(
        select(Membership).where(
            Membership.space_id == space.id,
            Membership.status == MembershipStatus.ACTIVE,
            Membership.user_id.is_not(None),
        )
    ).all()
    user_of = {m.id: m.user_id for m in memberships}
    owners = {m.user_id for m in memberships if m.role == Role.OWNER}

    projects = db.scalars(
        select(Project).where(
            Project.space_id == space.id, Project.status.not_in(CLOSED_PROJECT_STATUSES)
        )
    ).all()
    by_id = {p.id: p for p in projects}
    rows: list[dict] = []

    def add(
        users,
        rule: AlertRule,
        target_type: str,
        target_id,
        project: Project,
        title: str,
        detail: str,
    ):
        for user_id in {u for u in users if u}:
            rows.append(
                {
                    "id": uuid.uuid4(),
                    "space_id": space.id,
                    "user_id": user_id,
                    "rule": rule,
                    "target_type": target_type,
                    "target_id": target_id,
                    "project_id": project.id,
                    "alert_date": today,
                    "title": title[:200],
                    "detail": detail[:300],
                    "created_at": utcnow(),
                }
            )

    for p in projects:
        responsible = user_of.get(p.owner_member_id) if p.owner_member_id else None
        if p.due_date is not None:
            days = (p.due_date - today).days
            if days in DUE_SOON_DAYS:
                add(
                    [responsible],
                    AlertRule.DUE_SOON,
                    "project",
                    p.id,
                    p,
                    p.title,
                    _due_detail(p.due_date, today),
                )
            elif days < 0:
                add(
                    [responsible, *owners],
                    AlertRule.OVERDUE,
                    "project",
                    p.id,
                    p,
                    p.title,
                    f"Échéance dépassée depuis le {short_date(p.due_date)}",
                )
        if p.status == ProjectStatus.BLOCKED:
            add(
                [responsible, *owners],
                AlertRule.BLOCKED,
                "project",
                p.id,
                p,
                p.title,
                p.situation or "Projet bloqué",
            )
        unchanged = (today - _local_day(p.updated_at, space)).days
        if p.decision_needed and unchanged >= DECISION_DAYS:
            add(
                [responsible, *owners],
                AlertRule.DECISION_PENDING,
                "project",
                p.id,
                p,
                p.title,
                f"Décision attendue depuis {unchanged} jours : {p.decision_needed}",
            )
        if unchanged >= STALE_DAYS:
            add(
                [responsible] if responsible else owners,
                AlertRule.STALE,
                "project",
                p.id,
                p,
                p.title,
                f"Pas de mise à jour depuis {unchanged} jours",
            )
        if not (p.owner_member_id or p.owner_label) or not p.next_step:
            missing = (
                "responsable du suivi"
                if not (p.owner_member_id or p.owner_label)
                else "prochaine étape"
            )
            add(owners, AlertRule.MISSING_INFO, "project", p.id, p, p.title, f"Sans {missing}")

    tasks = db.scalars(
        select(Task).where(
            Task.space_id == space.id,
            Task.status.not_in(CLOSED_TASK_STATUSES),
            Task.due_date.is_not(None),
            Task.project_id.in_(list(by_id)),
        )
    ).all()
    for t in tasks:
        project = by_id[t.project_id]
        users = [
            user_of.get(t.assignee_member_id) if t.assignee_member_id else None,
            user_of.get(project.owner_member_id) if project.owner_member_id else None,
        ]
        days = (t.due_date - today).days
        title = f"{t.title} · {project.title}"
        if days in DUE_SOON_DAYS:
            add(
                users,
                AlertRule.DUE_SOON,
                "task",
                t.id,
                project,
                title,
                _due_detail(t.due_date, today),
            )
        elif days < 0:
            add(
                users,
                AlertRule.OVERDUE,
                "task",
                t.id,
                project,
                title,
                f"Tâche en retard depuis le {short_date(t.due_date)}",
            )

    if not rows:
        return 0
    result = db.execute(
        insert(Alert)
        .values(rows)
        .on_conflict_do_nothing(constraint="uq_alerts_user_rule_target_day")
    )
    return result.rowcount or 0


def preference_for(db: Session, user_id: uuid.UUID, space_id: uuid.UUID) -> AlertPreference:
    pref = db.scalar(
        select(AlertPreference).where(
            AlertPreference.user_id == user_id, AlertPreference.space_id == space_id
        )
    )
    if pref is None:
        pref = AlertPreference(
            user_id=user_id, space_id=space_id, disabled_rules=[], email_digest=True, digest_hour=7
        )
        db.add(pref)
        db.flush()
    return pref


def todays_alerts(
    db: Session, user_id: uuid.UUID, space: Space, today: date, pref: AlertPreference
):
    alerts = db.scalars(
        select(Alert).where(
            Alert.user_id == user_id, Alert.space_id == space.id, Alert.alert_date == today
        )
    ).all()
    alerts = [a for a in alerts if a.rule.value not in (pref.disabled_rules or [])]
    return sorted(alerts, key=lambda a: (RULE_ORDER.index(a.rule), a.title))


TAG_STYLE = "padding:8px 12px;color:#B4400A;font-weight:700;white-space:nowrap"
LINK_STYLE = "color:#18181B;font-weight:600"
BUTTON_STYLE = (
    "background:#D0450A;color:#fff;padding:10px 18px;border-radius:10px;"
    "text-decoration:none;font-weight:700"
)
FOOTER = (
    "<p style='color:#6B7280;font-size:12px'>Vous recevez ce récapitulatif car il est activé "
    "dans vos préférences d'alertes PILOT.</p>"
)


def digest_email(
    user: User, space: Space, alerts: list[Alert], today: date
) -> tuple[str, str, str]:
    base = get_settings().app_base_url.rstrip("/")
    link = f"{base}/espaces/{space.id}"
    subject = (
        f"PILOT · {space.name} : {len(alerts)} rappel{'s' if len(alerts) > 1 else ''} aujourd'hui"
    )
    if not alerts:
        subject = f"PILOT · {space.name} : aucun rappel aujourd'hui"
    lines_text, rows_html = [], []
    for alert in alerts:
        url = f"{base}/espaces/{space.id}/projets/{alert.project_id}"
        lines_text.append(f"- [{RULES[alert.rule]}] {alert.title} : {alert.detail}\n  {url}")
        rows_html.append(
            "<tr>"
            f"<td style='{TAG_STYLE}'>{html.escape(RULES[alert.rule])}</td>"
            f"<td style='padding:8px 12px'><a href='{html.escape(url)}' style='{LINK_STYLE}'>"
            f"{html.escape(alert.title)}</a>"
            f"<br><span style='color:#6B7280'>{html.escape(alert.detail)}</span></td>"
            "</tr>"
        )
    intro = (
        f"Bonjour {user.display_name}, voici ce qui demande votre attention le {short_date(today)}."
    )
    text = (
        intro
        + "\n\n"
        + ("\n".join(lines_text) or "Aucun rappel aujourd'hui.")
        + f"\n\nOuvrir PILOT : {link}\n"
    )
    body = (
        "".join(rows_html) or "<tr><td style='padding:8px 12px'>Aucun rappel aujourd'hui.</td></tr>"
    )
    page = (
        "<div style='font-family:Arial,sans-serif;color:#18181B;max-width:620px'>"
        f"<h1 style='font-size:20px'>{html.escape(space.name)}</h1>"
        f"<p>{html.escape(intro)}</p>"
        f"<table style='border-collapse:collapse;width:100%;font-size:14px'>{body}</table>"
        f"<p style='margin-top:20px'><a href='{html.escape(link)}' style='{BUTTON_STYLE}'>"
        "Ouvrir PILOT</a></p>"
        f"{FOOTER}"
        "</div>"
    )
    return subject, page, text


def run_daily(db: Session, send=send_email) -> dict:
    """Appelé chaque heure par la tâche planifiée : calcule les alertes de chaque espace,
    puis envoie le récapitulatif aux membres dont l'heure choisie est atteinte
    et qui ne l'ont pas encore reçu aujourd'hui."""
    stats = {"spaces": 0, "alerts_created": 0, "digests_sent": 0, "digest_errors": 0}
    can_mail = mail_configured() or send is not send_email
    for space in db.scalars(select(Space)).all():
        now = local_now(space)
        today = now.date()
        stats["spaces"] += 1
        stats["alerts_created"] += compute_alerts(db, space, today)
        members = db.execute(
            select(Membership, User)
            .join(User, User.id == Membership.user_id)
            .where(Membership.space_id == space.id, Membership.status == MembershipStatus.ACTIVE)
        ).all()
        for _, user in members:
            pref = preference_for(db, user.id, space.id)
            if not (can_mail and pref.email_digest) or now.hour < pref.digest_hour:
                continue
            if pref.last_digest_date == today:
                continue
            alerts = todays_alerts(db, user.id, space, today, pref)
            pref.last_digest_date = today
            if not alerts:
                continue  # pas d'e-mail vide
            subject, page, text = digest_email(user, space, alerts, today)
            try:
                send(
                    to_email=user.email,
                    to_name=user.display_name,
                    subject=subject,
                    html=page,
                    text=text,
                )
                stats["digests_sent"] += 1
            except MailError:
                stats["digest_errors"] += 1
                pref.last_digest_date = None  # nouvel essai à l'heure suivante
        db.commit()
    return stats
