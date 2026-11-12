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
from pilot_api.routers import custom_fields as CF
from pilot_api.routers import projects as P
from pilot_api.routers.decisions import create_decision
from pilot_api.routers.milestones import create_milestone
from pilot_api.routers.sections import create_section
from pilot_api.routers.task_collab import add_comment, create_subtask
from pilot_api.schemas import (
    CommentCreate,
    DecisionCreate,
    MilestoneCreate,
    ProjectCreate,
    ProjectStatusChange,
    ProjectUpdate,
    SectionCreate,
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


def _run(db: Session, membership: Membership, action: AiAction) -> str | tuple[str, uuid.UUID]:
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
        return f"Projet « {project.title} » créé.", project.id
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
    if action.kind == "full_project":
        return _full_project(db, membership, action.payload)  # (texte, projet créé)
    if action.kind == "custom_values":
        return _custom_values(db, membership, action.payload)
    if action.kind == "comment":
        add_comment(action.target_id, CommentCreate(**body), membership, db)
        return "Commentaire ajouté."
    raise HTTPException(400, "Proposition inconnue.")


def _custom_values(db: Session, membership: Membership, payload: dict) -> str:
    project = P.load_project(db, membership, uuid.UUID(payload["project_id"]), write=True)
    task = None
    if payload.get("task_id"):
        task = P.load_task(db, membership, uuid.UUID(payload["task_id"]), write=True)
    out = CF.project_fields_out(db, project)
    current = out.task_values.get(str(task.id), {}) if task else out.values
    if any(current.get(k) != v for k, v in (payload.get("before") or {}).items()):
        raise HTTPException(409, CHANGED)
    values = {uuid.UUID(k): v for k, v in payload["values"].items()}
    CF.write_values(db, membership, project, task, values)
    db.commit()
    return "Champs personnalisés enregistrés."


def _full_project(db: Session, membership: Membership, payload: dict) -> tuple[str, uuid.UUID]:
    """Projet complet : tout est vérifié avant la première écriture, puis créé dans l'ordre
    par les routes habituelles (mêmes droits, mêmes règles, même journal)."""
    require_writer(membership)
    project_body = ProjectCreate(**payload["project"])
    tasks = [
        (TaskCreate(**t["body"]), t.get("section"), [TaskCreate(title=x) for x in t["subtasks"]])
        for t in payload.get("tasks", [])
    ]
    milestones = [(m["body"], m.get("tasks", [])) for m in payload.get("milestones", [])]
    decisions = [DecisionCreate(**d) for d in payload.get("decisions", [])]

    project = P.create_project(project_body, membership, db)
    created = {"sections": 0, "tâches": 0, "sous-tâches": 0, "jalons": 0, "décisions": 0}
    try:
        section_ids = {}
        for title in payload.get("sections", []):
            section = create_section(project.id, SectionCreate(title=title), membership, db)
            section_ids[title] = section.id
            created["sections"] += 1
        task_ids = {}
        for body, section, subtasks in tasks:
            if section:
                body = body.model_copy(update={"section_id": section_ids.get(section)})
            task = P.create_task(project.id, body, membership, db)
            task_ids[task.title] = task.id
            created["tâches"] += 1
            for sub in subtasks:
                create_subtask(task.id, sub, membership, db)
                created["sous-tâches"] += 1
        for body, linked in milestones:
            create_milestone(
                project.id,
                MilestoneCreate(**body, task_ids=[task_ids[t] for t in linked if t in task_ids]),
                membership,
                db,
            )
            created["jalons"] += 1
        for body in decisions:
            complete = not missing_fields_for(body)
            create_decision(
                body.model_copy(update={"project_id": project.id, "validate_now": complete}),
                membership,
                db,
            )
            created["décisions"] += 1
    except HTTPException as error:
        db.rollback()
        done = ", ".join(f"{n} {k}" for k, n in created.items() if n)
        return (
            f"Projet « {project.title} » créé ({done or 'fiche seule'}), mais la suite s'est "
            f"arrêtée : {error.detail}"
        ), project.id
    done = ", ".join(f"{n} {k}" for k, n in created.items() if n)
    return f"Projet « {project.title} » créé" + (f" avec {done}." if done else "."), project.id


def missing_fields_for(body: DecisionCreate) -> list[str]:
    """Une décision complète est validée tout de suite ; sinon elle reste en brouillon."""
    from pilot_api.decision_rules import missing_fields
    from pilot_api.models import Decision

    probe = Decision(
        statement=body.statement,
        executor_member_id=body.executor_member_id,
        executor_label=body.executor_label,
        due_date=body.due_date,
        criterion=body.criterion,
    )
    return missing_fields(probe)


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
    created_id = None
    try:
        result = _run(db, membership, action)
        if isinstance(result, tuple):
            # Création d'un projet : la carte pourra ouvrir sa fiche.
            result, created_id = result
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
    if created_id is not None:
        action.target_id = created_id
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
