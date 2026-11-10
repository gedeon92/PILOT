"""Application d'une proposition de l'assistant, après le clic de la personne.

Chaque proposition est exécutée par la route habituelle (création, modification, statut,
commentaire) : mêmes droits, mêmes règles, même journal. Une fiche modifiée depuis la
proposition donne un conflit : rien n'est appliqué, il faut redemander à l'assistant.
"""

import uuid

from fastapi import HTTPException
from sqlalchemy import update
from sqlalchemy.orm import Session

from pilot_api.deps import require_writer
from pilot_api.models import AiAction, AiActionState, Membership, Project, Task, utcnow
from pilot_api.routers import projects as P
from pilot_api.routers.task_collab import add_comment, create_subtask
from pilot_api.schemas import (
    CommentCreate,
    ProjectCreate,
    ProjectStatusChange,
    ProjectUpdate,
    TaskCreate,
    TaskUpdate,
)

CHANGED = (
    "La fiche a été modifiée depuis la proposition : rien n'a été appliqué. Redemandez à "
    "l'assistant, il repartira de la version actuelle."
)


def _current_version(db: Session, model: type, target_id: uuid.UUID, space_id: uuid.UUID) -> int:
    row = db.get(model, target_id, populate_existing=True)
    if row is None or row.space_id != space_id:
        raise HTTPException(404, "La fiche n'existe plus.")
    return row.version


def _run(db: Session, membership: Membership, action: AiAction) -> str:
    body = action.payload.get("body") or {}
    sid = membership.space_id
    if action.kind == "create_task":
        parent = action.payload.get("parent_task_id")
        if parent:
            task = create_subtask(uuid.UUID(parent), TaskCreate(**body), membership, db)
        else:
            task = P.create_task(action.target_id, TaskCreate(**body), membership, db)
        return f"Tâche « {task.title} » créée."
    if action.kind == "update_task":
        version = _current_version(db, Task, action.target_id, sid)
        if version != action.base_version:
            raise HTTPException(409, CHANGED)
        task = P.update_task(action.target_id, TaskUpdate(version=version, **body), membership, db)
        return f"Tâche « {task.title} » modifiée."
    if action.kind == "create_project":
        require_writer(membership)
        project = P.create_project(ProjectCreate(**body), membership, db)
        return f"Projet « {project.title} » créé."
    if action.kind == "update_project":
        version = _current_version(db, Project, action.target_id, sid)
        if version != action.base_version:
            raise HTTPException(409, CHANGED)
        project = P.update_project(
            action.target_id, ProjectUpdate(version=version, **body), membership, db
        )
        return f"Projet « {project.title} » modifié."
    if action.kind == "project_status":
        version = _current_version(db, Project, action.target_id, sid)
        if version != action.base_version:
            raise HTTPException(409, CHANGED)
        project = P.change_status(
            action.target_id, ProjectStatusChange(version=version, **body), membership, db
        )
        return f"Statut du projet « {project.title} » changé."
    if action.kind == "comment":
        add_comment(action.target_id, CommentCreate(**body), membership, db)
        return "Commentaire ajouté."
    raise HTTPException(400, "Proposition inconnue.")


def apply_action(db: Session, membership: Membership, action_id: uuid.UUID) -> AiAction:
    # Réservation atomique : deux clics (ou deux onglets) n'appliquent jamais deux fois.
    claimed = db.execute(
        update(AiAction)
        .where(
            AiAction.id == action_id,
            AiAction.user_id == membership.user_id,
            AiAction.space_id == membership.space_id,
            AiAction.state == AiActionState.PENDING,
        )
        .values(state=AiActionState.APPLIED, decided_at=utcnow())
    ).rowcount
    db.commit()
    action = _own_action(db, membership, action_id)
    if not claimed:
        raise HTTPException(409, "Cette proposition a déjà été traitée.")
    try:
        result = _run(db, membership, action)
        state = AiActionState.APPLIED
    except HTTPException as error:
        db.rollback()
        result = str(error.detail)
        state = AiActionState.CONFLICT if error.status_code == 409 else AiActionState.FAILED
    except Exception:
        db.rollback()
        result = "Le changement n'a pas pu être appliqué."
        state = AiActionState.FAILED
    action = _own_action(db, membership, action_id)
    action.state = state
    action.result = result
    db.commit()
    return action


def reject_action(db: Session, membership: Membership, action_id: uuid.UUID) -> AiAction:
    action = _own_action(db, membership, action_id, lock=True)
    if action.state != AiActionState.PENDING:
        raise HTTPException(409, "Cette proposition a déjà été traitée.")
    action.state = AiActionState.REJECTED
    action.decided_at = utcnow()
    action.result = "Refusée."
    db.commit()
    return action


def _own_action(
    db: Session, membership: Membership, action_id: uuid.UUID, lock: bool = False
) -> AiAction:
    action = db.get(
        AiAction, action_id, populate_existing=True, with_for_update=True if lock else None
    )
    if (
        action is None
        or action.user_id != membership.user_id
        or action.space_id != membership.space_id
    ):
        raise HTTPException(404, "Proposition introuvable.")
    return action
