"""Projets et tâches (CDC §6, §8, §21, §22).

Lecteurs : consultation. Contributeurs et propriétaires : création et modification.
Chaque modification incrémente la version (conflits détectés) et laisse une trace au journal.
"""

import uuid
from datetime import date, timedelta
from enum import Enum
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, selectinload

from pilot_api.alerts import notify, short_date
from pilot_api.audit import record
from pilot_api.deps import CurrentMembership, DbSession, WriterMembership
from pilot_api.models import (
    CLOSED_PROJECT_STATUSES,
    CLOSED_TASK_STATUSES,
    EVENT_FOLLOW_UP_DAYS,
    AlertRule,
    AuditLog,
    Document,
    Entity,
    EventDetails,
    Membership,
    MembershipStatus,
    Portfolio,
    Program,
    Project,
    ProjectContributor,
    ProjectKind,
    ProjectLink,
    ProjectStatus,
    ProjectType,
    Space,
    Task,
    TaskComment,
    TaskDependency,
    TaskFollower,
    TaskStatus,
    User,
    utcnow,
)
from pilot_api.schemas import (
    EventOut,
    HistoryEntry,
    LinkedProject,
    PersonRef,
    PortfolioRef,
    ProjectCreate,
    ProjectLinkCreate,
    ProjectLinkOut,
    ProjectOut,
    ProjectStatusChange,
    ProjectTypeRef,
    ProjectUpdate,
    RefOut,
    SpaceTaskCreate,
    TaskCreate,
    TaskOut,
    TaskUpdate,
)

router = APIRouter(prefix="/api/spaces/{space_id}", tags=["projets"])

# Champs copiés tels quels de la requête vers le projet (hors références et responsable).
PROJECT_PLAIN_FIELDS = [
    "title",
    "origin",
    "situation",
    "next_step",
    "decision_needed",
    "decision_maker",
    "objective",
    "deliverables",
    "progress",
    "risk_level",
    "risk_note",
    "start_date",
    "end_date",
    "due_date",
    "date_certainty",
    "window_start",
    "window_end",
    "country",
    "city",
    "external_url",
]
PROJECT_AUDIT_FIELDS = [
    *PROJECT_PLAIN_FIELDS,
    "portfolio_id",
    "entity_id",
    "project_type_id",
    "owner_member_id",
    "owner_label",
    "status",
    "outcome",
    "cancel_reason",
    "decision_options",
]
EVENT_FIELDS = ["venue", "audience", "expected_attendance", "program_id", "edition_label"]
TASK_PLAIN_FIELDS = ["title", "deliverable", "due_date", "due_certainty"]
TASK_AUDIT_FIELDS = [*TASK_PLAIN_FIELDS, "status", "assignee_member_id", "assignee_label"]

CONFLICT = "Cet élément a été modifié entre-temps. Rechargez la page avant de réessayer."


# ---------- Outils ----------


def _json(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, uuid.UUID | date):
        return str(value)
    return value


def _snapshot(obj: Any, fields: list[str]) -> dict[str, Any]:
    return {name: _json(getattr(obj, name)) for name in fields}


def _project_snapshot(project: Project) -> dict[str, Any]:
    data = _snapshot(project, PROJECT_AUDIT_FIELDS)
    # Les contributeurs apparaissent au journal par leur nom (lisible même après un départ).
    data["contributors"] = [_person(c.member, c.label).name for c in project.contributors] or None
    if project.event_details is not None:
        data |= {f"event_{k}": v for k, v in _snapshot(project.event_details, EVENT_FIELDS).items()}
    return data


def _diff(before: dict[str, Any], after: dict[str, Any]) -> tuple[dict, dict]:
    changed = [k for k in after if before.get(k) != after[k]]
    return {k: before.get(k) for k in changed}, {k: after[k] for k in changed}


def today_in(space: Space) -> date:
    """La date du jour dans le fuseau de l'espace (CDC §12)."""
    return utcnow().astimezone(ZoneInfo(space.timezone)).date()


def _person(member: Membership | None, label: str | None) -> PersonRef:
    if member is not None:
        name = member.user.display_name if member.user else member.email
        return PersonRef(member_id=member.id, name=name, has_account=member.user_id is not None)
    return PersonRef(member_id=None, name=label, has_account=False)


def _resolve_person(
    db: Session, space_id: uuid.UUID, member_id: uuid.UUID | None, label: str | None
) -> tuple[uuid.UUID | None, str | None]:
    """Un responsable est soit un membre de l'espace, soit un nom libre (sans compte)."""
    if member_id is None:
        return None, label or None
    member = db.scalar(
        select(Membership)
        .options(selectinload(Membership.user))
        .where(Membership.id == member_id, Membership.space_id == space_id)
    )
    if member is None or member.status != MembershipStatus.ACTIVE:
        raise HTTPException(422, "Ce membre n'appartient pas à l'espace.")
    # Le nom est gardé en copie : il reste lisible si la personne quitte l'espace.
    return member.id, member.user.display_name if member.user else member.email


def _check_ref(db: Session, model: type, space_id: uuid.UUID, ref_id: uuid.UUID, label: str):
    item = db.scalar(select(model).where(model.id == ref_id, model.space_id == space_id))
    if item is None:
        raise HTTPException(422, f"{label} introuvable dans cet espace.")
    if item.archived_at is not None:
        raise HTTPException(422, f"{label} « {item.name} » est archivé.")


def _check_dates(project: Project) -> None:
    if project.start_date and project.end_date and project.end_date < project.start_date:
        raise HTTPException(422, "La date de fin précède la date de début.")
    if bool(project.window_start) != bool(project.window_end):
        raise HTTPException(422, "Une période doit avoir un début et une fin.")
    if project.window_start and project.window_end and project.window_end < project.window_start:
        raise HTTPException(422, "La fin de la période précède son début.")


def _task_counts(db: Session, project_ids: list[uuid.UUID], today: date) -> dict:
    if not project_ids:
        return {}
    is_open = Task.status.not_in(CLOSED_TASK_STATUSES)
    rows = db.execute(
        select(
            Task.project_id,
            func.count().filter(is_open),
            func.count().filter(and_(is_open, Task.due_date < today)),
        )
        .where(Task.project_id.in_(project_ids))
        .group_by(Task.project_id)
    ).all()
    return {project_id: (open_count, late) for project_id, open_count, late in rows}


def _project_query():
    # populate_existing : après un enregistrement, relire les liens (responsable, filiale…)
    # plutôt que réutiliser l'objet déjà chargé dans la session.
    return (
        select(Project)
        .execution_options(populate_existing=True)
        .options(
            selectinload(Project.portfolio),
            selectinload(Project.entity),
            selectinload(Project.project_type),
            selectinload(Project.owner_member).selectinload(Membership.user),
            selectinload(Project.event_details).selectinload(EventDetails.program),
            selectinload(Project.contributors)
            .selectinload(ProjectContributor.member)
            .selectinload(Membership.user),
        )
    )


def _is_event(project: Project) -> bool:
    return project.project_type is not None and project.project_type.kind == ProjectKind.EVENT


def _event_out(project: Project) -> EventOut | None:
    """Détails visibles seulement si le type est de nature « événement ». Si le type change,
    les détails sont conservés en base et réapparaissent quand le projet redevient un événement."""
    if not _is_event(project):
        return None
    details = project.event_details
    reference = project.end_date or project.start_date or project.due_date
    program = details.program if details else None
    return EventOut(
        venue=details.venue if details else None,
        audience=details.audience if details else None,
        expected_attendance=details.expected_attendance if details else None,
        program=RefOut(id=program.id, name=program.name) if program else None,
        edition_label=details.edition_label if details else None,
        follow_up_until=reference + timedelta(days=EVENT_FOLLOW_UP_DAYS) if reference else None,
    )


def _portfolio_ref(portfolio: Portfolio) -> PortfolioRef:
    return PortfolioRef(
        id=portfolio.id, name=portfolio.name, color=portfolio.color, emoji=portfolio.emoji
    )


def _project_out(project: Project, counts: tuple[int, int] = (0, 0)) -> ProjectOut:
    entity, ptype, portfolio = project.entity, project.project_type, project.portfolio
    return ProjectOut(
        id=project.id,
        title=project.title,
        status=project.status,
        portfolio=_portfolio_ref(portfolio),
        entity=RefOut(id=entity.id, name=entity.name) if entity else None,
        project_type=ProjectTypeRef(id=ptype.id, name=ptype.name, kind=ptype.kind)
        if ptype
        else None,
        owner=_person(project.owner_member, project.owner_label),
        contributors=[_person(c.member, c.label) for c in project.contributors],
        decision_options=project.decision_options or [],
        event=_event_out(project),
        open_tasks=counts[0],
        late_tasks=counts[1],
        **{
            name: getattr(project, name)
            for name in ProjectOut.model_fields
            if name
            not in {
                "id",
                "title",
                "status",
                "portfolio",
                "entity",
                "project_type",
                "owner",
                "event",
                "contributors",
                "decision_options",
            }
            | {"open_tasks", "late_tasks"}
        },
    )


def _load_project(db: Session, space_id: uuid.UUID, project_id: uuid.UUID) -> Project:
    project = db.scalar(
        _project_query().where(Project.id == project_id, Project.space_id == space_id)
    )
    if project is None:
        raise HTTPException(404, "Projet introuvable.")
    return project


def _project_with_counts(db: Session, membership: Membership, project: Project) -> ProjectOut:
    counts = _task_counts(db, [project.id], today_in(membership.space))
    return _project_out(project, counts.get(project.id, (0, 0)))


def task_extras(db: Session, task_ids: list[uuid.UUID]) -> dict[uuid.UUID, dict[str, int]]:
    """Compteurs affichés sur chaque tâche : sous-tâches, commentaires, tâches attendues."""
    extras: dict[uuid.UUID, dict[str, int]] = {}
    if not task_ids:
        return extras
    for parent_id, total, done in db.execute(
        select(
            Task.parent_id,
            func.count().filter(Task.status != TaskStatus.CANCELLED),
            func.count().filter(Task.status == TaskStatus.DONE),
        )
        .where(Task.parent_id.in_(task_ids))
        .group_by(Task.parent_id)
    ):
        extras.setdefault(parent_id, {}).update(subtasks_total=total, subtasks_done=done)
    for task_id, count in db.execute(
        select(TaskComment.task_id, func.count())
        .where(TaskComment.task_id.in_(task_ids))
        .group_by(TaskComment.task_id)
    ):
        extras.setdefault(task_id, {})["comments_count"] = count
    blocker = Task.__table__.alias("blocker")
    for task_id, count in db.execute(
        select(TaskDependency.task_id, func.count())
        .join(blocker, blocker.c.id == TaskDependency.depends_on_id)
        .where(
            TaskDependency.task_id.in_(task_ids),
            blocker.c.status.not_in([s.value for s in CLOSED_TASK_STATUSES]),
        )
        .group_by(TaskDependency.task_id)
    ):
        extras.setdefault(task_id, {})["waiting_on"] = count
    return extras


def _task_out(task: Task, today: date, extras: dict | None = None) -> TaskOut:
    late = (
        task.status not in CLOSED_TASK_STATUSES
        and task.due_date is not None
        and task.due_date < today
    )
    return TaskOut(
        id=task.id,
        project_id=task.project_id,
        title=task.title,
        deliverable=task.deliverable,
        status=task.status,
        assignee=_person(task.assignee_member, task.assignee_label),
        due_date=task.due_date,
        due_certainty=task.due_certainty,
        late=late,
        closed_at=task.closed_at,
        version=task.version,
        parent_id=task.parent_id,
        **(extras or {}).get(task.id, {}),
    )


def tasks_out(db: Session, tasks: list[Task], today: date) -> list[TaskOut]:
    extras = task_extras(db, [t.id for t in tasks])
    return [_task_out(t, today, extras) for t in tasks]


def task_out(db: Session, task: Task, today: date) -> TaskOut:
    return tasks_out(db, [task], today)[0]


def follow(db: Session, task: Task, user_ids) -> None:
    """Abonne des personnes (ayant un compte) à une tâche, sans doublon."""
    for user_id in {u for u in user_ids if u}:
        db.execute(
            insert(TaskFollower)
            .values(id=uuid.uuid4(), task_id=task.id, user_id=user_id, created_at=utcnow())
            .on_conflict_do_nothing(constraint="uq_task_followers")
        )


def followers_of(db: Session, task_id: uuid.UUID) -> set[uuid.UUID]:
    return set(db.scalars(select(TaskFollower.user_id).where(TaskFollower.task_id == task_id)))


def actor_name(membership: Membership) -> str:
    user = membership.user
    return user.display_name if user else membership.email


def notify_followers(db: Session, membership: Membership, task: Task, detail: str, skip=()) -> None:
    """Prévient les abonnés d'une tâche, sauf l'auteur du changement."""
    users = followers_of(db, task.id) - {membership.user_id, *skip}
    notify(db, membership.space, users, AlertRule.TASK_ACTIVITY, task, detail)


TASK_STATUS_WORDS = {
    TaskStatus.TODO: "À faire",
    TaskStatus.IN_PROGRESS: "En cours",
    TaskStatus.DONE: "Terminée",
    TaskStatus.CANCELLED: "Annulée",
}


def _load_task(db: Session, space_id: uuid.UUID, task_id: uuid.UUID) -> Task:
    task = db.scalar(
        select(Task)
        .execution_options(populate_existing=True)
        .options(selectinload(Task.assignee_member).selectinload(Membership.user))
        .where(Task.id == task_id, Task.space_id == space_id)
    )
    if task is None:
        raise HTTPException(404, "Tâche introuvable.")
    return task


def _apply_project_fields(db: Session, project: Project, body: Any, sent: set[str]) -> None:
    space_id = project.space_id
    for name in PROJECT_PLAIN_FIELDS:
        if name in sent:
            value = getattr(body, name)
            if name == "external_url" and value is not None:
                value = str(value)
            if isinstance(value, str) and value == "":
                value = None
            if name == "title" and value is None:
                continue  # le titre est obligatoire
            setattr(project, name, value)
    if "portfolio_id" in sent and body.portfolio_id is not None:
        if body.portfolio_id != project.portfolio_id:
            _check_ref(db, Portfolio, space_id, body.portfolio_id, "Le portefeuille")
        project.portfolio_id = body.portfolio_id
    if "entity_id" in sent:
        if body.entity_id is not None and body.entity_id != project.entity_id:
            _check_ref(db, Entity, space_id, body.entity_id, "La filiale")
        project.entity_id = body.entity_id
    if "project_type_id" in sent:
        if body.project_type_id is not None and body.project_type_id != project.project_type_id:
            _check_ref(db, ProjectType, space_id, body.project_type_id, "Le type de projet")
        project.project_type_id = body.project_type_id
    if "owner_member_id" in sent or "owner_label" in sent:
        project.owner_member_id, project.owner_label = _resolve_person(
            db, space_id, body.owner_member_id, body.owner_label
        )
    if "contributors" in sent:
        _apply_contributors(db, project, body.contributors or [])
    if "decision_options" in sent:
        options = [o.model_dump() for o in body.decision_options or []]
        project.decision_options = options or None
    if "event" in sent and body.event is not None:
        _apply_event_fields(db, project, body.event)
    _check_dates(project)


def _apply_contributors(db: Session, project: Project, people: list[Any]) -> None:
    """Remplace la liste des contributeurs ; doublons et noms vides sont ignorés."""
    seen: set[str] = set()
    result: list[ProjectContributor] = []
    for person in people:
        member_id, label = _resolve_person(db, project.space_id, person.member_id, person.label)
        if member_id is None and not label:
            continue
        key = str(member_id) if member_id else (label or "").casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(ProjectContributor(member_id=member_id, label=label, position=len(result)))
    project.contributors = result


def _mark_manual_situation(project: Project, membership: Membership) -> None:
    project.situation_updated_at = utcnow()
    project.situation_source = "manual"
    project.situation_source_label = None
    project.situation_updated_by = membership.user.display_name if membership.user else None


def _apply_event_fields(db: Session, project: Project, event: Any) -> None:
    ptype = db.get(ProjectType, project.project_type_id) if project.project_type_id else None
    if ptype is None or ptype.kind != ProjectKind.EVENT:
        raise HTTPException(
            422, "Les détails d'événement demandent un type de projet de nature « événement »."
        )
    details = project.event_details or EventDetails()
    for name in event.model_fields_set & set(EVENT_FIELDS):
        value = getattr(event, name)
        if isinstance(value, str) and value == "":
            value = None
        if name == "program_id" and value is not None and value != details.program_id:
            _check_ref(db, Program, project.space_id, value, "Le programme")
        setattr(details, name, value)
    project.event_details = details


# ---------- Projets ----------


@router.get("/projects")
def list_projects(
    membership: CurrentMembership,
    db: DbSession,
    portfolio_id: uuid.UUID | None = None,
    entity_id: uuid.UUID | None = None,
    status: ProjectStatus | None = None,
    kind: ProjectKind | None = None,
    program_id: uuid.UUID | None = None,
    q: str | None = None,
) -> list[ProjectOut]:
    query = _project_query().where(Project.space_id == membership.space_id)
    if kind:
        query = query.join(ProjectType, ProjectType.id == Project.project_type_id).where(
            ProjectType.kind == kind
        )
    if program_id:
        query = query.join(EventDetails, EventDetails.project_id == Project.id).where(
            EventDetails.program_id == program_id
        )
    if portfolio_id:
        query = query.where(Project.portfolio_id == portfolio_id)
    if entity_id:
        query = query.where(Project.entity_id == entity_id)
    if status:
        query = query.where(Project.status == status)
    if q:
        query = query.where(Project.title.ilike(f"%{q.strip()}%"))
    query = query.order_by(
        case((Project.status.in_(CLOSED_PROJECT_STATUSES), 1), else_=0),
        Project.due_date.asc().nulls_last(),
        func.lower(Project.title),
    )
    projects = db.scalars(query).all()
    counts = _task_counts(db, [p.id for p in projects], today_in(membership.space))
    return [_project_out(p, counts.get(p.id, (0, 0))) for p in projects]


@router.post("/projects", status_code=201)
def create_project(body: ProjectCreate, membership: WriterMembership, db: DbSession) -> ProjectOut:
    space_id = membership.space_id
    if body.client_request_id is not None:
        existing = db.scalar(
            _project_query().where(
                Project.space_id == space_id, Project.client_request_id == body.client_request_id
            )
        )
        if existing is not None:
            return _project_with_counts(db, membership, existing)

    _check_ref(db, Portfolio, space_id, body.portfolio_id, "Le portefeuille")
    project = Project(
        space_id=space_id,
        portfolio_id=body.portfolio_id,
        title=body.title,
        status=body.status,
        client_request_id=body.client_request_id,
        created_by_id=membership.user_id,
    )
    sent = body.model_fields_set - {"portfolio_id", "status", "client_request_id"}
    db.add(project)
    _apply_project_fields(db, project, body, sent)
    if project.situation:
        _mark_manual_situation(project, membership)
    db.flush()
    record(
        db,
        action="project.created",
        actor_id=membership.user_id,
        space_id=space_id,
        target_type="project",
        target_id=project.id,
        after={k: v for k, v in _project_snapshot(project).items() if v is not None},
    )
    db.commit()
    return _project_with_counts(db, membership, _load_project(db, space_id, project.id))


@router.get("/projects/{project_id}")
def get_project(project_id: uuid.UUID, membership: CurrentMembership, db: DbSession) -> ProjectOut:
    project = _load_project(db, membership.space_id, project_id)
    return _project_with_counts(db, membership, project)


@router.patch("/projects/{project_id}")
def update_project(
    project_id: uuid.UUID, body: ProjectUpdate, membership: WriterMembership, db: DbSession
) -> ProjectOut:
    project = _load_project(db, membership.space_id, project_id)
    if project.version != body.version:
        raise HTTPException(409, CONFLICT)
    before = _project_snapshot(project)
    _apply_project_fields(db, project, body, body.model_fields_set - {"version"})
    old, new = _diff(before, _project_snapshot(project))
    if new:
        if "situation" in new:
            _mark_manual_situation(project, membership)
        project.updated_at = utcnow()
        project.version += 1
        record(
            db,
            action="project.updated",
            actor_id=membership.user_id,
            space_id=project.space_id,
            target_type="project",
            target_id=project.id,
            before=old,
            after=new,
        )
        db.commit()
        project = _load_project(db, membership.space_id, project_id)
    return _project_with_counts(db, membership, project)


@router.post("/projects/{project_id}/status")
def change_status(
    project_id: uuid.UUID, body: ProjectStatusChange, membership: WriterMembership, db: DbSession
) -> ProjectOut:
    """Règles de transition (CDC §22) : bilan pour Terminé, motif et clôture des tâches
    ouvertes pour Annulé, réouverture explicite et journalisée."""
    project = _load_project(db, membership.space_id, project_id)
    if project.version != body.version:
        raise HTTPException(409, CONFLICT)
    if body.status == project.status:
        return _project_with_counts(db, membership, project)

    before = {"status": project.status.value}
    after: dict[str, Any] = {"status": body.status.value}
    if body.status == ProjectStatus.DONE:
        if not body.outcome:
            raise HTTPException(422, "Un bilan est nécessaire pour passer le projet à Terminé.")
        project.outcome = body.outcome
        after["outcome"] = body.outcome
    if body.status == ProjectStatus.CANCELLED:
        if not body.reason:
            raise HTTPException(422, "Un motif est nécessaire pour annuler le projet.")
        project.cancel_reason = body.reason
        after["cancel_reason"] = body.reason
        open_tasks = db.scalars(
            select(Task).where(
                Task.project_id == project.id, Task.status.not_in(CLOSED_TASK_STATUSES)
            )
        ).all()
        for task in open_tasks:
            task.status = TaskStatus.CANCELLED
            task.closed_at = utcnow()
            task.version += 1
        after["tasks_cancelled"] = len(open_tasks)

    reopened = (
        project.status in CLOSED_PROJECT_STATUSES and body.status not in CLOSED_PROJECT_STATUSES
    )
    project.status = body.status
    project.updated_at = utcnow()
    project.version += 1
    record(
        db,
        action="project.reopened" if reopened else "project.status_changed",
        actor_id=membership.user_id,
        space_id=project.space_id,
        target_type="project",
        target_id=project.id,
        before=before,
        after=after,
    )
    db.commit()
    return _project_with_counts(db, membership, _load_project(db, membership.space_id, project_id))


@router.get("/projects/{project_id}/history")
def project_history(
    project_id: uuid.UUID, membership: CurrentMembership, db: DbSession
) -> list[HistoryEntry]:
    project = _load_project(db, membership.space_id, project_id)
    task_ids = [str(t) for t in db.scalars(select(Task.id).where(Task.project_id == project.id))]
    document_ids = [
        str(d) for d in db.scalars(select(Document.id).where(Document.project_id == project.id))
    ]
    rows = db.execute(
        select(AuditLog, User.display_name)
        .outerjoin(User, User.id == AuditLog.actor_id)
        .where(
            AuditLog.space_id == membership.space_id,
            or_(
                and_(AuditLog.target_type == "project", AuditLog.target_id == str(project.id)),
                and_(AuditLog.target_type == "task", AuditLog.target_id.in_(task_ids)),
                and_(AuditLog.target_type == "document", AuditLog.target_id.in_(document_ids)),
            ),
        )
        .order_by(AuditLog.created_at.desc())
        .limit(100)
    ).all()
    return [
        HistoryEntry(
            id=entry.id,
            action=entry.action,
            target_type=entry.target_type,
            actor_name=actor_name,
            created_at=entry.created_at,
            before=entry.before,
            after=entry.after,
        )
        for entry, actor_name in rows
    ]


# ---------- Tâches ----------


@router.get("/tasks")
def list_space_tasks(
    membership: CurrentMembership, db: DbSession, include_closed: bool = False
) -> list[TaskOut]:
    """Tâches de tout l'espace (timeline, rappels). Par défaut, seulement les tâches ouvertes."""
    query = (
        select(Task)
        .options(selectinload(Task.assignee_member).selectinload(Membership.user))
        .where(Task.space_id == membership.space_id)
    )
    if not include_closed:
        query = query.where(Task.status.not_in(CLOSED_TASK_STATUSES))
    tasks = db.scalars(query.order_by(Task.due_date.asc().nulls_last()).limit(2000)).all()
    return tasks_out(db, list(tasks), today_in(membership.space))


@router.get("/projects/{project_id}/tasks")
def list_tasks(
    project_id: uuid.UUID, membership: CurrentMembership, db: DbSession
) -> list[TaskOut]:
    project = _load_project(db, membership.space_id, project_id)
    tasks = db.scalars(
        select(Task)
        .options(selectinload(Task.assignee_member).selectinload(Membership.user))
        .where(Task.project_id == project.id)
        .order_by(
            case((Task.status.in_(CLOSED_TASK_STATUSES), 1), else_=0),
            Task.due_date.asc().nulls_last(),
            Task.created_at,
        )
    ).all()
    return tasks_out(db, list(tasks), today_in(membership.space))


def _apply_task_fields(db: Session, task: Task, body: Any, sent: set[str]) -> None:
    for name in TASK_PLAIN_FIELDS:
        if name in sent:
            value = getattr(body, name)
            if isinstance(value, str) and value == "":
                value = None
            if name == "title" and value is None:
                continue
            setattr(task, name, value)
    if "assignee_member_id" in sent or "assignee_label" in sent:
        task.assignee_member_id, task.assignee_label = _resolve_person(
            db, task.space_id, body.assignee_member_id, body.assignee_label
        )
    if "status" in sent and body.status is not None and body.status != task.status:
        task.status = body.status
        task.closed_at = utcnow() if body.status in CLOSED_TASK_STATUSES else None


def create_task_in(
    db: Session,
    membership: Membership,
    project: Project | None,
    body: TaskCreate,
    parent: Task | None = None,
) -> TaskOut:
    if project is not None and project.status in CLOSED_PROJECT_STATUSES:
        raise HTTPException(400, "Ce projet est clôturé : rouvrez-le pour ajouter des tâches.")
    task = Task(
        space_id=membership.space_id,
        project_id=project.id if project else None,
        parent_id=parent.id if parent else None,
        title=body.title,
        status=TaskStatus.TODO,
    )
    sent = body.model_fields_set - {"title", "project_id"} | {"status"}
    _apply_task_fields(db, task, body, sent)
    db.add(task)
    db.flush()
    if project is not None:
        project.updated_at = utcnow()
    record(
        db,
        action="task.created",
        actor_id=membership.user_id,
        space_id=membership.space_id,
        target_type="task",
        target_id=task.id,
        after={
            k: v
            for k, v in (
                _snapshot(task, TASK_AUDIT_FIELDS)
                | ({"parent_title": parent.title} if parent else {})
            ).items()
            if v is not None
        },
    )
    # L'auteur et le responsable suivent la tâche ; la personne à qui on la confie est prévenue.
    assignee_user = _member_user(db, task.assignee_member_id)
    follow(db, task, [membership.user_id, assignee_user])
    if parent is not None:
        notify_followers(
            db,
            membership,
            parent,
            f"{actor_name(membership)} a ajouté la sous-tâche « {task.title} »",
        )
    if assignee_user and assignee_user != membership.user_id:
        notify(
            db,
            membership.space,
            [assignee_user],
            AlertRule.TASK_ACTIVITY,
            task,
            f"{actor_name(membership)} vous a confié cette tâche",
        )
    db.commit()
    return task_out(db, _load_task(db, membership.space_id, task.id), today_in(membership.space))


def _member_user(db: Session, member_id: uuid.UUID | None) -> uuid.UUID | None:
    if member_id is None:
        return None
    return db.scalar(select(Membership.user_id).where(Membership.id == member_id))


@router.post("/projects/{project_id}/tasks", status_code=201)
def create_task(
    project_id: uuid.UUID, body: TaskCreate, membership: WriterMembership, db: DbSession
) -> TaskOut:
    project = _load_project(db, membership.space_id, project_id)
    return create_task_in(db, membership, project, body)


@router.post("/tasks", status_code=201)
def create_space_task(
    body: SpaceTaskCreate, membership: WriterMembership, db: DbSession
) -> TaskOut:
    """Depuis la page Tâches : dans un projet, ou sans projet (suivi général, CDC §5)."""
    project = _load_project(db, membership.space_id, body.project_id) if body.project_id else None
    return create_task_in(db, membership, project, body)


@router.patch("/tasks/{task_id}")
def update_task(
    task_id: uuid.UUID, body: TaskUpdate, membership: WriterMembership, db: DbSession
) -> TaskOut:
    task = _load_task(db, membership.space_id, task_id)
    if task.version != body.version:
        raise HTTPException(409, CONFLICT)
    before = _snapshot(task, TASK_AUDIT_FIELDS)
    old_assignee = task.assignee_member_id
    was_closed = task.status in CLOSED_TASK_STATUSES
    _apply_task_fields(db, task, body, body.model_fields_set - {"version"})
    old, new = _diff(before, _snapshot(task, TASK_AUDIT_FIELDS))
    if new:
        task.version += 1
        project = db.get(Project, task.project_id) if task.project_id else None
        if project is not None:
            project.updated_at = utcnow()
        record(
            db,
            action="task.updated",
            actor_id=membership.user_id,
            space_id=task.space_id,
            target_type="task",
            target_id=task.id,
            before=old,
            after=new,
        )
        _notify_changes(db, membership, task, new, old_assignee, was_closed)
        db.commit()
        task = _load_task(db, membership.space_id, task_id)
    return task_out(db, task, today_in(membership.space))


def _notify_changes(
    db: Session,
    membership: Membership,
    task: Task,
    new: dict,
    old_assignee: uuid.UUID | None,
    was_closed: bool,
) -> None:
    """Abonnés prévenus des changements utiles ; tâches en attente prévenues du déblocage."""
    who = actor_name(membership)
    changes = []
    if "status" in new:
        changes.append(f"statut « {TASK_STATUS_WORDS[task.status]} »")
    if "due_date" in new:
        changes.append(
            f"échéance {short_date(task.due_date)}" if task.due_date else "échéance retirée"
        )
    assignee_user = None
    if task.assignee_member_id != old_assignee:
        assignee_user = _member_user(db, task.assignee_member_id)
        follow(db, task, [assignee_user])
        name = task.assignee_label  # copie du nom, à jour même pour un membre
        changes.append(f"confiée à {name}" if name else "responsable retiré")
        if assignee_user and assignee_user != membership.user_id:
            notify(
                db,
                membership.space,
                [assignee_user],
                AlertRule.TASK_ACTIVITY,
                task,
                f"{who} vous a confié cette tâche",
            )
    if changes:
        notify_followers(
            db,
            membership,
            task,
            f"{who} : " + ", ".join(changes),
            skip=[assignee_user] if assignee_user else (),
        )
    if not was_closed and task.status in CLOSED_TASK_STATUSES:
        _notify_unblocked(db, membership, task)


def _notify_unblocked(db: Session, membership: Membership, blocker: Task) -> None:
    waiting = db.scalars(
        select(Task)
        .join(TaskDependency, TaskDependency.task_id == Task.id)
        .where(TaskDependency.depends_on_id == blocker.id)
    ).all()
    extras = task_extras(db, [t.id for t in waiting])
    for task in waiting:
        if task.status in CLOSED_TASK_STATUSES or extras.get(task.id, {}).get("waiting_on"):
            continue
        users = followers_of(db, task.id) - {membership.user_id}
        notify(
            db,
            membership.space,
            users,
            AlertRule.TASK_ACTIVITY,
            task,
            f"« {blocker.title} » est terminée : cette tâche peut avancer",
        )


# ---------- Liens entre projets (CDC §5) ----------


def _linked_out(link: ProjectLink, other: Project) -> ProjectLinkOut:
    return ProjectLinkOut(
        id=link.id,
        project=LinkedProject(
            id=other.id,
            title=other.title,
            status=other.status,
            portfolio=_portfolio_ref(other.portfolio),
        ),
        note=link.note,
        created_at=link.created_at,
    )


@router.get("/projects/{project_id}/links")
def list_links(
    project_id: uuid.UUID, membership: CurrentMembership, db: DbSession
) -> list[ProjectLinkOut]:
    project = _load_project(db, membership.space_id, project_id)
    links = db.scalars(
        select(ProjectLink).where(
            or_(ProjectLink.project_a_id == project.id, ProjectLink.project_b_id == project.id)
        )
    ).all()

    def other_id(link: ProjectLink) -> uuid.UUID:
        return link.project_b_id if link.project_a_id == project.id else link.project_a_id

    ids = [other_id(lk) for lk in links]
    others = {p.id: p for p in db.scalars(_project_query().where(Project.id.in_(ids)))}
    result = [_linked_out(lk, others[other_id(lk)]) for lk in links]
    return sorted(result, key=lambda r: r.project.title.casefold())


def _record_link(db, membership, action, project, other, note=None):
    for a, b in ((project, other), (other, project)):
        record(
            db,
            action=action,
            actor_id=membership.user_id,
            space_id=membership.space_id,
            target_type="project",
            target_id=a.id,
            after={"linked_project": b.title, **({"note": note} if note else {})},
        )


@router.post("/projects/{project_id}/links", status_code=201)
def create_link(
    project_id: uuid.UUID, body: ProjectLinkCreate, membership: WriterMembership, db: DbSession
) -> ProjectLinkOut:
    project = _load_project(db, membership.space_id, project_id)
    if body.project_id == project.id:
        raise HTTPException(422, "Un projet ne peut pas être lié à lui-même.")
    other = _load_project(db, membership.space_id, body.project_id)
    a, b = sorted([project.id, other.id], key=str)
    existing = db.scalar(
        select(ProjectLink).where(ProjectLink.project_a_id == a, ProjectLink.project_b_id == b)
    )
    if existing is not None:
        raise HTTPException(409, f"Ce projet est déjà lié à « {other.title} ».")
    link = ProjectLink(
        space_id=membership.space_id, project_a_id=a, project_b_id=b, note=body.note or None
    )
    db.add(link)
    db.flush()
    _record_link(db, membership, "project.linked", project, other, link.note)
    db.commit()
    return _linked_out(link, other)


@router.delete("/projects/{project_id}/links/{other_id}", status_code=204)
def delete_link(
    project_id: uuid.UUID, other_id: uuid.UUID, membership: WriterMembership, db: DbSession
) -> None:
    project = _load_project(db, membership.space_id, project_id)
    other = _load_project(db, membership.space_id, other_id)
    a, b = sorted([project.id, other.id], key=str)
    link = db.scalar(
        select(ProjectLink).where(ProjectLink.project_a_id == a, ProjectLink.project_b_id == b)
    )
    if link is None:
        raise HTTPException(404, "Lien introuvable.")
    db.delete(link)
    _record_link(db, membership, "project.unlinked", project, other)
    db.commit()
