"""Jalons d'un projet (étape F2, cahier V2 TCH04 et CAP01–CAP03).

Un jalon est un résultat de passage daté : porteur, date engagée, critère, état et tâches dont
il dépend. Rien ne se supprime : un jalon est atteint (avec sa preuve), manqué ou annulé (avec
son motif), et peut être rouvert. Repousser sa date exige un motif ; après deux reports, une
revue de cadrage est exigée avant toute nouvelle date, et signalée aux responsables.
"""

import uuid
from datetime import date

from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from pilot_api.access import visible_project_ids
from pilot_api.alerts import notify_milestone
from pilot_api.audit import record
from pilot_api.deps import CurrentMembership, DbSession
from pilot_api.milestone_rules import REFRAME_AFTER, RISK_HORIZON_DAYS, risk
from pilot_api.models import (
    CLOSED_PROJECT_STATUSES,
    CLOSED_TASK_STATUSES,
    AlertRule,
    Membership,
    Milestone,
    MilestoneState,
    MilestoneTask,
    Project,
    ProjectSection,
    Role,
    Task,
    utcnow,
)
from pilot_api.routers.projects import (
    CONFLICT,
    _json,
    _person,
    _resolve_person,
    load_project,
    today_in,
)
from pilot_api.schemas import (
    MilestoneClose,
    MilestoneCreate,
    MilestoneOut,
    MilestoneTaskRef,
    MilestoneTasks,
    MilestoneUpdate,
    MilestoneVersion,
)

router = APIRouter(prefix="/api/spaces/{space_id}", tags=["jalons"])

MAX_MILESTONES = 100


def _linked(db: Session, milestone_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[Task]]:
    if not milestone_ids:
        return {}
    rows = db.execute(
        select(MilestoneTask.milestone_id, Task)
        .join(Task, Task.id == MilestoneTask.task_id)
        .where(MilestoneTask.milestone_id.in_(milestone_ids))
        .order_by(Task.created_at)
    ).all()
    linked: dict[uuid.UUID, list[Task]] = {}
    for milestone_id, task in rows:
        linked.setdefault(milestone_id, []).append(task)
    return linked


def milestones_out(
    db: Session, milestones: list[Milestone], today: date, titles: dict[uuid.UUID, str]
) -> list[MilestoneOut]:
    linked = _linked(db, [m.id for m in milestones])
    result = []
    for m in milestones:
        tasks = linked.get(m.id, [])
        late, at_risk, reasons = risk(m, tasks, today)
        result.append(
            MilestoneOut(
                id=m.id,
                project_id=m.project_id,
                project_title=titles.get(m.project_id, ""),
                section_id=m.section_id,
                title=m.title,
                criterion=m.criterion,
                owner=_person(m.owner_member, m.owner_label),
                due_date=m.due_date,
                original_due_date=m.original_due_date,
                postpone_count=m.postpone_count or 0,
                critical=bool(m.critical),
                state=m.state.value,
                close_note=m.close_note,
                closed_at=m.closed_at,
                reframe_note=m.reframe_note,
                late=late,
                at_risk=at_risk,
                risk_reasons=reasons,
                reframe_needed=m.state == MilestoneState.PLANNED
                and (m.postpone_count or 0) >= REFRAME_AFTER,
                tasks=[
                    MilestoneTaskRef(
                        id=t.id,
                        title=t.title,
                        status=t.status,
                        late=t.status not in CLOSED_TASK_STATUSES
                        and t.due_date is not None
                        and t.due_date < today,
                    )
                    for t in tasks
                ],
                version=m.version,
            )
        )
    return result


def _query():
    return select(Milestone).options(
        selectinload(Milestone.owner_member).selectinload(Membership.user)
    )


def _one_out(db: Session, membership: Membership, milestone: Milestone) -> MilestoneOut:
    project = db.get(Project, milestone.project_id)
    return milestones_out(db, [milestone], today_in(membership.space), {project.id: project.title})[
        0
    ]


def _load(
    db: Session, membership: Membership, milestone_id: uuid.UUID
) -> tuple[Milestone, Project]:
    milestone = db.scalar(
        _query()
        .execution_options(populate_existing=True)
        .where(Milestone.id == milestone_id, Milestone.space_id == membership.space_id)
    )
    if milestone is None:
        raise HTTPException(404, "Jalon introuvable.")
    project = load_project(db, membership, milestone.project_id, write=True)
    db.refresh(milestone, with_for_update={"of": Milestone})
    return milestone, project


def _check_section(db: Session, project: Project, section_id: uuid.UUID | None) -> None:
    if section_id is None:
        return
    section = db.get(ProjectSection, section_id)
    if section is None or section.project_id != project.id or section.archived_at is not None:
        raise HTTPException(422, "Choisissez une section active de ce projet.")


def _set_tasks(db: Session, milestone: Milestone, project: Project, task_ids) -> int:
    ids = list(dict.fromkeys(task_ids))
    found = set(db.scalars(select(Task.id).where(Task.id.in_(ids), Task.project_id == project.id)))
    if len(found) != len(ids):
        raise HTTPException(422, "Les tâches liées doivent appartenir au même projet.")
    current = {
        link.task_id: link
        for link in db.scalars(
            select(MilestoneTask).where(MilestoneTask.milestone_id == milestone.id)
        )
    }
    for task_id, link in current.items():
        if task_id not in found:
            db.delete(link)
    for task_id in ids:
        if task_id not in current:
            db.add(MilestoneTask(milestone_id=milestone.id, task_id=task_id))
    return len(ids)


def _journal(db, membership, milestone: Milestone, action: str, before=None, after=None):
    record(
        db,
        action=action,
        actor_id=membership.user_id,
        space_id=milestone.space_id,
        target_type="milestone",
        target_id=milestone.id,
        before=before,
        after={"milestone": milestone.title, **(after or {})},
    )


def _writable(project: Project) -> None:
    if project.status in CLOSED_PROJECT_STATUSES:
        raise HTTPException(400, "Ce projet est clôturé : rouvrez-le pour modifier ses jalons.")


@router.get("/projects/{project_id}/milestones")
def list_milestones(
    project_id: uuid.UUID, membership: CurrentMembership, db: DbSession
) -> list[MilestoneOut]:
    project = load_project(db, membership, project_id)
    milestones = db.scalars(
        _query().where(Milestone.project_id == project.id).order_by(Milestone.due_date)
    ).all()
    return milestones_out(
        db, list(milestones), today_in(membership.space), {project.id: project.title}
    )


@router.get("/milestones")
def upcoming_milestones(
    membership: CurrentMembership, db: DbSession, days: int = RISK_HORIZON_DAYS
) -> list[MilestoneOut]:
    """Jalons à venir de l'espace (projets visibles), y compris ceux déjà dépassés."""
    today = today_in(membership.space)
    visible = visible_project_ids(db, membership)
    query = (
        _query()
        .join(Project, Project.id == Milestone.project_id)
        .where(
            Milestone.space_id == membership.space_id,
            Milestone.state == MilestoneState.PLANNED,
            Project.status.not_in(CLOSED_PROJECT_STATUSES),
            Milestone.due_date <= date.fromordinal(today.toordinal() + max(0, min(days, 366))),
        )
        .order_by(Milestone.due_date)
        .limit(200)
    )
    if visible is not None:
        query = query.where(Milestone.project_id.in_(visible))
    milestones = list(db.scalars(query).all())
    titles = dict(
        db.execute(
            select(Project.id, Project.title).where(
                Project.id.in_({m.project_id for m in milestones})
            )
        ).all()
    )
    return milestones_out(db, milestones, today, titles)


@router.post("/projects/{project_id}/milestones", status_code=201)
def create_milestone(
    project_id: uuid.UUID, body: MilestoneCreate, membership: CurrentMembership, db: DbSession
) -> MilestoneOut:
    project = load_project(db, membership, project_id, write=True)
    _writable(project)
    count = len(db.scalars(select(Milestone.id).where(Milestone.project_id == project.id)).all())
    if count >= MAX_MILESTONES:
        raise HTTPException(422, f"{MAX_MILESTONES} jalons au plus par projet.")
    _check_section(db, project, body.section_id)
    milestone = Milestone(
        space_id=project.space_id,
        project_id=project.id,
        section_id=body.section_id,
        title=body.title,
        criterion=body.criterion or None,
        due_date=body.due_date,
        postpone_count=0,
        critical=bool(body.critical),
        state=MilestoneState.PLANNED,
    )
    milestone.owner_member_id, milestone.owner_label = _resolve_person(
        db, project.space_id, body.owner_member_id, body.owner_label
    )
    db.add(milestone)
    db.flush()
    linked = _set_tasks(db, milestone, project, body.task_ids)
    project.updated_at = utcnow()
    _journal(
        db,
        membership,
        milestone,
        "milestone.created",
        after={"due_date": str(milestone.due_date), "tasks": linked},
    )
    db.commit()
    return _one_out(db, membership, db.scalar(_query().where(Milestone.id == milestone.id)))


@router.patch("/milestones/{milestone_id}")
def update_milestone(
    milestone_id: uuid.UUID, body: MilestoneUpdate, membership: CurrentMembership, db: DbSession
) -> MilestoneOut:
    milestone, project = _load(db, membership, milestone_id)
    _writable(project)
    if milestone.version != body.version:
        raise HTTPException(409, CONFLICT)
    sent = body.model_fields_set
    before = {
        "title": milestone.title,
        "criterion": milestone.criterion,
        "due_date": _json(milestone.due_date),
        "owner_label": milestone.owner_label,
        "section_id": _json(milestone.section_id),
        "critical": milestone.critical,
    }
    if "title" in sent and body.title:
        milestone.title = body.title
    if "criterion" in sent:
        milestone.criterion = body.criterion or None
    if "critical" in sent and body.critical is not None:
        milestone.critical = body.critical
    if "section_id" in sent:
        if body.section_id != milestone.section_id:
            _check_section(db, project, body.section_id)
        milestone.section_id = body.section_id
    if "owner_member_id" in sent or "owner_label" in sent:
        milestone.owner_member_id, milestone.owner_label = _resolve_person(
            db, project.space_id, body.owner_member_id, body.owner_label
        )
    extra: dict = {}
    postponed = False
    if "due_date" in sent and body.due_date and body.due_date != milestone.due_date:
        if milestone.state != MilestoneState.PLANNED:
            raise HTTPException(400, "Rouvrez ce jalon avant de changer sa date.")
        if body.due_date > milestone.due_date:
            if not body.postpone_reason:
                raise HTTPException(422, "Indiquez le motif du report.")
            if (milestone.postpone_count or 0) >= REFRAME_AFTER and not body.reframe_note:
                raise HTTPException(
                    422,
                    f"Ce jalon a déjà été reporté {milestone.postpone_count} fois : une revue "
                    "de cadrage est nécessaire avant une nouvelle date (ce qui change, et "
                    "pourquoi la nouvelle date est tenable).",
                )
            if milestone.original_due_date is None:
                milestone.original_due_date = milestone.due_date
            milestone.postpone_count = (milestone.postpone_count or 0) + 1
            extra = {
                "postponed_from": str(milestone.due_date),
                "postpone_reason": body.postpone_reason,
                "postpone_count": milestone.postpone_count,
            }
            if body.reframe_note:
                milestone.reframe_note = body.reframe_note
                extra["reframe_note"] = body.reframe_note
            postponed = True
        milestone.due_date = body.due_date
    after = {
        "title": milestone.title,
        "criterion": milestone.criterion,
        "due_date": _json(milestone.due_date),
        "owner_label": milestone.owner_label,
        "section_id": _json(milestone.section_id),
        "critical": milestone.critical,
    }
    changed = {k: v for k, v in after.items() if before[k] != v}
    if changed or extra:
        milestone.version += 1
        project.updated_at = utcnow()
        _journal(
            db,
            membership,
            milestone,
            "milestone.postponed" if postponed else "milestone.updated",
            before={k: before[k] for k in changed},
            after={**changed, **extra},
        )
        if postponed and milestone.postpone_count == REFRAME_AFTER:
            _warn_reframe(db, membership, milestone, project)
        db.commit()
    return _one_out(db, membership, db.scalar(_query().where(Milestone.id == milestone.id)))


def _warn_reframe(db: Session, membership: Membership, milestone: Milestone, project: Project):
    """Deuxième report : le porteur, le responsable du projet et les propriétaires sont prévenus
    qu'une revue de cadrage est attendue avant toute nouvelle date (règle « 2 reports »)."""
    member_ids = {milestone.owner_member_id, project.owner_member_id} - {None}
    users = set(db.scalars(select(Membership.user_id).where(Membership.id.in_(member_ids)))) | set(
        db.scalars(
            select(Membership.user_id).where(
                Membership.space_id == project.space_id, Membership.role == Role.OWNER
            )
        )
    )
    users.discard(None)
    notify_milestone(
        db,
        membership.space,
        users,
        AlertRule.MILESTONE_REFRAME,
        milestone,
        project,
        f"Reporté {milestone.postpone_count} fois : revue de cadrage avant toute nouvelle date",
    )


@router.post("/milestones/{milestone_id}/close")
def close_milestone(
    milestone_id: uuid.UUID, body: MilestoneClose, membership: CurrentMembership, db: DbSession
) -> MilestoneOut:
    milestone, project = _load(db, membership, milestone_id)
    if milestone.version != body.version:
        raise HTTPException(409, CONFLICT)
    if milestone.state != MilestoneState.PLANNED:
        raise HTTPException(400, "Ce jalon est déjà clôturé : rouvrez-le d'abord.")
    state = MilestoneState(body.state)
    if state in (MilestoneState.MISSED, MilestoneState.CANCELLED) and not body.note:
        raise HTTPException(422, "Indiquez le motif.")
    milestone.state = state
    milestone.close_note = body.note or None
    milestone.closed_at = utcnow()
    milestone.version += 1
    project.updated_at = utcnow()
    _journal(
        db,
        membership,
        milestone,
        f"milestone.{state.value}",
        after={"note": body.note, "due_date": str(milestone.due_date)},
    )
    db.commit()
    return _one_out(db, membership, db.scalar(_query().where(Milestone.id == milestone.id)))


@router.post("/milestones/{milestone_id}/reopen")
def reopen_milestone(
    milestone_id: uuid.UUID, body: MilestoneVersion, membership: CurrentMembership, db: DbSession
) -> MilestoneOut:
    milestone, project = _load(db, membership, milestone_id)
    _writable(project)
    if milestone.version != body.version:
        raise HTTPException(409, CONFLICT)
    if milestone.state == MilestoneState.PLANNED:
        return _one_out(db, membership, milestone)
    previous = milestone.state
    milestone.state = MilestoneState.PLANNED
    milestone.closed_at = None
    milestone.version += 1
    _journal(
        db,
        membership,
        milestone,
        "milestone.reopened",
        before={"state": previous.value, "note": milestone.close_note},
    )
    milestone.close_note = None
    db.commit()
    return _one_out(db, membership, db.scalar(_query().where(Milestone.id == milestone.id)))


@router.put("/milestones/{milestone_id}/tasks")
def set_milestone_tasks(
    milestone_id: uuid.UUID, body: MilestoneTasks, membership: CurrentMembership, db: DbSession
) -> MilestoneOut:
    milestone, project = _load(db, membership, milestone_id)
    _writable(project)
    if milestone.version != body.version:
        raise HTTPException(409, CONFLICT)
    count = _set_tasks(db, milestone, project, body.task_ids)
    milestone.version += 1
    _journal(db, membership, milestone, "milestone.tasks", after={"tasks": count})
    db.commit()
    return _one_out(db, membership, db.scalar(_query().where(Milestone.id == milestone.id)))
