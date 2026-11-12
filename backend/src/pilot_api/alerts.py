"""Calcul des alertes et récapitulatif quotidien (WORKFLOW phase 7, CDC §16, §19).

Une alerte invite à vérifier une situation ; elle ne déclare jamais un projet en échec.
Seuls les membres ayant un compte reçoivent des alertes :
un responsable saisi en nom libre n'en reçoit pas.
"""

import html
import uuid
from collections.abc import Callable
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from pilot_api.access import (
    can_see,
    project_overrides,
    users_who_can_see,
    visible_project_ids,
)
from pilot_api.config import get_settings
from pilot_api.decision_rules import (
    ORPHAN_DAYS,
    accepted,
    is_late,
    mid_term,
    minutes_due,
    minutes_late,
)
from pilot_api.email_theme import pill, render_email
from pilot_api.mailer import MailError, mail_configured, send_email
from pilot_api.milestone_rules import risk
from pilot_api.models import (
    CLOSED_PROJECT_STATUSES,
    CLOSED_TASK_STATUSES,
    OPEN_PROPOSAL_STATES,
    Alert,
    AlertPreference,
    AlertRule,
    Decision,
    DecisionState,
    Meeting,
    Membership,
    MembershipStatus,
    Milestone,
    MilestoneState,
    MilestoneTask,
    Project,
    ProjectStatus,
    Proposal,
    Role,
    Space,
    Task,
    UpdateRequest,
    User,
    utcnow,
)

DUE_SOON_DAYS = {7, 3, 1, 0}
DECISION_DAYS = 7
STALE_DAYS = 14
# Une proposition non traitée depuis 2 jours est rappelée à son auteur.
PROPOSAL_DAYS = 2

RULES: dict[AlertRule, str] = {
    AlertRule.OVERDUE: "En retard",
    AlertRule.BLOCKED: "Bloqué",
    AlertRule.DUE_SOON: "Échéance proche",
    AlertRule.DECISION_PENDING: "Décision en attente",
    AlertRule.STALE: "Suivi non actualisé",
    AlertRule.MISSING_INFO: "Information manquante",
    AlertRule.PROPOSAL_PENDING: "Proposition à valider",
    AlertRule.MENTION: "Mention",
    AlertRule.TASK_ACTIVITY: "Tâche suivie",
    AlertRule.MILESTONE_AT_RISK: "Jalon à risque",
    AlertRule.MILESTONE_REFRAME: "Revue de cadrage",
    AlertRule.MINUTES_OVERDUE: "Relevé à diffuser",
    AlertRule.DECISION_REMINDER: "Relance de décision",
    AlertRule.ORPHAN_SUBJECT: "Sujet sans porteur",
    AlertRule.EVENT_CONTROL: "Contrôle d'événement",
    AlertRule.ENCOUNTER_FOLLOW_UP: "Rencontre à suivre",
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
    # Lot C : un rappel sur un projet ne va qu'aux personnes qui voient ce projet.
    member_of_user = {m.user_id: m for m in memberships}
    overrides = project_overrides(db, by_id)

    def allowed(project: Project) -> Callable[[uuid.UUID], bool]:
        if project.id not in overrides and project.id not in by_id:
            overrides.update(project_overrides(db, [project.id]))
        project_roles = overrides.get(project.id, {})

        def check(user_id: uuid.UUID) -> bool:
            m = member_of_user.get(user_id)
            return m is not None and can_see(m, project.private, project_roles)

        return check

    def add(
        users,
        rule: AlertRule,
        target_type: str,
        target_id,
        project: Project | None,
        title: str,
        detail: str,
    ):
        users = {u for u in users if u}
        if project is not None:
            users = set(filter(allowed(project), users))
        for user_id in users:
            rows.append(
                {
                    "id": uuid.uuid4(),
                    "space_id": space.id,
                    "user_id": user_id,
                    "rule": rule,
                    "target_type": target_type,
                    "target_id": target_id,
                    "project_id": project.id if project else None,
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
            # Tâches des projets ouverts, et tâches du suivi général (sans projet).
            or_(Task.project_id.in_(list(by_id)), Task.project_id.is_(None)),
        )
    ).all()
    for t in tasks:
        project = by_id.get(t.project_id) if t.project_id else None
        assignee = user_of.get(t.assignee_member_id) if t.assignee_member_id else None
        if project is not None:
            users = [
                assignee,
                user_of.get(project.owner_member_id) if project.owner_member_id else None,
            ]
            title = f"{t.title} · {project.title}"
        else:
            # Suivi général : la personne désignée, sinon les propriétaires de l'espace.
            users = [assignee] if assignee else list(owners)
            title = f"{t.title} · Suivi général"
        days = (t.due_date - today).days
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

    # Jalons (étape F2) : échéance proche, dépassée, ou à risque dans les trois semaines.
    milestones = db.scalars(
        select(Milestone).where(
            Milestone.space_id == space.id,
            Milestone.state == MilestoneState.PLANNED,
            Milestone.project_id.in_(list(by_id)),
        )
    ).all()
    linked: dict[uuid.UUID, list[Task]] = {}
    if milestones:
        for milestone_id, task in db.execute(
            select(MilestoneTask.milestone_id, Task)
            .join(Task, Task.id == MilestoneTask.task_id)
            .where(MilestoneTask.milestone_id.in_([m.id for m in milestones]))
        ).all():
            linked.setdefault(milestone_id, []).append(task)
    for m in milestones:
        project = by_id[m.project_id]
        users = [
            user_of.get(m.owner_member_id) if m.owner_member_id else None,
            user_of.get(project.owner_member_id) if project.owner_member_id else None,
        ]
        # Sans porteur ni responsable avec un compte : les propriétaires de l'espace.
        if not any(users):
            users = list(owners)
        title = f"◆ {m.title} · {project.title}"
        late, at_risk, reasons = risk(m, linked.get(m.id, []), today)
        days = (m.due_date - today).days
        if late:
            add(
                [*users, *owners],
                AlertRule.OVERDUE,
                "milestone",
                m.id,
                project,
                title,
                f"Jalon non atteint, prévu le {short_date(m.due_date)}",
            )
        elif at_risk:
            add(
                [*users, *owners] if m.critical else users,
                AlertRule.MILESTONE_AT_RISK,
                "milestone",
                m.id,
                project,
                title,
                f"Prévu le {short_date(m.due_date)} : " + ", ".join(reasons),
            )
        elif days in DUE_SOON_DAYS:
            add(
                users,
                AlertRule.DUE_SOON,
                "milestone",
                m.id,
                project,
                title,
                _due_detail(m.due_date, today),
            )

    # Réunions (étape F3) : relevé non diffusé 24 h après la fin de la réunion.
    now = utcnow()
    for meeting in db.scalars(
        select(Meeting).where(Meeting.space_id == space.id, Meeting.minutes_state != "sent")
    ).all():
        if not minutes_late(meeting, now):
            continue
        project = by_id.get(meeting.project_id) if meeting.project_id else None
        if meeting.project_id and project is None:
            continue  # projet clôturé : plus de rappel
        add(
            [meeting.created_by_id] if meeting.created_by_id else owners,
            AlertRule.MINUTES_OVERDUE,
            "meeting",
            meeting.id,
            project,
            meeting.title,
            "Relevé à diffuser : délai de 24 h dépassé depuis le "
            + short_date(_local_day(minutes_due(meeting), space)),
        )

    # Décisions (étape F3) : relance unique à mi-échéance, retard à escalader, sujet sans
    # porteur accepté depuis 30 jours. Une décision confidentielle ne va qu'à ses acteurs.
    for d in db.scalars(
        select(Decision).where(
            Decision.space_id == space.id,
            Decision.state.in_([DecisionState.DRAFT, DecisionState.OPEN]),
        )
    ).all():
        project = by_id.get(d.project_id) if d.project_id else None
        if d.project_id and project is None:
            continue
        executor = user_of.get(d.executor_member_id) if d.executor_member_id else None
        decider = user_of.get(d.decider_member_id) if d.decider_member_id else None
        title = f"⚖ {d.statement[:150]}"

        actors = {executor, decider, d.created_by_id, *owners}

        def to(users, d=d, actors=actors):
            users = {u for u in users if u}
            return users & actors if d.private else users

        if d.state == DecisionState.OPEN:
            mid = mid_term(d)
            if is_late(d, today):
                add(
                    to([executor, decider, *owners]),
                    AlertRule.OVERDUE,
                    "decision",
                    d.id,
                    project,
                    title,
                    f"Échéance du {short_date(d.due_date)} non tenue : à escalader vers "
                    "l'instance compétente si rien ne la justifie",
                )
            elif mid is not None and today >= mid and d.reminded_on is None:
                d.reminded_on = today
                add(
                    to([executor] if executor else [d.created_by_id]),
                    AlertRule.DECISION_REMINDER,
                    "decision",
                    d.id,
                    project,
                    title,
                    f"Mi-échéance : à exécuter avant le {short_date(d.due_date)}",
                )
        if not accepted(d) and (today - _local_day(d.created_at, space)).days >= ORPHAN_DAYS:
            add(
                to(owners),
                AlertRule.ORPHAN_SUBJECT,
                "decision",
                d.id,
                project,
                title,
                f"Sans porteur accepté depuis {(today - _local_day(d.created_at, space)).days}"
                " jours : attribution formelle requise",
            )

    # Étape F6 : contrôles d'événement (J−10, veille, contacts sous 5 jours ouvrés, bilan
    # sous 10 jours) dus la veille, le jour même ou dépassés.
    from pilot_api.routers.pilotage import event_controls, event_projects

    for project, details in event_projects(db, space.id):
        # Un événement terminé garde ses contrôles d'après (contacts, bilan) ; un événement
        # annulé n'en a plus.
        if project.status == ProjectStatus.CANCELLED:
            continue
        responsible = user_of.get(project.owner_member_id) if project.owner_member_id else None
        for control in event_controls(project, details, today):
            if control.done_at is not None or control.due_date is None:
                continue
            days = (control.due_date - today).days
            if days > 1 or days < -30:
                continue
            add(
                [responsible] if responsible else owners,
                AlertRule.EVENT_CONTROL,
                "project",
                project.id,
                project,
                project.title,
                f"{control.label} : "
                + ("en retard depuis le " if days < 0 else "à faire pour le ")
                + short_date(control.due_date),
            )

    # Rencontres : dossier à préparer 48 h avant ; rencontre passée sans compte rendu ou sans
    # action suivante datée (REL03).
    from pilot_api.models import Encounter, EncounterTriage

    for e in db.scalars(
        select(Encounter).where(
            Encounter.space_id == space.id,
            Encounter.closed_at.is_(None),
            Encounter.triage == EncounterTriage.ACCEPT,
            Encounter.starts_on.is_not(None),
        )
    ).all():
        target = user_of.get(e.owner_member_id) if e.owner_member_id else e.created_by_id
        end = e.ends_on or e.starts_on
        if e.dossier_ready_at is None and 0 <= (e.starts_on - today).days <= 2:
            add(
                [target],
                AlertRule.ENCOUNTER_FOLLOW_UP,
                "encounter",
                e.id,
                None,
                e.title,
                "Dossier à préparer avant le " + short_date(e.starts_on),
            )
        elif end < today and not (e.report and e.next_action and e.next_action_date):
            add(
                [target],
                AlertRule.ENCOUNTER_FOLLOW_UP,
                "encounter",
                e.id,
                None,
                e.title,
                "Rencontre du " + short_date(end) + " sans compte rendu ou sans suite datée",
            )

    # Propositions de la boîte de mise à jour restées sans décision : rappel à leur auteur.
    pending = db.execute(
        select(Proposal, UpdateRequest.author_id)
        .join(UpdateRequest, UpdateRequest.id == Proposal.request_id)
        .where(Proposal.space_id == space.id, Proposal.state.in_(OPEN_PROPOSAL_STATES))
    ).all()
    writers = {m.user_id for m in memberships if m.role != Role.READER}
    for proposal, author_id in pending:
        waited = (today - _local_day(proposal.created_at, space)).days
        if waited < PROPOSAL_DAYS or author_id not in writers:
            continue
        project = db.get(Project, proposal.project_id) if proposal.project_id else None
        add(
            [author_id],
            AlertRule.PROPOSAL_PENDING,
            "proposal",
            proposal.id,
            project,
            project.title if project else "Mise à jour : projet à préciser",
            f"Proposition en attente depuis {waited} jours ({proposal.source_label})",
        )

    if not rows:
        return 0
    created = db.execute(
        insert(Alert)
        .values(rows)
        .on_conflict_do_nothing(constraint="uq_alerts_user_rule_target_day")
        .returning(Alert.id)
    ).all()
    return len(created)


def notify(
    db: Session,
    space: Space,
    user_ids,
    rule: AlertRule,
    task: Task,
    detail: str,
) -> None:
    """Notification déclenchée par un événement (mention, activité sur une tâche suivie).
    Une seule alerte par personne, règle et tâche dans la journée : un nouvel événement la
    remet à jour et la signale de nouveau comme non lue (pas d'avalanche d'alertes)."""
    users = (
        users_who_can_see(db, db.get(Project, task.project_id), user_ids)
        if (task.project_id)
        else {u for u in user_ids if u}
    )
    if not users:
        return
    today = local_now(space).date()
    now = utcnow()
    for user_id in users:
        stmt = insert(Alert).values(
            id=uuid.uuid4(),
            space_id=space.id,
            user_id=user_id,
            rule=rule,
            target_type="task",
            target_id=task.id,
            project_id=task.project_id,
            alert_date=today,
            title=task.title[:200],
            detail=detail[:300],
            created_at=now,
        )
        db.execute(
            stmt.on_conflict_do_update(
                constraint="uq_alerts_user_rule_target_day",
                set_={
                    "detail": stmt.excluded.detail,
                    "title": stmt.excluded.title,
                    "read_at": None,
                    "created_at": now,
                },
            )
        )


def notify_milestone(
    db: Session,
    space: Space,
    user_ids,
    rule: AlertRule,
    milestone: Milestone,
    project: Project,
    detail: str,
) -> None:
    """Alerte déclenchée par un événement sur un jalon (ex. deuxième report)."""
    users = users_who_can_see(db, project, user_ids)
    today = local_now(space).date()
    now = utcnow()
    for user_id in users:
        stmt = insert(Alert).values(
            id=uuid.uuid4(),
            space_id=space.id,
            user_id=user_id,
            rule=rule,
            target_type="milestone",
            target_id=milestone.id,
            project_id=project.id,
            alert_date=today,
            title=f"◆ {milestone.title} · {project.title}"[:200],
            detail=detail[:300],
            created_at=now,
        )
        db.execute(
            stmt.on_conflict_do_update(
                constraint="uq_alerts_user_rule_target_day",
                set_={"detail": stmt.excluded.detail, "read_at": None, "created_at": now},
            )
        )


def preference_for(db: Session, user_id: uuid.UUID, space_id: uuid.UUID) -> AlertPreference:
    pref = db.scalar(
        select(AlertPreference).where(
            AlertPreference.user_id == user_id, AlertPreference.space_id == space_id
        )
    )
    if pref is None:
        # Deux premières ouvertures simultanées ne créent pas de doublon (ni d'erreur).
        db.execute(
            insert(AlertPreference)
            .values(
                id=uuid.uuid4(),
                user_id=user_id,
                space_id=space_id,
                disabled_rules=[],
                email_digest=True,
                digest_hour=7,
            )
            .on_conflict_do_nothing(constraint="uq_alert_preferences")
        )
        pref = db.scalar(
            select(AlertPreference).where(
                AlertPreference.user_id == user_id, AlertPreference.space_id == space_id
            )
        )
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
    # Lot C : rien sur un projet que cette personne ne voit pas (ou plus). Appliqué ici pour
    # tous les envois : récapitulatif quotidien et aperçu.
    membership = db.scalar(
        select(Membership).where(
            Membership.space_id == space.id,
            Membership.user_id == user_id,
            Membership.status == MembershipStatus.ACTIVE,
        )
    )
    if membership is None:
        return []
    projects = visible_project_ids(db, membership)
    if projects is not None:
        alerts = [a for a in alerts if a.project_id is None or a.project_id in projects]
    return sorted(alerts, key=lambda a: (RULE_ORDER.index(a.rule), a.title))


RULE_COLORS: dict[AlertRule, str] = {
    AlertRule.OVERDUE: "#ff8fa3",
    AlertRule.BLOCKED: "#ff8fa3",
    AlertRule.DUE_SOON: "#fcd56a",
    AlertRule.DECISION_PENDING: "#c4b5fd",
    AlertRule.STALE: "#8f97ac",
    AlertRule.MISSING_INFO: "#8f97ac",
    AlertRule.PROPOSAL_PENDING: "#7dd3fc",
    AlertRule.MENTION: "#ffa3c4",
    AlertRule.TASK_ACTIVITY: "#7ff0ff",
    AlertRule.MILESTONE_AT_RISK: "#fcd56a",
    AlertRule.MILESTONE_REFRAME: "#ff8fa3",
    AlertRule.MINUTES_OVERDUE: "#fcd56a",
    AlertRule.DECISION_REMINDER: "#c4b5fd",
    AlertRule.ORPHAN_SUBJECT: "#ff8fa3",
    AlertRule.EVENT_CONTROL: "#fcd56a",
    AlertRule.ENCOUNTER_FOLLOW_UP: "#7dd3fc",
}


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
        if alert.target_type == "proposal":
            url = f"{base}/espaces/{space.id}/mises-a-jour"
        elif alert.project_id is None:
            url = f"{base}/espaces/{space.id}"  # ancienne tâche sans projet
        else:
            url = f"{base}/espaces/{space.id}/projets/{alert.project_id}"
        if alert.target_type == "task":
            url += f"?tache={alert.target_id}"
        lines_text.append(f"- [{RULES[alert.rule]}] {alert.title} : {alert.detail}\n  {url}")
        rows_html.append(
            "<tr><td style='padding:12px 0;border-top:1px solid #23263a'>"
            f"{pill(RULES[alert.rule], RULE_COLORS[alert.rule])}"
            f"<div style='margin-top:6px'><a href='{html.escape(url)}' style='color:#eef1fb;"
            f"font-size:15px;font-weight:600;text-decoration:none'>{html.escape(alert.title)}"
            "</a></div>"
            f"<div style='margin-top:2px;font-size:13px;color:#8f97ac'>"
            f"{html.escape(alert.detail)}</div></td></tr>"
        )
    day = short_date(today).rstrip(".")
    intro = f"Bonjour {user.display_name}, voici ce qui demande votre attention le {day}."
    text = (
        intro
        + "\n\n"
        + ("\n".join(lines_text) or "Aucun rappel aujourd'hui.")
        + f"\n\nOuvrir PILOT : {link}\n"
    )
    rows = "".join(rows_html) or (
        "<tr><td style='padding:12px 0;border-top:1px solid #23263a;color:#8f97ac'>"
        "Aucun rappel aujourd'hui : tout est sous contrôle.</td></tr>"
    )
    page = render_email(
        kicker=f"Récapitulatif du {day} · {space.name}",
        title=(
            f"{len(alerts)} sujet{'s' if len(alerts) > 1 else ''} à suivre aujourd'hui"
            if alerts
            else "Aucun rappel aujourd'hui"
        ),
        paragraphs=[intro],
        extra_html=(
            "<table role='presentation' width='100%' cellpadding='0' cellspacing='0' "
            f"style='margin:6px 0 4px;font-family:Helvetica,Arial,sans-serif'>{rows}</table>"
        ),
        button_label="Ouvrir PILOT",
        button_url=link,
        footer="Vous recevez ce récapitulatif car il est activé dans vos préférences d'alertes "
        "PILOT.",
        preheader=intro,
    )
    return subject, page, text


# Domaines réservés aux essais : jamais d'envoi (les comptes de test n'ont pas de vraie boîte).
TEST_DOMAINS = ("example.com", "example.org", "example.net", "exemple.com")
TEST_SUFFIXES = (".test", ".example", ".invalid", ".localhost")


def is_test_address(email: str) -> bool:
    domain = email.rsplit("@", 1)[-1].lower()
    return domain in TEST_DOMAINS or domain.endswith(TEST_SUFFIXES)


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
            if is_test_address(user.email):
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
