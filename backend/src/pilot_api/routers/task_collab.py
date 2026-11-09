"""Tâches complètes (WORKFLOW, suite « Asana », lot A) : fiche d'une tâche, sous-tâches,
commentaires avec mentions, abonnés et dépendances.

Les droits restent ceux de l'espace : les lecteurs consultent et peuvent suivre une tâche
(être prévenus ne modifie rien) ; contributeurs et propriétaires commentent et modifient.
Chaque action est inscrite au journal du projet.
"""

import uuid

from fastapi import APIRouter, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from pilot_api.access import project_role, visible_project_ids
from pilot_api.alerts import notify
from pilot_api.audit import record
from pilot_api.deps import CurrentMembership, DbSession
from pilot_api.models import (
    CLOSED_TASK_STATUSES,
    AlertRule,
    Membership,
    MembershipStatus,
    Project,
    Role,
    Task,
    TaskComment,
    TaskDependency,
    TaskFollower,
    User,
    utcnow,
)
from pilot_api.routers.projects import (
    actor_name,
    create_task_in,
    follow,
    load_task,
    notify_followers,
    task_out,
    tasks_out,
    today_in,
)
from pilot_api.schemas import (
    CommentCreate,
    CommentOut,
    DependencyCreate,
    FollowerOut,
    MentionRef,
    TaskCreate,
    TaskDetail,
    TaskOut,
    TaskRef,
)

router = APIRouter(prefix="/api/spaces/{space_id}", tags=["tâches"])

MAX_DEPENDENCIES = 20


def _refs(db: Session, tasks: list[Task]) -> list[TaskRef]:
    titles = dict(
        db.execute(
            select(Project.id, Project.title).where(
                Project.id.in_({t.project_id for t in tasks if t.project_id})
            )
        ).all()
    )
    return [
        TaskRef(
            id=t.id,
            title=t.title,
            status=t.status,
            project_id=t.project_id,
            project_title=titles.get(t.project_id),
        )
        for t in tasks
    ]


def _touch(db: Session, task: Task) -> None:
    if task.project_id:
        project = db.get(Project, task.project_id)
        if project is not None:
            project.updated_at = utcnow()


@router.get("/tasks/{task_id}")
def task_detail(task_id: uuid.UUID, membership: CurrentMembership, db: DbSession) -> TaskDetail:
    task = load_task(db, membership, task_id)
    today = today_in(membership.space)
    subtasks = db.scalars(
        select(Task)
        .options(selectinload(Task.assignee_member).selectinload(Membership.user))
        .where(Task.parent_id == task.id)
        .order_by(Task.created_at)
    ).all()
    depends_on = db.scalars(
        select(Task)
        .join(TaskDependency, TaskDependency.depends_on_id == Task.id)
        .where(TaskDependency.task_id == task.id)
        .order_by(TaskDependency.created_at)
    ).all()
    blocking = db.scalars(
        select(Task)
        .join(TaskDependency, TaskDependency.task_id == Task.id)
        .where(TaskDependency.depends_on_id == task.id)
        .order_by(TaskDependency.created_at)
    ).all()
    # Les tâches d'un projet invisible pour cette personne ne sont pas montrées.
    visible = visible_project_ids(db, membership)

    def shown(items):
        return [t for t in items if visible is None or t.project_id in visible]

    depends_on, blocking = shown(depends_on), shown(blocking)
    parent = db.get(Task, task.parent_id) if task.parent_id else None
    comments = db.scalars(
        select(TaskComment).where(TaskComment.task_id == task.id).order_by(TaskComment.created_at)
    ).all()
    names = _member_names(db, membership.space_id)
    followers = db.execute(
        select(User.id, User.display_name)
        .join(TaskFollower, TaskFollower.user_id == User.id)
        .where(TaskFollower.task_id == task.id)
        .order_by(TaskFollower.created_at)
    ).all()
    project = db.get(Project, task.project_id) if task.project_id else None
    return TaskDetail(
        task=task_out(db, task, today),
        project_title=project.title if project else None,
        parent=_refs(db, [parent])[0] if parent else None,
        subtasks=tasks_out(db, list(subtasks), today),
        depends_on=_refs(db, list(depends_on)),
        blocking=_refs(db, list(blocking)),
        comments=[
            CommentOut(
                id=c.id,
                author_name=c.author_name,
                body=c.body,
                mentions=[
                    MentionRef(member_id=uuid.UUID(m), name=names[m])
                    for m in (c.mentions or [])
                    if m in names
                ],
                created_at=c.created_at,
                can_delete=c.author_id == membership.user_id or membership.role == Role.OWNER,
            )
            for c in comments
        ],
        followers=[FollowerOut(user_id=uid, name=name) for uid, name in followers],
        following=any(uid == membership.user_id for uid, _ in followers),
        can_write=_can_write(db, membership, project),
    )


def _can_write(db: Session, membership: Membership, project: Project | None) -> bool:
    if project is None:
        return membership.role in (Role.OWNER, Role.CONTRIBUTOR)
    return project_role(db, membership, project) in (Role.OWNER, Role.CONTRIBUTOR)


def _member_names(db: Session, space_id: uuid.UUID) -> dict[str, str]:
    rows = db.execute(
        select(Membership.id, Membership.email, User.display_name)
        .outerjoin(User, User.id == Membership.user_id)
        .where(Membership.space_id == space_id)
    ).all()
    return {str(mid): name or email for mid, email, name in rows}


# ---------- Sous-tâches ----------


@router.post("/tasks/{task_id}/subtasks", status_code=201)
def create_subtask(
    task_id: uuid.UUID, body: TaskCreate, membership: CurrentMembership, db: DbSession
) -> TaskOut:
    parent = load_task(db, membership, task_id, write=True)
    if parent.parent_id is not None:
        raise HTTPException(422, "Une sous-tâche ne peut pas avoir elle-même de sous-tâches.")
    if parent.status in CLOSED_TASK_STATUSES:
        raise HTTPException(400, "Cette tâche est clôturée : rouvrez-la pour la découper.")
    project = db.get(Project, parent.project_id) if parent.project_id else None
    return create_task_in(db, membership, project, body, parent=parent)


# ---------- Commentaires ----------


@router.post("/tasks/{task_id}/comments", status_code=201)
def add_comment(
    task_id: uuid.UUID, body: CommentCreate, membership: CurrentMembership, db: DbSession
) -> TaskDetail:
    task = load_task(db, membership, task_id, write=True)
    mentioned = db.execute(
        select(Membership.id, Membership.user_id).where(
            Membership.id.in_(set(body.mentions)),
            Membership.space_id == membership.space_id,
            Membership.status == MembershipStatus.ACTIVE,
            Membership.user_id.is_not(None),
        )
    ).all()
    who = actor_name(membership)
    comment = TaskComment(
        space_id=membership.space_id,
        task_id=task.id,
        author_id=membership.user_id,
        author_name=who[:120],
        body=body.body,
        mentions=[str(mid) for mid, _ in mentioned],
    )
    db.add(comment)
    db.flush()
    excerpt = body.body if len(body.body) <= 120 else body.body[:117] + "…"
    mentioned_users = {uid for _, uid in mentioned} - {membership.user_id}
    # Les personnes citées sont prévenues à part (« Mention ») et suivent désormais la tâche.
    notify(
        db,
        membership.space,
        mentioned_users,
        AlertRule.MENTION,
        task,
        f"{who} vous a mentionné : « {excerpt} »",
    )
    notify_followers(
        db, membership, task, f"{who} a commenté : « {excerpt} »", skip=mentioned_users
    )
    follow(db, task, [membership.user_id, *mentioned_users])
    _touch(db, task)
    record(
        db,
        action="task.commented",
        actor_id=membership.user_id,
        space_id=membership.space_id,
        target_type="task",
        target_id=task.id,
        after={"task": task.title, "comment": excerpt},
    )
    db.commit()
    return task_detail(task_id, membership, db)


@router.delete("/tasks/{task_id}/comments/{comment_id}", status_code=204)
def delete_comment(
    task_id: uuid.UUID, comment_id: uuid.UUID, membership: CurrentMembership, db: DbSession
) -> None:
    task = load_task(db, membership, task_id, write=True)
    comment = db.scalar(
        select(TaskComment).where(TaskComment.id == comment_id, TaskComment.task_id == task.id)
    )
    if comment is None:
        raise HTTPException(404, "Commentaire introuvable.")
    if comment.author_id != membership.user_id and membership.role != Role.OWNER:
        raise HTTPException(
            403, "Seuls son auteur ou un propriétaire peuvent retirer ce commentaire."
        )
    record(
        db,
        action="task.comment_deleted",
        actor_id=membership.user_id,
        space_id=membership.space_id,
        target_type="task",
        target_id=task.id,
        before={"task": task.title, "author": comment.author_name, "comment": comment.body[:120]},
    )
    db.delete(comment)
    db.commit()


# ---------- Abonnement ----------


@router.post("/tasks/{task_id}/follow")
def follow_task(task_id: uuid.UUID, membership: CurrentMembership, db: DbSession) -> TaskDetail:
    task = load_task(db, membership, task_id)
    follow(db, task, [membership.user_id])
    db.commit()
    return task_detail(task_id, membership, db)


@router.delete("/tasks/{task_id}/follow")
def unfollow_task(task_id: uuid.UUID, membership: CurrentMembership, db: DbSession) -> TaskDetail:
    task = load_task(db, membership, task_id)
    db.execute(
        delete(TaskFollower).where(
            TaskFollower.task_id == task.id, TaskFollower.user_id == membership.user_id
        )
    )
    db.commit()
    return task_detail(task_id, membership, db)


# ---------- Dépendances ----------


def _creates_cycle(db: Session, task_id: uuid.UUID, depends_on_id: uuid.UUID) -> bool:
    """Vrai si `depends_on_id` attend déjà (directement ou non) la fin de `task_id`."""
    seen, frontier = {depends_on_id}, [depends_on_id]
    while frontier:
        nxt = list(
            db.scalars(
                select(TaskDependency.depends_on_id).where(TaskDependency.task_id.in_(frontier))
            )
        )
        if task_id in nxt:
            return True
        frontier = [t for t in nxt if t not in seen]
        seen.update(frontier)
    return False


@router.post("/tasks/{task_id}/dependencies", status_code=201)
def add_dependency(
    task_id: uuid.UUID, body: DependencyCreate, membership: CurrentMembership, db: DbSession
) -> TaskDetail:
    task = load_task(db, membership, task_id, write=True)
    other = load_task(db, membership, body.depends_on_id)
    if other.id == task.id:
        raise HTTPException(422, "Une tâche ne peut pas attendre sa propre fin.")
    exists = db.scalar(
        select(TaskDependency.id).where(
            TaskDependency.task_id == task.id, TaskDependency.depends_on_id == other.id
        )
    )
    if exists:
        raise HTTPException(409, "Cette tâche attend déjà celle-ci.")
    count = len(
        db.scalars(select(TaskDependency.id).where(TaskDependency.task_id == task.id)).all()
    )
    if count >= MAX_DEPENDENCIES:
        raise HTTPException(422, f"Une tâche peut attendre {MAX_DEPENDENCIES} tâches au plus.")
    if _creates_cycle(db, task.id, other.id):
        raise HTTPException(
            422,
            f"« {other.title} » attend déjà la fin de cette tâche : les deux s'attendraient "
            "mutuellement.",
        )
    db.add(TaskDependency(space_id=membership.space_id, task_id=task.id, depends_on_id=other.id))
    _touch(db, task)
    record(
        db,
        action="task.dependency_added",
        actor_id=membership.user_id,
        space_id=membership.space_id,
        target_type="task",
        target_id=task.id,
        after={"task": task.title, "waits_for": other.title},
    )
    db.commit()
    return task_detail(task_id, membership, db)


@router.delete("/tasks/{task_id}/dependencies/{depends_on_id}")
def remove_dependency(
    task_id: uuid.UUID, depends_on_id: uuid.UUID, membership: CurrentMembership, db: DbSession
) -> TaskDetail:
    task = load_task(db, membership, task_id, write=True)
    link = db.scalar(
        select(TaskDependency).where(
            TaskDependency.task_id == task.id, TaskDependency.depends_on_id == depends_on_id
        )
    )
    if link is None:
        raise HTTPException(404, "Cette tâche n'attend pas celle-ci.")
    other = db.get(Task, depends_on_id)
    db.delete(link)
    _touch(db, task)
    record(
        db,
        action="task.dependency_removed",
        actor_id=membership.user_id,
        space_id=membership.space_id,
        target_type="task",
        target_id=task.id,
        before={"task": task.title, "waits_for": other.title if other else None},
    )
    db.commit()
    return task_detail(task_id, membership, db)
