"""Modèles de projet (suite « Asana », n° 2).

Les propriétaires de l'espace enregistrent les tâches d'un projet comme modèle, puis le
renomment ou le suppriment. Contributeurs et propriétaires choisissent un modèle à la création
d'un projet. Supprimer un modèle ne touche pas aux projets déjà créés avec lui.
"""

import uuid

from fastapi import APIRouter, HTTPException, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from pilot_api.access import ensure_visible
from pilot_api.audit import record
from pilot_api.deps import DbSession, OwnerMembership, WriterMembership
from pilot_api.models import Project, ProjectTemplate
from pilot_api.schemas import (
    TemplateCreate,
    TemplateMilestoneOut,
    TemplateOut,
    TemplateTaskOut,
    TemplateUpdate,
)
from pilot_api.templates import snapshot_milestones, snapshot_sections, snapshot_tasks

router = APIRouter(prefix="/api/spaces/{space_id}", tags=["modèles de projet"])

MAX_TEMPLATES = 200


def _out(template: ProjectTemplate) -> TemplateOut:
    tasks = [t for t in template.tasks or [] if isinstance(t, dict)]
    return TemplateOut(
        id=template.id,
        name=template.name,
        description=template.description,
        tasks_count=len(tasks),
        sections=[str(x) for x in template.sections or []],
        milestones=[
            TemplateMilestoneOut(
                title=str(m.get("title", "")),
                offset_days=m.get("offset_days"),
                critical=bool(m.get("critical")),
            )
            for m in template.milestones or []
            if isinstance(m, dict)
        ],
        tasks=[
            TemplateTaskOut(
                title=str(t.get("title", "")),
                offset_days=t.get("offset_days"),
                is_subtask=bool(t.get("parent")),
            )
            for t in tasks
        ],
        created_at=template.created_at,
        version=template.version,
    )


def _get(db: Session, space_id: uuid.UUID, template_id: uuid.UUID) -> ProjectTemplate:
    template = db.scalar(
        select(ProjectTemplate).where(
            ProjectTemplate.id == template_id, ProjectTemplate.space_id == space_id
        )
    )
    if template is None:
        raise HTTPException(404, "Modèle de projet introuvable.")
    return template


@router.get("/templates")
def list_templates(membership: WriterMembership, db: DbSession) -> list[TemplateOut]:
    templates = db.scalars(
        select(ProjectTemplate)
        .where(ProjectTemplate.space_id == membership.space_id)
        .order_by(func.lower(ProjectTemplate.name))
    ).all()
    return [_out(t) for t in templates]


@router.post("/templates", status_code=201)
def create_template(
    body: TemplateCreate, membership: OwnerMembership, db: DbSession
) -> TemplateOut:
    project = db.scalar(
        select(Project).where(
            Project.id == body.project_id, Project.space_id == membership.space_id
        )
    )
    if project is None:
        raise HTTPException(404, "Projet introuvable.")
    ensure_visible(db, membership, project)
    count = db.scalar(select(func.count()).where(ProjectTemplate.space_id == membership.space_id))
    if count >= MAX_TEMPLATES:
        raise HTTPException(400, f"{MAX_TEMPLATES} modèles au plus : supprimez-en un d'abord.")
    tasks = snapshot_tasks(db, project)
    if not tasks:
        raise HTTPException(
            422, "Ce projet n'a pas de tâche : ajoutez-en avant d'en faire un modèle."
        )
    template = ProjectTemplate(
        space_id=membership.space_id,
        name=body.name,
        description=body.description,
        tasks=tasks,
        sections=snapshot_sections(db, project) or None,
        milestones=snapshot_milestones(db, project) or None,
        created_by_id=membership.user_id,
    )
    db.add(template)
    db.flush()
    record(
        db,
        action="template.created",
        actor_id=membership.user_id,
        space_id=membership.space_id,
        target_type="template",
        target_id=template.id,
        after={"name": template.name, "from_project": project.title, "tasks": len(tasks)},
    )
    db.commit()
    return _out(template)


@router.patch("/templates/{template_id}")
def update_template(
    template_id: uuid.UUID, body: TemplateUpdate, membership: OwnerMembership, db: DbSession
) -> TemplateOut:
    template = _get(db, membership.space_id, template_id)
    db.refresh(template, with_for_update=True)
    if template.version != body.version:
        raise HTTPException(
            409, "Cet élément a été modifié entre-temps. Rechargez la page avant de réessayer."
        )
    before = {"name": template.name, "description": template.description}
    if body.name is not None:
        template.name = body.name
    if "description" in body.model_fields_set:
        template.description = body.description or None
    after = {"name": template.name, "description": template.description}
    if after != before:
        template.version += 1
        record(
            db,
            action="template.updated",
            actor_id=membership.user_id,
            space_id=membership.space_id,
            target_type="template",
            target_id=template.id,
            before=before,
            after=after,
        )
        db.commit()
    return _out(template)


@router.delete("/templates/{template_id}", status_code=204)
def delete_template(template_id: uuid.UUID, membership: OwnerMembership, db: DbSession) -> Response:
    template = _get(db, membership.space_id, template_id)
    record(
        db,
        action="template.deleted",
        actor_id=membership.user_id,
        space_id=membership.space_id,
        target_type="template",
        target_id=template.id,
        before={"name": template.name, "tasks": len(template.tasks or [])},
    )
    db.delete(template)
    db.commit()
    return Response(status_code=204)
