"""Pilotage (étape F6, cahier V2 VIS02–VIS04, CAP02, DEC04 et contrôles d'événement).

- Indicateurs de référence : chaque résultat montre sa période, son périmètre, sa cible, le
  nombre de cas (numérateur / dénominateur) et sa date de calcul. Un dénominateur nul donne
  « non calculable », pas 100 % ; les annulations sont comptées à part, jamais comme réussies ;
  les jalons sont jugés sur leur date d'origine (un report ne rend pas le délai « bon »).
  Une donnée que PILOT ne mesure pas est dite « non mesurée » plutôt qu'inventée.
- Charge et capacité : heures estimées des tâches ouvertes, par personne et par semaine
  d'échéance, face à la capacité saisie (même unité, même période). Sans capacité : « Capacité
  à vérifier » ; une tâche sans estimation est comptée à part, jamais pour zéro.
- Contrôles d'événement : cibles confirmées à J−10, répétition la veille, contacts transmis
  sous cinq jours ouvrés, bilan chiffré sous dix jours.
- Dossier d'arbitrage d'une décision : contexte, faits, impacts, options, recommandation,
  risques et décision attendue ; il ne se soumet que complet. Les droits de l'application ne
  donnent aucun mandat pour trancher, signer ou dépasser un budget.
"""

import uuid
from datetime import date, datetime, time, timedelta
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from pilot_api.access import ensure_writer, visible_project_ids
from pilot_api.audit import record
from pilot_api.decision_rules import accepted, missing_fields, orphan_age
from pilot_api.deps import CurrentMembership, DbSession, OwnerMembership
from pilot_api.models import (
    CLOSED_TASK_STATUSES,
    Decision,
    DecisionState,
    Encounter,
    EventDetails,
    Meeting,
    MemberCapacity,
    Membership,
    MembershipStatus,
    Milestone,
    MilestoneState,
    OccurrenceState,
    Project,
    ProjectKind,
    Role,
    Routine,
    RoutineOccurrence,
    Space,
    Task,
    utcnow,
)
from pilot_api.routers.decisions import _load as load_decision
from pilot_api.routers.decisions import _one as decision_one
from pilot_api.routers.decisions import _visible_filter as decision_filter
from pilot_api.routers.projects import CONFLICT, load_project, today_in
from pilot_api.schemas import DecisionOut

router = APIRouter(prefix="/api/spaces/{space_id}", tags=["pilotage"])

Text = Annotated[str, StringConstraints(strip_whitespace=True, max_length=4000)]


# ---------- Outils de dates ----------


def local_day(moment: datetime, space: Space) -> date:
    from zoneinfo import ZoneInfo

    return moment.astimezone(ZoneInfo(space.timezone)).date()


def add_workdays(day: date, count: int) -> date:
    """`count` jours ouvrés (lundi–vendredi) après `day`. Les jours fériés ne sont pas
    encore pris en compte."""
    current = day
    while count > 0:
        current += timedelta(days=1)
        if current.weekday() < 5:
            count -= 1
    return current


# ---------- Indicateurs (VIS02, VIS03) ----------

# Cibles du cahier (fiches de référence) ; modifiables par l'espace.
INDICATORS: dict[str, dict[str, Any]] = {
    "decisions_complete": {
        "label": "Décisions complètes",
        "measure": "Part des décisions avec responsable nommé, échéance et critère observable",
        "target": 100,
        "comparator": ">=",
        "unit": "%",
    },
    "decisions_on_time": {
        "label": "Décisions à l'heure",
        "measure": "Décisions exécutées à temps parmi celles arrivées à échéance",
        "target": 85,
        "comparator": ">=",
        "unit": "%",
    },
    "milestones_on_time": {
        "label": "Jalons à l'heure",
        "measure": "Jalons atteints à leur date engagée d'origine parmi ceux arrivés à échéance",
        "target": 80,
        "comparator": ">=",
        "unit": "%",
    },
    "minutes_24h": {
        "label": "Relevés diffusés",
        "measure": "Relevés déclarés envoyés dans les 24 h après la réunion",
        "target": 100,
        "comparator": ">=",
        "unit": "%",
    },
    "dossiers_48h": {
        "label": "Préparation des dossiers",
        "measure": "Dossiers de rendez-vous prêts au moins 48 h avant",
        "target": 100,
        "comparator": ">=",
        "unit": "%",
    },
    "orphan_subjects": {
        "label": "Sujets sans porteur",
        "measure": "Sujets ouverts sans porteur accepté depuis plus de 30 jours",
        "target": 0,
        "comparator": "<=",
        "unit": "count",
    },
    "event_contacts": {
        "label": "Contacts événementiels",
        "measure": "Événements dont les contacts qualifiés ont été transmis sous 5 jours ouvrés",
        "target": 100,
        "comparator": ">=",
        "unit": "%",
    },
    "monthly_report": {
        "label": "Reporting mensuel",
        "measure": "Mois dont la synthèse d'exécution a été faite avant le 5",
        "target": 100,
        "comparator": ">=",
        "unit": "%",
    },
    "strategic_time": {
        "label": "Temps stratégique",
        "measure": "Temps catégorisé stratégique sur temps mesuré",
        "target": 70,
        "comparator": ">=",
        "unit": "%",
    },
}


class IndicatorOut(BaseModel):
    key: str
    label: str
    measure: str
    target: float
    comparator: Literal[">=", "<="]
    unit: Literal["%", "count"]
    numerator: int | None
    denominator: int | None
    value: float | None
    status: Literal["ok", "below", "na"]
    na_reason: str | None
    cancelled: int
    note: str | None


class IndicatorsOut(BaseModel):
    start: date
    end: date
    scope: str
    computed_at: datetime
    indicators: list[IndicatorOut]


class TargetsIn(BaseModel):
    targets: Annotated[dict[str, Annotated[float, Field(ge=0, le=100)]], Field(max_length=20)]


def _result(
    space: Space,
    key: str,
    numerator: int | None,
    denominator: int | None,
    *,
    cancelled: int = 0,
    na: str | None = None,
    note: str | None = None,
    count: int | None = None,
) -> IndicatorOut:
    spec = INDICATORS[key]
    target = float((space.indicator_targets or {}).get(key, spec["target"]))
    value: float | None = None
    if na is None:
        if spec["unit"] == "count":
            value = float(count or 0)
        elif not denominator:
            na = "Non calculable : aucun cas sur la période"
        else:
            value = round(100 * (numerator or 0) / denominator, 1)
    if value is None:
        status = "na"
    elif spec["comparator"] == ">=":
        status = "ok" if value >= target else "below"
    else:
        status = "ok" if value <= target else "below"
    return IndicatorOut(
        key=key,
        label=spec["label"],
        measure=spec["measure"],
        target=target,
        comparator=spec["comparator"],
        unit=spec["unit"],
        numerator=numerator,
        denominator=denominator,
        value=value,
        status=status,
        na_reason=na,
        cancelled=cancelled,
        note=note,
    )


def compute_indicators(
    db: Session, membership: Membership, start: date, end: date
) -> list[IndicatorOut]:
    space = membership.space
    today = today_in(space)
    until = min(end, today)
    visible = visible_project_ids(db, membership)

    def project_ok(project_id: uuid.UUID | None) -> bool:
        return project_id is None or visible is None or project_id in visible

    results: list[IndicatorOut] = []

    decisions = list(db.scalars(select(Decision).where(decision_filter(db, membership))))
    created = [
        d
        for d in decisions
        if start <= local_day(d.created_at, space) <= end and d.state != DecisionState.CANCELLED
    ]
    complete = [d for d in created if not missing_fields(d)]
    results.append(
        _result(
            space,
            "decisions_complete",
            len(complete),
            len(created),
            cancelled=len(
                [
                    d
                    for d in decisions
                    if start <= local_day(d.created_at, space) <= end
                    and d.state == DecisionState.CANCELLED
                ]
            ),
        )
    )

    due = [d for d in decisions if d.due_date and start <= d.due_date <= until]
    due_live = [d for d in due if d.state != DecisionState.CANCELLED]
    on_time = [
        d
        for d in due_live
        if d.state == DecisionState.DONE
        and d.closed_at is not None
        and local_day(d.closed_at, space) <= d.due_date
    ]
    results.append(
        _result(
            space,
            "decisions_on_time",
            len(on_time),
            len(due_live),
            cancelled=len(due) - len(due_live),
        )
    )

    milestones = [
        m
        for m in db.scalars(select(Milestone).where(Milestone.space_id == space.id))
        if project_ok(m.project_id)
    ]
    committed = [m for m in milestones if start <= (m.original_due_date or m.due_date) <= until]
    live = [m for m in committed if m.state != MilestoneState.CANCELLED]
    held = [
        m
        for m in live
        if m.state == MilestoneState.REACHED
        and m.closed_at is not None
        and local_day(m.closed_at, space) <= (m.original_due_date or m.due_date)
    ]
    results.append(
        _result(
            space,
            "milestones_on_time",
            len(held),
            len(live),
            cancelled=len(committed) - len(live),
            note="Jugés sur la date d'origine : un jalon reporté n'est pas « à l'heure ».",
        )
    )

    now = utcnow()
    meetings = [
        m
        for m in db.scalars(select(Meeting).where(Meeting.space_id == space.id))
        if project_ok(m.project_id)
        and start <= local_day(m.ended_at, space) <= end
        and m.ended_at + timedelta(hours=24) <= now
    ]
    sent = [
        m
        for m in meetings
        if m.minutes_sent_at is not None and m.minutes_sent_at <= m.ended_at + timedelta(hours=24)
    ]
    results.append(
        _result(
            space,
            "minutes_24h",
            len(sent),
            len(meetings),
            note="« Envoyé » est une déclaration : PILOT ne prouve pas la remise.",
        )
    )

    encounters = [
        e
        for e in db.scalars(
            select(Encounter).where(
                Encounter.space_id == space.id,
                Encounter.starts_on.is_not(None),
                Encounter.starts_on.between(start, until),
            )
        )
        if project_ok(e.project_id) and (not e.private or _encounter_actor(e, membership))
    ]
    ready = [
        e
        for e in encounters
        if e.dossier_ready_at is not None
        and e.dossier_ready_at
        <= datetime.combine(e.starts_on, time(0, 0), tzinfo=e.dossier_ready_at.tzinfo)
        - timedelta(hours=48)
    ]
    results.append(_result(space, "dossiers_48h", len(ready), len(encounters)))

    orphans = [
        d
        for d in decisions
        if d.state in (DecisionState.DRAFT, DecisionState.OPEN)
        and not accepted(d)
        and (orphan_age(d, today) or 0) > 30
    ]
    results.append(
        _result(space, "orphan_subjects", None, None, count=len(orphans), note="Au jour du calcul.")
    )

    due_events = []
    for project, details in event_projects(db, space.id):
        if not project_ok(project.id):
            continue
        end_day = project.end_date or project.start_date
        deadline = add_workdays(end_day, 5)
        if start <= end_day <= end and deadline <= today:
            done_at = ((details.controls or {}).get("contacts_5") or {}).get("done_at")
            due_events.append(done_at is not None and date.fromisoformat(done_at[:10]) <= deadline)
    results.append(_result(space, "event_contacts", sum(due_events), len(due_events)))

    report = db.scalars(
        select(Routine).where(Routine.space_id == space.id, Routine.profile == "synthese_execution")
    ).first()
    if report is None:
        results.append(
            _result(
                space,
                "monthly_report",
                None,
                None,
                na="Non mesuré : ajoutez la routine « Produire la synthèse d'exécution ».",
            )
        )
    else:
        months, ok = 0, 0
        done_days = [
            local_day(o.closed_at, space)
            for o in db.scalars(
                select(RoutineOccurrence).where(
                    RoutineOccurrence.routine_id == report.id,
                    RoutineOccurrence.state == OccurrenceState.DONE,
                    RoutineOccurrence.closed_at.is_not(None),
                )
            )
        ]
        cursor = date(start.year, start.month, 1)
        while cursor <= until:
            if start <= cursor.replace(day=5) <= until:
                months += 1
                if any(
                    d.year == cursor.year and d.month == cursor.month and d.day < 5
                    for d in done_days
                ):
                    ok += 1
            cursor = date(cursor.year + cursor.month // 12, cursor.month % 12 + 1, 1)
        results.append(_result(space, "monthly_report", ok, months))

    results.append(
        _result(
            space,
            "strategic_time",
            None,
            None,
            na="Non mesuré : PILOT ne suit pas le temps passé (rien n'est déduit des connexions).",
        )
    )
    return results


@router.get("/indicators")
def get_indicators(
    membership: CurrentMembership,
    db: DbSession,
    start: date | None = None,
    end: date | None = None,
) -> IndicatorsOut:
    if membership.role == Role.GUEST:
        raise HTTPException(403, "Les indicateurs de l'espace ne sont pas ouverts aux invités.")
    today = today_in(membership.space)
    end = end or today
    start = start or end - timedelta(days=89)
    if end < start or (end - start).days > 400:
        raise HTTPException(422, "Période de 400 jours au plus.")
    scope = (
        "Tout l'espace"
        if membership.role == Role.OWNER
        else "Projets et décisions que vous pouvez consulter"
    )
    return IndicatorsOut(
        start=start,
        end=end,
        scope=scope,
        computed_at=utcnow(),
        indicators=compute_indicators(db, membership, start, end),
    )


@router.put("/indicators/targets")
def set_targets(body: TargetsIn, membership: OwnerMembership, db: DbSession) -> IndicatorsOut:
    unknown = set(body.targets) - set(INDICATORS)
    if unknown:
        raise HTTPException(422, "Indicateur inconnu.")
    space = db.get(Space, membership.space_id, with_for_update=True)
    before = dict(space.indicator_targets or {})
    space.indicator_targets = {**before, **body.targets}
    record(
        db,
        action="space.indicator_targets",
        actor_id=membership.user_id,
        space_id=space.id,
        target_type="space",
        target_id=space.id,
        before=before,
        after=space.indicator_targets,
    )
    db.commit()
    return get_indicators(membership, db)


# ---------- Charge et capacité (CAP02) ----------


class CapacityWeek(BaseModel):
    start: date
    hours: float
    unestimated: int
    tasks: int
    over: bool | None


class CapacityPerson(BaseModel):
    member_id: uuid.UUID
    name: str
    capacity: float | None
    capacity_note: str | None
    capacity_updated_at: datetime | None
    late_hours: float
    late_unestimated: int
    undated_hours: float
    undated_unestimated: int
    weeks: list[CapacityWeek]
    sustained_overload: bool


class CapacityOut(BaseModel):
    weeks: list[date]
    people: list[CapacityPerson]
    note: str


class CapacityIn(BaseModel):
    hours_per_week: Annotated[float, Field(ge=0, le=168)] | None = None
    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)] | None = None


def _monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


@router.get("/capacity")
def get_capacity(membership: CurrentMembership, db: DbSession, weeks: int = 6) -> CapacityOut:
    if membership.role == Role.GUEST:
        raise HTTPException(403, "La charge de l'équipe n'est pas ouverte aux invités.")
    weeks = max(1, min(weeks, 12))
    today = today_in(membership.space)
    first = _monday(today)
    mondays = [first + timedelta(weeks=n) for n in range(weeks)]
    last = mondays[-1] + timedelta(days=6)
    visible = visible_project_ids(db, membership)
    members = list(
        db.scalars(
            select(Membership)
            .options(selectinload(Membership.user))
            .where(
                Membership.space_id == membership.space_id,
                Membership.status == MembershipStatus.ACTIVE,
                Membership.role != Role.GUEST,
            )
            .order_by(Membership.created_at)
        )
    )
    capacities = {
        c.member_id: c
        for c in db.scalars(
            select(MemberCapacity).where(MemberCapacity.space_id == membership.space_id)
        )
    }
    query = select(Task).where(
        Task.space_id == membership.space_id,
        Task.assignee_member_id.is_not(None),
        Task.status.not_in(CLOSED_TASK_STATUSES),
    )
    if visible is not None:
        query = query.where(Task.project_id.in_(visible))
    tasks = list(db.scalars(query))
    people = []
    for m in members:
        mine = [t for t in tasks if t.assignee_member_id == m.id]
        cap = capacities.get(m.id)
        hours = cap.hours_per_week if cap else None

        def bucket(items: list[Task]) -> tuple[float, int]:
            return (
                round(sum(t.estimate_hours or 0 for t in items), 1),
                len([t for t in items if t.estimate_hours is None]),
            )

        late_h, late_u = bucket([t for t in mine if t.due_date and t.due_date < first])
        undated_h, undated_u = bucket([t for t in mine if t.due_date is None])
        week_rows = []
        streak = best = 0
        for monday in mondays:
            items = [
                t for t in mine if t.due_date and monday <= t.due_date <= monday + timedelta(days=6)
            ]
            load, unestimated = bucket(items)
            over = None if hours is None else load > hours
            streak = streak + 1 if over else 0
            best = max(best, streak)
            week_rows.append(
                CapacityWeek(
                    start=monday, hours=load, unestimated=unestimated, tasks=len(items), over=over
                )
            )
        people.append(
            CapacityPerson(
                member_id=m.id,
                name=m.user.display_name if m.user else m.email,
                capacity=hours,
                capacity_note=cap.note if cap else None,
                capacity_updated_at=cap.updated_at if cap else None,
                late_hours=late_h,
                late_unestimated=late_u,
                undated_hours=undated_h,
                undated_unestimated=undated_u,
                weeks=week_rows,
                sustained_overload=best > 3,
            )
        )
    del last
    return CapacityOut(
        weeks=mondays,
        people=people,
        note=(
            "Charge = heures estimées des tâches ouvertes, rangées par semaine d'échéance. "
            "Une tâche sans estimation est comptée à part. Surcharge durable : plus de trois "
            "semaines consécutives au-dessus de la capacité."
        ),
    )


@router.put("/capacity/{member_id}")
def set_capacity(
    member_id: uuid.UUID, body: CapacityIn, membership: CurrentMembership, db: DbSession
) -> CapacityOut:
    """Un propriétaire saisit la capacité de chacun ; chacun peut saisir la sienne."""
    if membership.role != Role.OWNER and member_id != membership.id:
        raise HTTPException(403, "Seul un propriétaire saisit la capacité d'une autre personne.")
    member = db.get(Membership, member_id)
    if member is None or member.space_id != membership.space_id:
        raise HTTPException(404, "Membre introuvable.")
    cap = db.get(MemberCapacity, member_id, with_for_update=True)
    before = {"hours_per_week": cap.hours_per_week} if cap else None
    if body.hours_per_week is None:
        if cap is not None:
            db.delete(cap)
    else:
        if cap is None:
            cap = MemberCapacity(member_id=member_id, space_id=membership.space_id)
            db.add(cap)
        cap.hours_per_week = body.hours_per_week
        cap.note = body.note or None
        cap.updated_by_id = membership.user_id
        cap.updated_at = utcnow()
    record(
        db,
        action="member.capacity",
        actor_id=membership.user_id,
        space_id=membership.space_id,
        target_type="membership",
        target_id=member_id,
        before=before,
        after={"hours_per_week": body.hours_per_week},
    )
    db.commit()
    return get_capacity(membership, db)


# ---------- Contrôles d'événement ----------


def event_projects(db: Session, space_id: uuid.UUID) -> list[tuple[Project, EventDetails]]:
    """Projets dont le type est de nature « événement » (avec une date de début), et leurs
    informations d'événement (vides tant que rien n'a été saisi)."""
    from pilot_api.models import ProjectType

    rows = db.execute(
        select(Project, EventDetails)
        .join(ProjectType, ProjectType.id == Project.project_type_id)
        .outerjoin(EventDetails, EventDetails.project_id == Project.id)
        .where(
            Project.space_id == space_id,
            ProjectType.kind == ProjectKind.EVENT,
            Project.start_date.is_not(None),
        )
    ).all()
    return [(p, d if d is not None else EventDetails(project_id=p.id)) for p, d in rows]


EVENT_CONTROLS = [
    ("targets_j10", "Confirmations des cibles prioritaires vérifiées", "start", -10),
    ("rehearsal_j1", "Répétition technique faite et responsable sur place désigné", "start", -1),
    ("contacts_5", "Contacts qualifiés transmis (sous 5 jours ouvrés)", "end", 5),
    ("report_10", "Bilan chiffré produit (sous 10 jours)", "end", 10),
]


class EventControlOut(BaseModel):
    key: str
    label: str
    due_date: date | None
    done_at: datetime | None
    done_by: str | None
    note: str | None
    late: bool


class EventControlIn(BaseModel):
    done: bool
    note: Text | None = None


def control_due(key: str, project: Project) -> date | None:
    if project.start_date is None:
        return None
    for k, _label, anchor, offset in EVENT_CONTROLS:
        if k != key:
            continue
        if anchor == "start":
            return project.start_date + timedelta(days=offset)
        end_day = project.end_date or project.start_date
        return (
            add_workdays(end_day, offset)
            if key == "contacts_5"
            else end_day + timedelta(days=offset)
        )
    return None


def event_controls(project: Project, details: EventDetails, today: date) -> list[EventControlOut]:
    stored = details.controls or {}
    out = []
    for key, label, _anchor, _offset in EVENT_CONTROLS:
        entry = stored.get(key) or {}
        due = control_due(key, project)
        done_at = datetime.fromisoformat(entry["done_at"]) if entry.get("done_at") else None
        out.append(
            EventControlOut(
                key=key,
                label=label,
                due_date=due,
                done_at=done_at,
                done_by=entry.get("by"),
                note=entry.get("note"),
                late=done_at is None and due is not None and due < today,
            )
        )
    return out


def _event(db: Session, membership: Membership, project_id: uuid.UUID, write: bool):
    project = load_project(db, membership, project_id, write=write)
    details = db.get(EventDetails, project.id, with_for_update=write)
    is_event = project.project_type is not None and project.project_type.kind == ProjectKind.EVENT
    if details is None and is_event:
        details = EventDetails(project_id=project.id)
        if write:
            db.add(details)
            db.flush()
    if details is None:
        raise HTTPException(404, "Ce projet n'est pas un événement.")
    return project, details


@router.get("/projects/{project_id}/event-controls")
def get_event_controls(
    project_id: uuid.UUID, membership: CurrentMembership, db: DbSession
) -> list[EventControlOut]:
    project, details = _event(db, membership, project_id, write=False)
    return event_controls(project, details, today_in(membership.space))


@router.put("/projects/{project_id}/event-controls/{key}")
def set_event_control(
    project_id: uuid.UUID,
    key: str,
    body: EventControlIn,
    membership: CurrentMembership,
    db: DbSession,
) -> list[EventControlOut]:
    if key not in {k for k, *_ in EVENT_CONTROLS}:
        raise HTTPException(404, "Contrôle inconnu.")
    project, details = _event(db, membership, project_id, write=True)
    controls = dict(details.controls or {})
    if body.done:
        name = membership.user.display_name if membership.user else membership.email
        controls[key] = {"done_at": utcnow().isoformat(), "by": name, "note": body.note or None}
    else:
        controls.pop(key, None)
    details.controls = controls
    project.updated_at = utcnow()
    record(
        db,
        action="project.event_control",
        actor_id=membership.user_id,
        space_id=project.space_id,
        target_type="project",
        target_id=project.id,
        after={"control": key, "done": body.done, "note": body.note},
    )
    db.commit()
    return event_controls(project, details, today_in(membership.space))


# ---------- Dossier d'arbitrage (DEC04) ----------

ARBITRATION_FIELDS = {
    "context": "contexte",
    "facts": "faits",
    "impact": "impact délai, coût ou capacité",
    "recommendation": "recommandation",
    "risks": "risques",
    "expected_decision": "décision attendue",
}


class ArbitrationOption(BaseModel):
    label: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    consequence: Text | None = None


class ArbitrationIn(BaseModel):
    version: int
    context: Text | None = None
    facts: Text | None = None
    impact_delay: Text | None = None
    impact_cost: Text | None = None
    impact_capacity: Text | None = None
    options: Annotated[list[ArbitrationOption], Field(max_length=3)] = []
    recommendation: Text | None = None
    risks: Text | None = None
    expected_decision: Text | None = None
    # Soumettre exige un dossier complet ; sinon le dossier reste en préparation.
    submit: bool = False


def arbitration_missing(data: dict[str, Any]) -> list[str]:
    missing = []
    for key, label in ARBITRATION_FIELDS.items():
        if key == "impact":
            if not any(data.get(k) for k in ("impact_delay", "impact_cost", "impact_capacity")):
                missing.append(label)
        elif not data.get(key):
            missing.append(label)
    if len(data.get("options") or []) < 2:
        missing.append("au moins deux options")
    return missing


@router.put("/decisions/{decision_id}/arbitration")
def set_arbitration(
    decision_id: uuid.UUID, body: ArbitrationIn, membership: CurrentMembership, db: DbSession
) -> DecisionOut:
    decision = load_decision(db, membership, decision_id)
    if decision.version != body.version:
        raise HTTPException(409, CONFLICT)
    if decision.project_id is not None:
        ensure_writer(db, membership, db.get(Project, decision.project_id))
    data = body.model_dump(exclude={"version", "submit"}, mode="json")
    data = {k: v for k, v in data.items() if v not in (None, "", [])}
    if body.submit:
        missing = arbitration_missing(data)
        if missing:
            raise HTTPException(422, "Dossier incomplet, il manque : " + ", ".join(missing) + ".")
    decision.arbitration = data or None
    if body.submit and decision.arbitration_submitted_at is None:
        decision.arbitration_submitted_at = utcnow()
    elif not body.submit:
        decision.arbitration_submitted_at = None
    decision.version += 1
    record(
        db,
        action="decision.arbitration_submitted" if body.submit else "decision.arbitration_saved",
        actor_id=membership.user_id,
        space_id=decision.space_id,
        target_type="decision",
        target_id=decision.id,
        after={"decision": decision.statement[:200], "options": len(data.get("options") or [])},
    )
    db.commit()
    return decision_one(db, membership, decision.id)


def _encounter_actor(encounter: Encounter, membership: Membership) -> bool:
    return (
        membership.role == Role.OWNER
        or membership.id
        in (
            encounter.owner_member_id,
            encounter.follow_owner_member_id,
        )
        or encounter.created_by_id == membership.user_id
    )
