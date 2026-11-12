"""Routines de pilotage et vues « Ma journée » / « Ma semaine » (étape F5, cahier V2 RIT01–RIT07,
VIS01).

Une routine est un modèle (finalité, fréquence, durée, responsable, checklist, sortie
attendue) ; ses occurrences sont générées une seule fois par date (relancer le générateur ne
crée aucun doublon). Reporter une occurrence ne décale qu'elle. Une occurrence ne se clôture
comme faite qu'avec ses contrôles obligatoires cochés, sinon avec une exception motivée et
visible. Un constat devient une tâche (ou une décision) rattachée à son projet ; la routine en
garde seulement le lien.

Rien n'est envoyé hors de PILOT (RIT07) : les occurrences et rappels vivent dans l'application.
"""

import secrets
import uuid
from datetime import date, timedelta
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, StringConstraints, field_validator
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from pilot_api.access import visible_project_ids
from pilot_api.audit import record
from pilot_api.deps import CurrentMembership, DbSession
from pilot_api.models import (
    CLOSED_TASK_STATUSES,
    Decision,
    DecisionState,
    Membership,
    Milestone,
    MilestoneState,
    OccurrenceLink,
    OccurrenceState,
    Project,
    Role,
    Routine,
    RoutineFrequency,
    RoutineOccurrence,
    Task,
    utcnow,
)
from pilot_api.routers.decisions import _visible_filter as decision_filter
from pilot_api.routers.decisions import create_decision
from pilot_api.routers.projects import (
    CONFLICT,
    _person,
    _resolve_person,
    create_task,
    today_in,
)
from pilot_api.routine_rules import PROFILES, dates_between, generation_window
from pilot_api.schemas import DecisionCreate, PersonRef, TaskCreate

router = APIRouter(prefix="/api/spaces/{space_id}", tags=["routines"])

MAX_ROUTINES = 60
WRITERS = {Role.OWNER, Role.CONTRIBUTOR}

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
LongText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=4000)]
Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=2000)]
Label = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class ChecklistItemIn(BaseModel):
    id: str | None = None
    label: Label
    mandatory: bool = True


class NthWeekday(BaseModel):
    n: Annotated[int, Field(ge=-1, le=4)]
    weekday: Annotated[int, Field(ge=0, le=6)]

    @field_validator("n")
    @classmethod
    def _not_zero(cls, value: int) -> int:
        if value == 0:
            raise ValueError("n vaut 1 à 4, ou -1 pour le dernier.")
        return value


class _RoutineFields(BaseModel):
    purpose: LongText | None = None
    weekdays: Annotated[list[Annotated[int, Field(ge=0, le=6)]], Field(max_length=7)] | None = None
    month_days: Annotated[list[Annotated[int, Field(ge=1, le=31)]], Field(max_length=2)] | None = (
        None
    )
    nth_weekday: NthWeekday | None = None
    workdays_only: bool | None = None
    time_of_day: Annotated[str, StringConstraints(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")] | None = (
        None
    )
    duration_minutes: Annotated[int, Field(ge=5, le=480)] | None = None
    owner_member_id: uuid.UUID | None = None
    owner_label: Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)] | None = (
        None
    )
    participants: LongText | None = None
    checklist: Annotated[list[ChecklistItemIn], Field(max_length=20)] | None = None
    expected_output: LongText | None = None


class RoutineCreate(_RoutineFields):
    title: Title
    frequency: RoutineFrequency
    start_date: date | None = None


class RoutineUpdate(_RoutineFields):
    version: int
    title: Title | None = None
    frequency: RoutineFrequency | None = None
    # « model » : seulement les occurrences créées à l'avenir ; « following » : aussi les
    # occurrences déjà prévues à partir d'aujourd'hui (non commencées) sont recalculées.
    scope: Literal["model", "following"] = "model"


class ProfilesIn(BaseModel):
    keys: Annotated[list[str], Field(min_length=1, max_length=len(PROFILES))]


class ArchiveIn(BaseModel):
    reason: Reason


class ChecklistItemOut(BaseModel):
    id: str
    label: str
    mandatory: bool


class RoutineOut(BaseModel):
    id: uuid.UUID
    profile: str | None
    title: str
    purpose: str | None
    frequency: RoutineFrequency
    weekdays: list[int]
    month_days: list[int]
    nth_weekday: dict[str, int] | None
    workdays_only: bool
    time_of_day: str | None
    duration_minutes: int | None
    owner: PersonRef
    participants: str | None
    checklist: list[ChecklistItemOut]
    expected_output: str | None
    start_date: date
    paused: bool
    archived: bool
    archive_reason: str | None
    next_date: date | None
    late_count: int
    version: int


class ProfileOut(BaseModel):
    key: str
    title: str
    purpose: str
    frequency: RoutineFrequency
    weekdays: list[int]
    month_days: list[int]
    time_of_day: str | None
    duration_minutes: int | None
    checklist: list[dict[str, Any]]
    already_added: bool


class LinkOut(BaseModel):
    kind: Literal["task", "decision"]
    id: uuid.UUID
    title: str
    project_id: uuid.UUID | None


class OccurrenceOut(BaseModel):
    id: uuid.UUID
    routine_id: uuid.UUID
    routine_title: str
    time_of_day: str | None
    duration_minutes: int | None
    scheduled_date: date
    due_date: date
    postponed: bool
    postpone_reason: str | None
    state: OccurrenceState
    late: bool
    owner: PersonRef
    checklist: list[ChecklistItemOut]
    checks: dict[str, bool]
    missing_mandatory: list[str]
    result: str | None
    expected_output: str | None
    exception_reason: str | None
    cancel_reason: str | None
    links: list[LinkOut]
    version: int


class OccurrenceUpdate(BaseModel):
    version: int
    checks: Annotated[dict[str, bool], Field(max_length=20)] | None = None
    result: LongText | None = None
    due_date: date | None = None
    postpone_reason: LongText | None = None
    owner_member_id: uuid.UUID | None = None
    owner_label: Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)] | None = (
        None
    )


class OccurrenceClose(BaseModel):
    version: int
    state: Literal["done", "cancelled"]
    result: LongText | None = None
    exception_reason: LongText | None = None
    cancel_reason: LongText | None = None


class OccurrenceVersion(BaseModel):
    version: int


class FollowUpIn(BaseModel):
    kind: Literal["task", "decision"]
    project_id: uuid.UUID | None = None
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    due_date: date | None = None


class AgendaItem(BaseModel):
    kind: Literal["task", "decision", "milestone"]
    id: uuid.UUID
    title: str
    project_id: uuid.UUID | None
    project_title: str | None
    due_date: date | None
    late: bool
    detail: str | None


class AgendaOut(BaseModel):
    start: date
    end: date
    today: date
    items: list[AgendaItem]
    occurrences: list[OccurrenceOut]


# ---------- Outils ----------


def _ensure_reader(membership: Membership) -> None:
    if membership.role == Role.GUEST:
        raise HTTPException(403, "Les routines de l'espace ne sont pas ouvertes aux invités.")


def _ensure_writer(membership: Membership) -> None:
    if membership.role not in WRITERS:
        raise HTTPException(
            403, "Votre rôle permet de consulter les routines, pas de les modifier."
        )


def _checklist(items: list[ChecklistItemIn], current: list[dict[str, Any]]) -> list[dict]:
    known = {c["id"] for c in current}
    out = []
    for item in items:
        if item.id is not None and item.id not in known:
            raise HTTPException(422, "Contrôle inconnu.")
        out.append(
            {
                "id": item.id or f"chk_{secrets.token_hex(4)}",
                "label": item.label,
                "mandatory": item.mandatory,
            }
        )
    return out


def _check_rule(routine: Routine) -> None:
    f = routine.frequency
    by_week = (RoutineFrequency.DAILY, RoutineFrequency.WEEKLY, RoutineFrequency.BIWEEKLY)
    if f in by_week and not routine.weekdays:
        raise HTTPException(422, "Choisissez au moins un jour de la semaine.")
    if f == RoutineFrequency.TWICE_MONTHLY and len(set(routine.month_days or [])) != 2:
        raise HTTPException(422, "« Deux fois par mois » demande deux jours du mois différents.")
    nth = f == RoutineFrequency.MONTHLY and routine.nth_weekday
    if f in (RoutineFrequency.MONTHLY, RoutineFrequency.QUARTERLY) and not (
        routine.month_days or nth
    ):
        raise HTTPException(422, "Indiquez le jour du mois.")


def _apply(db: Session, membership: Membership, routine: Routine, body: _RoutineFields) -> None:
    sent = body.model_fields_set
    for name in (
        "purpose",
        "workdays_only",
        "time_of_day",
        "duration_minutes",
        "participants",
        "expected_output",
    ):
        if name in sent:
            value = getattr(body, name)
            setattr(routine, name, value if value != "" else None)
    if "weekdays" in sent:
        routine.weekdays = sorted(set(body.weekdays or []))
    if "month_days" in sent:
        routine.month_days = list(dict.fromkeys(body.month_days or []))
    if "nth_weekday" in sent:
        routine.nth_weekday = body.nth_weekday.model_dump() if body.nth_weekday else None
    if "owner_member_id" in sent or "owner_label" in sent:
        routine.owner_member_id, routine.owner_label = _resolve_person(
            db, membership.space_id, body.owner_member_id, body.owner_label
        )
    if "checklist" in sent:
        routine.checklist = _checklist(body.checklist or [], routine.checklist or [])
    if routine.workdays_only is None:
        routine.workdays_only = True


def _query_routines():
    return select(Routine).options(selectinload(Routine.owner_member).selectinload(Membership.user))


def _load_routine(db: Session, membership: Membership, routine_id: uuid.UUID) -> Routine:
    routine = db.scalar(
        _query_routines()
        .execution_options(populate_existing=True)
        .where(Routine.id == routine_id, Routine.space_id == membership.space_id)
        .with_for_update(of=Routine)
    )
    if routine is None:
        raise HTTPException(404, "Routine introuvable.")
    return routine


def generate(db: Session, routines: list[Routine], today: date, until: date | None = None) -> int:
    """Crée les occurrences manquantes (une seule fois par date). Renvoie le nombre créé."""
    created = 0
    for routine in routines:
        if routine.archived_at is not None or routine.paused_at is not None:
            continue
        first, last = generation_window(routine, today, until)
        wanted = dates_between(routine, first, last)
        if not wanted:
            continue
        existing = set(
            db.scalars(
                select(RoutineOccurrence.scheduled_date).where(
                    RoutineOccurrence.routine_id == routine.id,
                    RoutineOccurrence.scheduled_date.between(first, last),
                )
            )
        )
        for day in wanted:
            if day in existing:
                continue
            db.add(
                RoutineOccurrence(
                    space_id=routine.space_id,
                    routine_id=routine.id,
                    scheduled_date=day,
                    due_date=day,
                    state=OccurrenceState.PLANNED,
                    checks={},
                )
            )
            created += 1
    if created:
        db.flush()
    return created


def _space_routines(db: Session, space_id: uuid.UUID) -> list[Routine]:
    return list(
        db.scalars(
            _query_routines().where(Routine.space_id == space_id).order_by(Routine.created_at)
        )
    )


def _missing(routine: Routine, checks: dict[str, bool]) -> list[str]:
    return [
        c["label"]
        for c in routine.checklist or []
        if c.get("mandatory") and not checks.get(c["id"])
    ]


def _links(db: Session, occurrence_ids: list[uuid.UUID], membership: Membership) -> dict:
    if not occurrence_ids:
        return {}
    visible = visible_project_ids(db, membership)
    out: dict[uuid.UUID, list[LinkOut]] = {}
    rows = db.scalars(
        select(OccurrenceLink)
        .where(OccurrenceLink.occurrence_id.in_(occurrence_ids))
        .order_by(OccurrenceLink.created_at)
    )
    for link in rows:
        if link.task_id:
            task = db.get(Task, link.task_id)
            if task is None or (visible is not None and task.project_id not in visible):
                continue
            item = LinkOut(kind="task", id=task.id, title=task.title, project_id=task.project_id)
        else:
            decision = db.scalar(
                select(Decision).where(
                    Decision.id == link.decision_id, decision_filter(db, membership)
                )
            )
            if decision is None:
                continue
            item = LinkOut(
                kind="decision",
                id=decision.id,
                title=decision.statement[:200],
                project_id=decision.project_id,
            )
        out.setdefault(link.occurrence_id, []).append(item)
    return out


def occurrences_out(
    db: Session, membership: Membership, occurrences: list[RoutineOccurrence], today: date
) -> list[OccurrenceOut]:
    links = _links(db, [o.id for o in occurrences], membership)
    result = []
    for o in occurrences:
        r = o.routine
        owner = (
            _person(o.owner_member, o.owner_label)
            if o.owner_member_id or o.owner_label
            else _person(r.owner_member, r.owner_label)
        )
        result.append(
            OccurrenceOut(
                id=o.id,
                routine_id=r.id,
                routine_title=r.title,
                time_of_day=r.time_of_day,
                duration_minutes=r.duration_minutes,
                scheduled_date=o.scheduled_date,
                due_date=o.due_date,
                postponed=o.due_date != o.scheduled_date,
                postpone_reason=o.postpone_reason,
                state=o.state,
                late=o.state == OccurrenceState.PLANNED and o.due_date < today,
                owner=owner,
                checklist=[ChecklistItemOut(**c) for c in r.checklist or []],
                checks=o.checks or {},
                missing_mandatory=_missing(r, o.checks or {}),
                result=o.result,
                expected_output=r.expected_output,
                exception_reason=o.exception_reason,
                cancel_reason=o.cancel_reason,
                links=links.get(o.id, []),
                version=o.version,
            )
        )
    return result


def _occurrence_query():
    return select(RoutineOccurrence).options(
        selectinload(RoutineOccurrence.routine)
        .selectinload(Routine.owner_member)
        .selectinload(Membership.user),
        selectinload(RoutineOccurrence.owner_member).selectinload(Membership.user),
    )


def routines_out(db: Session, routines: list[Routine], today: date) -> list[RoutineOut]:
    ids = [r.id for r in routines]
    upcoming: dict[uuid.UUID, date] = {}
    late: dict[uuid.UUID, int] = {}
    if ids:
        for o in db.scalars(
            select(RoutineOccurrence).where(
                RoutineOccurrence.routine_id.in_(ids),
                RoutineOccurrence.state == OccurrenceState.PLANNED,
            )
        ):
            if o.due_date < today:
                late[o.routine_id] = late.get(o.routine_id, 0) + 1
            elif o.routine_id not in upcoming or o.due_date < upcoming[o.routine_id]:
                upcoming[o.routine_id] = o.due_date
    return [
        RoutineOut(
            id=r.id,
            profile=r.profile,
            title=r.title,
            purpose=r.purpose,
            frequency=r.frequency,
            weekdays=r.weekdays or [],
            month_days=r.month_days or [],
            nth_weekday=r.nth_weekday,
            workdays_only=r.workdays_only,
            time_of_day=r.time_of_day,
            duration_minutes=r.duration_minutes,
            owner=_person(r.owner_member, r.owner_label),
            participants=r.participants,
            checklist=[ChecklistItemOut(**c) for c in r.checklist or []],
            expected_output=r.expected_output,
            start_date=r.start_date,
            paused=r.paused_at is not None,
            archived=r.archived_at is not None,
            archive_reason=r.archive_reason,
            next_date=upcoming.get(r.id),
            late_count=late.get(r.id, 0),
            version=r.version,
        )
        for r in routines
    ]


def _journal(db: Session, membership: Membership, action: str, target: Any, after=None) -> None:
    record(
        db,
        action=action,
        actor_id=membership.user_id,
        space_id=membership.space_id,
        target_type="routine",
        target_id=target.id,
        after=after,
    )


# ---------- Routines ----------


@router.get("/routines")
def list_routines(membership: CurrentMembership, db: DbSession) -> list[RoutineOut]:
    _ensure_reader(membership)
    today = today_in(membership.space)
    routines = _space_routines(db, membership.space_id)
    if generate(db, routines, today):
        db.commit()
    return routines_out(db, routines, today)


@router.get("/routines/profiles")
def list_profiles(membership: CurrentMembership, db: DbSession) -> list[ProfileOut]:
    _ensure_reader(membership)
    added = {r.profile for r in _space_routines(db, membership.space_id) if r.archived_at is None}
    return [
        ProfileOut(
            key=key,
            title=p["title"],
            purpose=p["purpose"],
            frequency=p["frequency"],
            weekdays=p.get("weekdays", []),
            month_days=p.get("month_days", []),
            time_of_day=p.get("time_of_day"),
            duration_minutes=p.get("duration_minutes"),
            checklist=p["checklist"],
            already_added=key in added,
        )
        for key, p in PROFILES.items()
    ]


def _count(db: Session, space_id: uuid.UUID) -> int:
    return len([r for r in _space_routines(db, space_id) if r.archived_at is None])


@router.post("/routines", status_code=201)
def create_routine(body: RoutineCreate, membership: CurrentMembership, db: DbSession) -> RoutineOut:
    _ensure_writer(membership)
    if _count(db, membership.space_id) >= MAX_ROUTINES:
        raise HTTPException(422, f"{MAX_ROUTINES} routines actives au plus.")
    today = today_in(membership.space)
    routine = Routine(
        space_id=membership.space_id,
        title=body.title,
        frequency=body.frequency,
        start_date=body.start_date or today,
        weekdays=[],
        month_days=[],
        checklist=[],
        workdays_only=True,
        created_by_id=membership.user_id,
    )
    _apply(db, membership, routine, body)
    _check_rule(routine)
    db.add(routine)
    db.flush()
    _journal(db, membership, "routine.created", routine, {"title": routine.title})
    generate(db, [routine], today)
    db.commit()
    return routines_out(db, [routine], today)[0]


@router.post("/routines/profiles", status_code=201)
def add_profiles(
    body: ProfilesIn, membership: CurrentMembership, db: DbSession
) -> list[RoutineOut]:
    _ensure_writer(membership)
    unknown = set(body.keys) - set(PROFILES)
    if unknown:
        raise HTTPException(422, "Routine type inconnue.")
    today = today_in(membership.space)
    added = {r.profile for r in _space_routines(db, membership.space_id) if r.archived_at is None}
    created = []
    for key in dict.fromkeys(body.keys):
        if key in added:
            continue
        p = PROFILES[key]
        routine = Routine(
            space_id=membership.space_id,
            profile=key,
            title=p["title"],
            purpose=p["purpose"],
            frequency=p["frequency"],
            weekdays=p.get("weekdays", []),
            month_days=p.get("month_days", []),
            time_of_day=p.get("time_of_day"),
            duration_minutes=p.get("duration_minutes"),
            expected_output=p.get("expected_output"),
            checklist=[{"id": f"chk_{secrets.token_hex(4)}", **c} for c in p["checklist"]],
            workdays_only=True,
            start_date=today,
            owner_member_id=membership.id,
            owner_label=membership.user.display_name if membership.user else None,
            created_by_id=membership.user_id,
        )
        db.add(routine)
        db.flush()
        _journal(db, membership, "routine.created", routine, {"title": routine.title})
        created.append(routine)
    if _count(db, membership.space_id) > MAX_ROUTINES:
        raise HTTPException(422, f"{MAX_ROUTINES} routines actives au plus.")
    generate(db, created, today)
    db.commit()
    return routines_out(db, created, today)


@router.patch("/routines/{routine_id}")
def update_routine(
    routine_id: uuid.UUID, body: RoutineUpdate, membership: CurrentMembership, db: DbSession
) -> RoutineOut:
    _ensure_writer(membership)
    routine = _load_routine(db, membership, routine_id)
    if routine.version != body.version:
        raise HTTPException(409, CONFLICT)
    if body.title is not None:
        routine.title = body.title
    if body.frequency is not None:
        routine.frequency = body.frequency
    _apply(db, membership, routine, body)
    _check_rule(routine)
    routine.version += 1
    today = today_in(membership.space)
    removed = 0
    if body.scope == "following":
        # Les occurrences à venir non commencées sont recalculées ; celles déjà touchées
        # (cochées, reportées, avec un résultat ou un lien) restent telles quelles.
        linked = set(
            db.scalars(
                select(OccurrenceLink.occurrence_id)
                .join(RoutineOccurrence, RoutineOccurrence.id == OccurrenceLink.occurrence_id)
                .where(RoutineOccurrence.routine_id == routine.id)
            )
        )
        for o in db.scalars(
            select(RoutineOccurrence).where(
                RoutineOccurrence.routine_id == routine.id,
                RoutineOccurrence.state == OccurrenceState.PLANNED,
                RoutineOccurrence.scheduled_date >= today,
            )
        ):
            untouched = (
                not any((o.checks or {}).values())
                and o.due_date == o.scheduled_date
                and not o.result
                and o.id not in linked
                and o.owner_member_id is None
                and not o.owner_label
            )
            if untouched:
                db.delete(o)
                removed += 1
        db.flush()
        routine.generate_from = today
    _journal(
        db, membership, "routine.updated", routine, {"title": routine.title, "scope": body.scope}
    )
    generate(db, [routine], today)
    db.commit()
    return routines_out(db, [routine], today)[0]


@router.post("/routines/{routine_id}/pause")
def pause_routine(
    routine_id: uuid.UUID, membership: CurrentMembership, db: DbSession
) -> RoutineOut:
    _ensure_writer(membership)
    routine = _load_routine(db, membership, routine_id)
    if routine.paused_at is None:
        routine.paused_at = utcnow()
        routine.version += 1
        _journal(db, membership, "routine.paused", routine)
    db.commit()
    return routines_out(db, [routine], today_in(membership.space))[0]


@router.post("/routines/{routine_id}/resume")
def resume_routine(
    routine_id: uuid.UUID, membership: CurrentMembership, db: DbSession
) -> RoutineOut:
    _ensure_writer(membership)
    routine = _load_routine(db, membership, routine_id)
    today = today_in(membership.space)
    if routine.paused_at is not None:
        routine.paused_at = None
        # Pas de rattrapage de la période de pause.
        routine.generate_from = today
        routine.version += 1
        _journal(db, membership, "routine.resumed", routine)
        generate(db, [routine], today)
    db.commit()
    return routines_out(db, [routine], today)[0]


@router.post("/routines/{routine_id}/archive")
def archive_routine(
    routine_id: uuid.UUID, body: ArchiveIn, membership: CurrentMembership, db: DbSession
) -> RoutineOut:
    """Annulation motivée de la série : les occurrences passées restent, les prochaines non
    commencées sont annulées avec le même motif."""
    _ensure_writer(membership)
    routine = _load_routine(db, membership, routine_id)
    today = today_in(membership.space)
    if routine.archived_at is None:
        routine.archived_at = utcnow()
        routine.archive_reason = body.reason
        routine.version += 1
        for o in db.scalars(
            select(RoutineOccurrence).where(
                RoutineOccurrence.routine_id == routine.id,
                RoutineOccurrence.state == OccurrenceState.PLANNED,
                RoutineOccurrence.due_date >= today,
            )
        ):
            o.state = OccurrenceState.CANCELLED
            o.cancel_reason = body.reason
            o.closed_at = utcnow()
            o.closed_by_id = membership.user_id
            o.version += 1
        _journal(db, membership, "routine.archived", routine, {"reason": body.reason})
    db.commit()
    return routines_out(db, [routine], today)[0]


@router.post("/routines/{routine_id}/restore")
def restore_routine(
    routine_id: uuid.UUID, membership: CurrentMembership, db: DbSession
) -> RoutineOut:
    _ensure_writer(membership)
    routine = _load_routine(db, membership, routine_id)
    today = today_in(membership.space)
    if routine.archived_at is not None:
        routine.archived_at = None
        routine.archive_reason = None
        routine.generate_from = today
        routine.version += 1
        _journal(db, membership, "routine.restored", routine)
        generate(db, [routine], today)
    db.commit()
    return routines_out(db, [routine], today)[0]


# ---------- Occurrences ----------


@router.get("/routine-occurrences")
def list_occurrences(
    membership: CurrentMembership,
    db: DbSession,
    start: date | None = None,
    end: date | None = None,
    routine_id: uuid.UUID | None = None,
) -> list[OccurrenceOut]:
    """Occurrences de la période (et les occurrences en retard d'avant, toujours visibles)."""
    _ensure_reader(membership)
    today = today_in(membership.space)
    start = start or today
    end = end or start + timedelta(days=6)
    if end < start or (end - start).days > 120:
        raise HTTPException(422, "Période de 120 jours au plus.")
    routines = _space_routines(db, membership.space_id)
    generate(db, routines, today, end)
    query = _occurrence_query().where(
        RoutineOccurrence.space_id == membership.space_id,
        or_(
            RoutineOccurrence.due_date.between(start, end),
            (RoutineOccurrence.state == OccurrenceState.PLANNED)
            & (RoutineOccurrence.due_date < min(start, today)),
        ),
    )
    if routine_id is not None:
        query = query.where(RoutineOccurrence.routine_id == routine_id)
    rows = list(db.scalars(query.order_by(RoutineOccurrence.due_date)))
    db.commit()
    rows.sort(key=lambda o: (o.due_date, o.routine.time_of_day or "99:99", o.routine.title))
    return occurrences_out(db, membership, rows, today)


def _load_occurrence(
    db: Session, membership: Membership, occurrence_id: uuid.UUID, version: int | None
) -> RoutineOccurrence:
    _ensure_writer(membership)
    occurrence = db.scalar(
        _occurrence_query()
        .execution_options(populate_existing=True)
        .where(
            RoutineOccurrence.id == occurrence_id,
            RoutineOccurrence.space_id == membership.space_id,
        )
        .with_for_update(of=RoutineOccurrence)
    )
    if occurrence is None:
        raise HTTPException(404, "Occurrence introuvable.")
    if version is not None and occurrence.version != version:
        raise HTTPException(409, CONFLICT)
    return occurrence


def _one(db: Session, membership: Membership, occurrence: RoutineOccurrence) -> OccurrenceOut:
    return occurrences_out(db, membership, [occurrence], today_in(membership.space))[0]


@router.patch("/routine-occurrences/{occurrence_id}")
def update_occurrence(
    occurrence_id: uuid.UUID, body: OccurrenceUpdate, membership: CurrentMembership, db: DbSession
) -> OccurrenceOut:
    occurrence = _load_occurrence(db, membership, occurrence_id, body.version)
    if occurrence.state != OccurrenceState.PLANNED:
        raise HTTPException(422, "Rouvrez d'abord cette occurrence.")
    sent = body.model_fields_set
    if body.checks is not None:
        known = {c["id"] for c in occurrence.routine.checklist or []}
        if set(body.checks) - known:
            raise HTTPException(422, "Contrôle inconnu.")
        occurrence.checks = {**(occurrence.checks or {}), **body.checks}
    if "result" in sent:
        occurrence.result = body.result or None
    if body.due_date is not None and body.due_date != occurrence.due_date:
        if not (body.postpone_reason or "").strip():
            raise HTTPException(422, "Un report demande un motif.")
        # Seule cette occurrence bouge ; la date prévue par la série est gardée.
        before = occurrence.due_date
        occurrence.due_date = body.due_date
        occurrence.postpone_reason = body.postpone_reason
        _journal(
            db,
            membership,
            "routine.occurrence_postponed",
            occurrence.routine,
            {
                "occurrence": str(occurrence.id),
                "from": before.isoformat(),
                "to": body.due_date.isoformat(),
                "reason": body.postpone_reason,
            },
        )
    if "owner_member_id" in sent or "owner_label" in sent:
        occurrence.owner_member_id, occurrence.owner_label = _resolve_person(
            db, membership.space_id, body.owner_member_id, body.owner_label
        )
    occurrence.version += 1
    db.commit()
    db.refresh(occurrence)
    return _one(db, membership, occurrence)


@router.post("/routine-occurrences/{occurrence_id}/close")
def close_occurrence(
    occurrence_id: uuid.UUID, body: OccurrenceClose, membership: CurrentMembership, db: DbSession
) -> OccurrenceOut:
    occurrence = _load_occurrence(db, membership, occurrence_id, body.version)
    if occurrence.state != OccurrenceState.PLANNED:
        raise HTTPException(422, "Cette occurrence est déjà clôturée.")
    if body.result is not None:
        occurrence.result = body.result or None
    if body.state == "done":
        missing = _missing(occurrence.routine, occurrence.checks or {})
        if missing and not (body.exception_reason or "").strip():
            raise HTTPException(
                422,
                "Contrôles obligatoires non faits : "
                + ", ".join(missing)
                + ". Cochez-les, ou motivez l'exception.",
            )
        occurrence.exception_reason = body.exception_reason if missing else None
        occurrence.state = OccurrenceState.DONE
    else:
        if not (body.cancel_reason or "").strip():
            raise HTTPException(422, "Une annulation demande un motif.")
        occurrence.cancel_reason = body.cancel_reason
        occurrence.state = OccurrenceState.CANCELLED
    occurrence.closed_at = utcnow()
    occurrence.closed_by_id = membership.user_id
    occurrence.version += 1
    _journal(
        db,
        membership,
        f"routine.occurrence_{body.state}",
        occurrence.routine,
        {
            "occurrence": str(occurrence.id),
            "date": occurrence.due_date.isoformat(),
            "exception": occurrence.exception_reason,
            "reason": occurrence.cancel_reason,
        },
    )
    db.commit()
    db.refresh(occurrence)
    return _one(db, membership, occurrence)


@router.post("/routine-occurrences/{occurrence_id}/reopen")
def reopen_occurrence(
    occurrence_id: uuid.UUID, body: OccurrenceVersion, membership: CurrentMembership, db: DbSession
) -> OccurrenceOut:
    occurrence = _load_occurrence(db, membership, occurrence_id, body.version)
    if occurrence.state != OccurrenceState.PLANNED:
        occurrence.state = OccurrenceState.PLANNED
        occurrence.closed_at = None
        occurrence.closed_by_id = None
        occurrence.version += 1
        _journal(
            db,
            membership,
            "routine.occurrence_reopened",
            occurrence.routine,
            {"occurrence": str(occurrence.id)},
        )
    db.commit()
    db.refresh(occurrence)
    return _one(db, membership, occurrence)


@router.post("/routine-occurrences/{occurrence_id}/follow-ups", status_code=201)
def create_follow_up(
    occurrence_id: uuid.UUID, body: FollowUpIn, membership: CurrentMembership, db: DbSession
) -> OccurrenceOut:
    """Transforme un constat en tâche (dans un projet) ou en décision (brouillon), avec lien."""
    occurrence = _load_occurrence(db, membership, occurrence_id, None)
    if body.kind == "task":
        if body.project_id is None:
            raise HTTPException(422, "Choisissez le projet de la tâche.")
        task = create_task(
            body.project_id,
            TaskCreate(title=body.title, due_date=body.due_date),
            membership,
            db,
        )
        link = OccurrenceLink(occurrence_id=occurrence.id, task_id=task.id)
    else:
        decision = create_decision(
            DecisionCreate(
                statement=body.title, due_date=body.due_date, project_id=body.project_id
            ),
            membership,
            db,
        )
        link = OccurrenceLink(occurrence_id=occurrence.id, decision_id=decision.id)
    occurrence = _load_occurrence(db, membership, occurrence_id, None)
    db.add(link)
    db.commit()
    db.refresh(occurrence)
    return _one(db, membership, occurrence)


# ---------- Ma journée / Ma semaine (VIS01) ----------


@router.get("/agenda")
def my_agenda(
    membership: CurrentMembership,
    db: DbSession,
    start: date | None = None,
    end: date | None = None,
) -> AgendaOut:
    """Ce qui revient à la personne sur la période : ses tâches, les décisions qu'elle porte ou
    exécute, ses jalons et les occurrences de routines dont elle est responsable (ou sans
    responsable). Ce qui est en retard reste affiché. Rien de confidentiel n'y apparaît au-delà
    de ce que la personne peut déjà voir."""
    today = today_in(membership.space)
    start = start or today
    end = end or start
    if end < start or (end - start).days > 31:
        raise HTTPException(422, "Période de 31 jours au plus.")
    visible = visible_project_ids(db, membership)
    titles = {
        pid: title
        for pid, title in db.execute(
            select(Project.id, Project.title).where(Project.space_id == membership.space_id)
        )
    }

    items: list[AgendaItem] = []

    task_query = select(Task).where(
        Task.space_id == membership.space_id,
        Task.assignee_member_id == membership.id,
        Task.status.not_in(CLOSED_TASK_STATUSES),
        Task.due_date.is_not(None),
        Task.due_date <= end,
    )
    if visible is not None:
        task_query = task_query.where(Task.project_id.in_(visible))
    for t in db.scalars(task_query.order_by(Task.due_date)):
        items.append(
            AgendaItem(
                kind="task",
                id=t.id,
                title=t.title,
                project_id=t.project_id,
                project_title=titles.get(t.project_id),
                due_date=t.due_date,
                late=t.due_date < today,
                detail=None,
            )
        )

    decision_query = select(Decision).where(
        decision_filter(db, membership),
        Decision.state.in_([DecisionState.DRAFT, DecisionState.OPEN]),
        or_(
            Decision.executor_member_id == membership.id,
            Decision.decider_member_id == membership.id,
        ),
        Decision.due_date.is_not(None),
        Decision.due_date <= end,
    )
    for d in db.scalars(decision_query.order_by(Decision.due_date)):
        role = "à exécuter" if d.executor_member_id == membership.id else "à porter"
        items.append(
            AgendaItem(
                kind="decision",
                id=d.id,
                title=d.statement[:200],
                project_id=d.project_id,
                project_title=titles.get(d.project_id) if d.project_id else None,
                due_date=d.due_date,
                late=d.due_date < today,
                detail=f"Décision {role}" + (" (brouillon)" if d.state == "draft" else ""),
            )
        )

    milestone_query = select(Milestone).where(
        Milestone.space_id == membership.space_id,
        Milestone.owner_member_id == membership.id,
        Milestone.state == MilestoneState.PLANNED,
        Milestone.due_date <= end,
    )
    if visible is not None:
        milestone_query = milestone_query.where(Milestone.project_id.in_(visible))
    for m in db.scalars(milestone_query.order_by(Milestone.due_date)):
        items.append(
            AgendaItem(
                kind="milestone",
                id=m.id,
                title=m.title,
                project_id=m.project_id,
                project_title=titles.get(m.project_id),
                due_date=m.due_date,
                late=m.due_date < today,
                detail="Jalon critique" if m.critical else "Jalon",
            )
        )
    items.sort(key=lambda i: (i.due_date or end, i.kind))

    occurrences: list[OccurrenceOut] = []
    if membership.role != Role.GUEST:
        routines = _space_routines(db, membership.space_id)
        generate(db, routines, today, end)
        rows = db.scalars(
            _occurrence_query()
            .join(Routine, Routine.id == RoutineOccurrence.routine_id)
            .where(
                RoutineOccurrence.space_id == membership.space_id,
                or_(
                    RoutineOccurrence.owner_member_id == membership.id,
                    (RoutineOccurrence.owner_member_id.is_(None))
                    & (RoutineOccurrence.owner_label.is_(None))
                    & or_(
                        Routine.owner_member_id == membership.id,
                        (Routine.owner_member_id.is_(None)) & (Routine.owner_label.is_(None)),
                    ),
                ),
                or_(
                    RoutineOccurrence.due_date.between(start, end),
                    (RoutineOccurrence.state == OccurrenceState.PLANNED)
                    & (RoutineOccurrence.due_date < min(start, today)),
                ),
            )
        )
        rows = sorted(
            rows, key=lambda o: (o.due_date, o.routine.time_of_day or "99:99", o.routine.title)
        )
        occurrences = occurrences_out(db, membership, list(rows), today)
        db.commit()
    return AgendaOut(start=start, end=end, today=today, items=items, occurrences=occurrences)
