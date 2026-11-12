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

from pilot_api.access import (
    ensure_visible,
    ensure_writer,
    project_role,
    users_who_can_see,
    visible_project_ids,
    visible_projects,
)
from pilot_api.alerts import notify, short_date
from pilot_api.audit import record
from pilot_api.deps import CurrentMembership, DbSession, WriterMembership
from pilot_api.models import (
    CLOSED_PROJECT_STATUSES,
    CLOSED_TASK_STATUSES,
    EVENT_FOLLOW_UP_DAYS,
    AlertRule,
    AuditLog,
    Decision,
    Document,
    Entity,
    EventDetails,
    Membership,
    MembershipStatus,
    Milestone,
    Portfolio,
    Program,
    Project,
    ProjectContributor,
    ProjectKind,
    ProjectLink,
    ProjectSection,
    ProjectStatus,
    ProjectTemplate,
    ProjectType,
    Role,
    Space,
    Task,
    TaskComment,
    TaskDependency,
    TaskFollower,
    TaskStatus,
    User,
    utcnow,
)
from pilot_api.recurrence import next_due_date
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
from pilot_api.templates import apply_template

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
TASK_PLAIN_FIELDS = [
    "title",
    "deliverable",
    "due_date",
    "due_certainty",
    "recurrence",
    "priority",
    "start_date",
    "estimate_hours",
]
TASK_AUDIT_FIELDS = [
    *TASK_PLAIN_FIELDS,
    "status",
    "assignee_member_id",
    "assignee_label",
    "section_id",
]
VALIDATION_REFUSED = (
    "Cette tâche attend une validation : seul le responsable du projet ou un propriétaire de "
    "l'espace peut la passer à Terminée. Vous pouvez la renvoyer En cours."
)

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


def _project_out(
    project: Project, counts: tuple[int, int] = (0, 0), my_role: str | None = None
) -> ProjectOut:
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
        my_role=my_role,
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
            | {"open_tasks", "late_tasks", "my_role"}
        },
    )


def _load_project(db: Session, space_id: uuid.UUID, project_id: uuid.UUID) -> Project:
    project = db.scalar(
        _project_query().where(Project.id == project_id, Project.space_id == space_id)
    )
    if project is None:
        raise HTTPException(404, "Projet introuvable.")
    return project


def load_project(
    db: Session, membership: Membership, project_id: uuid.UUID, write: bool = False
) -> Project:
    """Projet de l'espace, visible pour cette personne (404 sinon) ; `write` exige en plus le
    droit de le modifier (403 sinon). Voir access.py."""
    project = _load_project(db, membership.space_id, project_id)
    if write:
        ensure_writer(db, membership, project)
        # Verrou jusqu'à la fin de l'enregistrement, puis relecture : deux modifications
        # simultanées donnent un conflit (409) au lieu d'un écrasement silencieux.
        db.refresh(project, with_for_update={"of": Project})
    else:
        ensure_visible(db, membership, project)
    return project


def _project_with_counts(db: Session, membership: Membership, project: Project) -> ProjectOut:
    counts = _task_counts(db, [project.id], today_in(membership.space))
    role = project_role(db, membership, project)
    return _project_out(project, counts.get(project.id, (0, 0)), role.value if role else None)


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
    for task_id, count in db.execute(
        select(Document.task_id, func.count())
        .where(
            Document.task_id.in_(task_ids),
            Document.archived_at.is_(None),
            Document.replaced_at.is_(None),
        )
        .group_by(Document.task_id)
    ):
        extras.setdefault(task_id, {})["documents_count"] = count
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
        recurrence=task.recurrence,
        next_task_id=task.next_task_id,
        section_id=task.section_id,
        priority=task.priority,
        estimate_hours=task.estimate_hours,
        start_date=task.start_date,
        original_due_date=task.original_due_date,
        postpone_count=task.postpone_count or 0,
        **(extras or {}).get(task.id, {}),
    )


def tasks_out(db: Session, tasks: list[Task], today: date) -> list[TaskOut]:
    extras = task_extras(db, [t.id for t in tasks])
    return [_task_out(t, today, extras) for t in tasks]


def task_out(db: Session, task: Task, today: date) -> TaskOut:
    return tasks_out(db, [task], today)[0]


def follow(db: Session, task: Task, user_ids) -> None:
    """Abonne des personnes (ayant un compte) à une tâche, sans doublon ; seulement celles qui
    voient son projet (lot C)."""
    users = {u for u in user_ids if u}
    if task.project_id:
        users = users_who_can_see(db, db.get(Project, task.project_id), users)
    for user_id in users:
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
    TaskStatus.TO_QUALIFY: "À qualifier",
    TaskStatus.TODO: "À faire",
    TaskStatus.IN_PROGRESS: "En cours",
    TaskStatus.BLOCKED: "Bloquée",
    TaskStatus.AWAITING_VALIDATION: "En attente de validation",
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


def load_task(db: Session, membership: Membership, task_id: uuid.UUID, write: bool = False) -> Task:
    """Tâche de l'espace dont le projet est visible (404 sinon) ; `write` exige le droit de
    modifier ce projet. Une ancienne tâche sans projet suit le rôle de l'espace."""
    task = _load_task(db, membership.space_id, task_id)
    project = db.get(Project, task.project_id) if task.project_id else None
    if project is not None:
        if write:
            ensure_writer(db, membership, project)
            db.refresh(task, with_for_update={"of": Task})
        else:
            ensure_visible(db, membership, project)
    elif membership.role == Role.GUEST or (write and membership.role == Role.READER):
        raise HTTPException(404 if membership.role == Role.GUEST else 403, "Tâche introuvable.")
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
    query = _project_query().where(
        Project.space_id == membership.space_id, visible_projects(membership)
    )
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
    return [
        _project_out(p, counts.get(p.id, (0, 0)), _role_value(db, membership, p)) for p in projects
    ]


def _role_value(db: Session, membership: Membership, project: Project) -> str | None:
    role = project_role(db, membership, project)
    return role.value if role else None


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
    template = None
    if body.template_id is not None:
        template = db.scalar(
            select(ProjectTemplate).where(
                ProjectTemplate.id == body.template_id, ProjectTemplate.space_id == space_id
            )
        )
        if template is None:
            raise HTTPException(404, "Modèle de projet introuvable.")
    project = Project(
        space_id=space_id,
        portfolio_id=body.portfolio_id,
        title=body.title,
        status=body.status,
        client_request_id=body.client_request_id,
        created_by_id=membership.user_id,
    )
    sent = body.model_fields_set - {"portfolio_id", "status", "client_request_id", "template_id"}
    db.add(project)
    _apply_project_fields(db, project, body, sent)
    if project.situation:
        _mark_manual_situation(project, membership)
    db.flush()
    after = {k: v for k, v in _project_snapshot(project).items() if v is not None}
    if template is not None:
        # Tâches du modèle : l'auteur et chaque responsable les suivent (sans alerte par tâche).
        created = apply_template(db, project, template)
        for task in created:
            follow(db, task, [membership.user_id, _member_user(db, task.assignee_member_id)])
        after |= {"template": template.name, "template_tasks": len(created)}
    record(
        db,
        action="project.created",
        actor_id=membership.user_id,
        space_id=space_id,
        target_type="project",
        target_id=project.id,
        after=after,
    )
    db.commit()
    return _project_with_counts(db, membership, _load_project(db, space_id, project.id))


@router.get("/projects/{project_id}")
def get_project(project_id: uuid.UUID, membership: CurrentMembership, db: DbSession) -> ProjectOut:
    project = load_project(db, membership, project_id)
    return _project_with_counts(db, membership, project)


@router.patch("/projects/{project_id}")
def update_project(
    project_id: uuid.UUID, body: ProjectUpdate, membership: CurrentMembership, db: DbSession
) -> ProjectOut:
    project = load_project(db, membership, project_id, write=True)
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
    project_id: uuid.UUID, body: ProjectStatusChange, membership: CurrentMembership, db: DbSession
) -> ProjectOut:
    """Règles de transition (CDC §22) : bilan pour Terminé, motif et clôture des tâches
    ouvertes pour Annulé, réouverture explicite et journalisée."""
    project = load_project(db, membership, project_id, write=True)
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
    project = load_project(db, membership, project_id)
    task_ids = [str(t) for t in db.scalars(select(Task.id).where(Task.project_id == project.id))]
    document_ids = [
        str(d) for d in db.scalars(select(Document.id).where(Document.project_id == project.id))
    ]
    milestone_ids = [
        str(m) for m in db.scalars(select(Milestone.id).where(Milestone.project_id == project.id))
    ]
    # Décisions du projet (étape F3) ; les confidentielles restent hors de l'historique commun.
    decision_ids = [
        str(d)
        for d in db.scalars(
            select(Decision.id).where(
                Decision.project_id == project.id, Decision.private.is_(False)
            )
        )
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
                and_(AuditLog.target_type == "milestone", AuditLog.target_id.in_(milestone_ids)),
                and_(AuditLog.target_type == "decision", AuditLog.target_id.in_(decision_ids)),
            ),
        )
        .order_by(AuditLog.created_at.desc())
        .limit(100)
    ).all()
    hide = _hidden_titles(db, membership)
    return [
        HistoryEntry(
            id=entry.id,
            action=entry.action,
            target_type=entry.target_type,
            actor_name=actor_name,
            created_at=entry.created_at,
            before=_redact(entry.before, hide),
            after=_redact(entry.after, hide),
        )
        for entry, actor_name in rows
    ]


HIDDEN = "un projet auquel vous n'avez pas accès"


def _hidden_titles(db: Session, membership: Membership) -> tuple[set[str], set[str]]:
    """Projets que cette personne ne voit pas : identifiants et titres (lot C), pour ne pas
    les révéler par l'historique d'un projet visible (lien, dépendance)."""
    if membership.role == Role.OWNER:
        return set(), set()
    rows = db.execute(
        select(Project.id, Project.title).where(
            Project.space_id == membership.space_id, ~visible_projects(membership)
        )
    ).all()
    return {str(pid) for pid, _ in rows}, {title for _, title in rows}


def _redact(data: dict | None, hide: tuple[set[str], set[str]]) -> dict | None:
    ids, titles = hide
    if not data or not ids:
        return data
    data = dict(data)
    if "linked_project" in data and (
        data.get("linked_project_id") in ids
        or ("linked_project_id" not in data and data["linked_project"] in titles)
    ):
        data["linked_project"] = HIDDEN
        data.pop("note", None)
    if data.get("waits_for_project_id") in ids:
        data["waits_for"] = "une tâche d'un projet auquel vous n'avez pas accès"
    data.pop("linked_project_id", None)
    data.pop("waits_for_project_id", None)
    return data


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
    visible = visible_project_ids(db, membership)
    if visible is not None:
        query = query.where(Task.project_id.in_(visible))
    if not include_closed:
        query = query.where(Task.status.not_in(CLOSED_TASK_STATUSES))
    tasks = db.scalars(query.order_by(Task.due_date.asc().nulls_last()).limit(2000)).all()
    return tasks_out(db, list(tasks), today_in(membership.space))


@router.get("/projects/{project_id}/tasks")
def list_tasks(
    project_id: uuid.UUID, membership: CurrentMembership, db: DbSession
) -> list[TaskOut]:
    project = load_project(db, membership, project_id)
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
    old_due = task.due_date
    for name in TASK_PLAIN_FIELDS:
        if name in sent:
            value = getattr(body, name)
            if isinstance(value, str) and value == "":
                value = None
            if name == "title" and value is None:
                continue
            setattr(task, name, value)
    # Report (TCH03) : une échéance repoussée garde la première échéance et compte les reports.
    if old_due is not None and task.due_date is not None and task.due_date > old_due:
        if task.original_due_date is None:
            task.original_due_date = old_due
        task.postpone_count = (task.postpone_count or 0) + 1
    if task.start_date and task.due_date and task.start_date > task.due_date:
        raise HTTPException(422, "La date de début est après l'échéance : vérifiez les dates.")
    if "section_id" in sent:
        _set_section(db, task, body.section_id)
    if "assignee_member_id" in sent or "assignee_label" in sent:
        task.assignee_member_id, task.assignee_label = _resolve_person(
            db, task.space_id, body.assignee_member_id, body.assignee_label
        )
    if "status" in sent and body.status is not None and body.status != task.status:
        task.status = body.status
        task.closed_at = utcnow() if body.status in CLOSED_TASK_STATUSES else None
    if task.recurrence is not None:
        if task.parent_id is not None:
            raise HTTPException(422, "Une sous-tâche ne peut pas se répéter : répétez sa tâche.")
        if task.due_date is None:
            raise HTTPException(
                422, "Une tâche répétée a besoin d'une échéance : indiquez-la d'abord."
            )


def _set_section(db: Session, task: Task, section_id: uuid.UUID | None) -> None:
    if section_id is None:
        task.section_id = None
        return
    if task.parent_id is not None:
        raise HTTPException(422, "Une sous-tâche reste dans la section de sa tâche.")
    section = db.get(ProjectSection, section_id)
    if section is None or section.project_id != task.project_id:
        raise HTTPException(422, "Cette section n'appartient pas au projet de la tâche.")
    if section.archived_at is not None and task.section_id != section.id:
        raise HTTPException(422, "Cette section est archivée : restaurez-la d'abord.")
    task.section_id = section.id


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
    project_id: uuid.UUID, body: TaskCreate, membership: CurrentMembership, db: DbSession
) -> TaskOut:
    project = load_project(db, membership, project_id, write=True)
    return create_task_in(db, membership, project, body)


@router.post("/tasks", status_code=201)
def create_space_task(
    body: SpaceTaskCreate, membership: CurrentMembership, db: DbSession
) -> TaskOut:
    """Une tâche appartient toujours à un projet (décision du 9 nov. 2026 : plus de tâche du
    « suivi général » sans projet)."""
    project = load_project(db, membership, body.project_id, write=True)
    return create_task_in(db, membership, project, body)


@router.patch("/tasks/{task_id}")
def update_task(
    task_id: uuid.UUID, body: TaskUpdate, membership: CurrentMembership, db: DbSession
) -> TaskOut:
    task = load_task(db, membership, task_id, write=True)
    if task.version != body.version:
        raise HTTPException(409, CONFLICT)
    before = _snapshot(task, TASK_AUDIT_FIELDS)
    old_assignee = task.assignee_member_id
    was_closed = task.status in CLOSED_TASK_STATUSES
    if (
        task.status == TaskStatus.AWAITING_VALIDATION
        and body.status == TaskStatus.DONE
        and not _can_validate(db, membership, task)
    ):
        raise HTTPException(403, VALIDATION_REFUSED)
    postponed_before = task.postpone_count or 0
    _apply_task_fields(db, task, body, body.model_fields_set - {"version", "postpone_reason"})
    old, new = _diff(before, _snapshot(task, TASK_AUDIT_FIELDS))
    if new and (task.postpone_count or 0) > postponed_before:
        new["postponed_from"] = str(before["due_date"]) if before.get("due_date") else None
        if body.postpone_reason:
            new["postpone_reason"] = body.postpone_reason
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
        if not was_closed and task.status == TaskStatus.DONE:
            _repeat(db, membership, task, project)
        db.commit()
        task = _load_task(db, membership.space_id, task_id)
    return task_out(db, task, today_in(membership.space))


def _can_validate(db: Session, membership: Membership, task: Task) -> bool:
    """Valider une tâche (En attente de validation → Terminée) : un propriétaire de l'espace ou
    le responsable du projet. Un droit de modification ne suffit pas (cahier V2, TCH03)."""
    if membership.role == Role.OWNER:
        return True
    project = db.get(Project, task.project_id) if task.project_id else None
    return project is not None and project.owner_member_id == membership.id


def _repeat(db: Session, membership: Membership, task: Task, project: Project | None) -> None:
    """Tâche répétée terminée : crée la suivante (une seule fois), avec ses sous-tâches remises
    à faire et ses abonnés. Rien n'est créé dans un projet clôturé."""
    if (
        task.recurrence is None
        or task.next_task_id is not None
        or task.due_date is None
        or task.parent_id is not None
        or project is None
        or project.status in CLOSED_PROJECT_STATUSES
    ):
        return
    due = next_due_date(task.due_date, task.recurrence, today_in(membership.space))
    shift = due - task.due_date
    following = Task(
        space_id=task.space_id,
        project_id=task.project_id,
        title=task.title,
        deliverable=task.deliverable,
        status=TaskStatus.TODO,
        assignee_member_id=task.assignee_member_id,
        assignee_label=task.assignee_label,
        due_date=due,
        due_certainty=task.due_certainty,
        recurrence=task.recurrence,
        section_id=task.section_id,
        priority=task.priority,
        estimate_hours=task.estimate_hours,
    )
    db.add(following)
    db.flush()
    task.next_task_id = following.id
    subtasks = db.scalars(
        select(Task)
        .where(Task.parent_id == task.id, Task.status != TaskStatus.CANCELLED)
        .order_by(Task.created_at)
    ).all()
    for sub in subtasks:
        db.add(
            Task(
                space_id=task.space_id,
                project_id=task.project_id,
                parent_id=following.id,
                title=sub.title,
                deliverable=sub.deliverable,
                status=TaskStatus.TODO,
                assignee_member_id=sub.assignee_member_id,
                assignee_label=sub.assignee_label,
                due_date=sub.due_date + shift if sub.due_date else None,
                due_certainty=sub.due_certainty,
            )
        )
    record(
        db,
        action="task.repeated",
        actor_id=membership.user_id,
        space_id=task.space_id,
        target_type="task",
        target_id=following.id,
        after={
            "title": following.title,
            "due_date": due.isoformat(),
            "recurrence": task.recurrence.value,
            "previous_task_id": str(task.id),
        },
    )
    follow(db, following, followers_of(db, task.id))
    notify_followers(
        db,
        membership,
        following,
        f"Tâche répétée : la prochaine est prévue le {short_date(due)}",
    )


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
        # Le titre de la tâche terminée n'est donné qu'à ceux qui voient son projet (lot C).
        blocker_project = db.get(Project, blocker.project_id) if blocker.project_id else None
        knowing = users_who_can_see(db, blocker_project, users) if blocker_project else users
        notify(
            db,
            membership.space,
            users - knowing,
            AlertRule.TASK_ACTIVITY,
            task,
            "La tâche attendue est terminée : cette tâche peut avancer",
        )
        users = knowing
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
    project = load_project(db, membership, project_id)
    links = db.scalars(
        select(ProjectLink).where(
            or_(ProjectLink.project_a_id == project.id, ProjectLink.project_b_id == project.id)
        )
    ).all()

    def other_id(link: ProjectLink) -> uuid.UUID:
        return link.project_b_id if link.project_a_id == project.id else link.project_a_id

    ids = [other_id(lk) for lk in links]
    # Un projet lié invisible pour cette personne n'est pas montré (pas même son titre).
    others = {
        p.id: p
        for p in db.scalars(
            _project_query().where(Project.id.in_(ids), visible_projects(membership))
        )
    }
    result = [_linked_out(lk, others[other_id(lk)]) for lk in links if other_id(lk) in others]
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
            after={
                "linked_project": b.title,
                "linked_project_id": str(b.id),
                **({"note": note} if note else {}),
            },
        )


@router.post("/projects/{project_id}/links", status_code=201)
def create_link(
    project_id: uuid.UUID, body: ProjectLinkCreate, membership: CurrentMembership, db: DbSession
) -> ProjectLinkOut:
    project = load_project(db, membership, project_id, write=True)
    if body.project_id == project.id:
        raise HTTPException(422, "Un projet ne peut pas être lié à lui-même.")
    other = load_project(db, membership, body.project_id)
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
    project_id: uuid.UUID, other_id: uuid.UUID, membership: CurrentMembership, db: DbSession
) -> None:
    project = load_project(db, membership, project_id, write=True)
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
