"""Sections d'un projet (étape F1, cahier V2 STR02 et STR04).

Une section organise les tâches d'un projet ; ce n'est ni un statut ni une phase. Les
contributeurs du projet créent, renomment, réordonnent, archivent et restaurent les sections.
Rien n'est jamais supprimé : archiver propose de ranger ailleurs les tâches ouvertes.
Le journal des sections est rattaché au projet (visible dans son historique).
"""

import uuid

from fastapi import APIRouter, HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from pilot_api.audit import record
from pilot_api.deps import CurrentMembership, DbSession
from pilot_api.models import (
    CLOSED_TASK_STATUSES,
    Membership,
    Project,
    ProjectSection,
    Task,
    utcnow,
)
from pilot_api.routers.projects import CONFLICT, load_project
from pilot_api.schemas import (
    SectionArchive,
    SectionCreate,
    SectionOrder,
    SectionOut,
    SectionUpdate,
)

router = APIRouter(prefix="/api/spaces/{space_id}", tags=["sections"])

MAX_SECTIONS = 50
# Modèle de départ proposé par le cahier V2 (§02).
DEFAULT_SECTIONS = [
    ("Cadrage", "Objectif, périmètre, livrables, sponsor et critères de succès"),
    ("Préparation", "Plan d'action, moyens, calendrier et dépendances"),
    ("Exécution", "Actions opérationnelles et preuves"),
    ("Décisions et blocages", "Arbitrages, risques et engagements à suivre"),
    ("Contrôle et validation", "Livrables à approuver et jalons de passage"),
    ("Bilan et suites", "Résultats, actions résiduelles et capitalisation"),
]


def section_out(section: ProjectSection) -> SectionOut:
    return SectionOut(
        id=section.id,
        project_id=section.project_id,
        title=section.title,
        description=section.description,
        position=section.position,
        archived=section.archived_at is not None,
        version=section.version,
    )


def _sections(db: Session, project_id: uuid.UUID) -> list[ProjectSection]:
    return list(
        db.scalars(
            select(ProjectSection)
            .where(ProjectSection.project_id == project_id)
            .order_by(ProjectSection.position, ProjectSection.created_at)
        )
    )


def _load_section(
    db: Session, membership: Membership, section_id: uuid.UUID
) -> tuple[ProjectSection, Project]:
    section = db.get(ProjectSection, section_id, populate_existing=True)
    if section is None or section.space_id != membership.space_id:
        raise HTTPException(404, "Section introuvable.")
    project = load_project(db, membership, section.project_id, write=True)
    db.refresh(section, with_for_update=True)
    return section, project


def _journal(
    db: Session, membership: Membership, project: Project, action: str, after: dict
) -> None:
    project.updated_at = utcnow()
    record(
        db,
        action=action,
        actor_id=membership.user_id,
        space_id=project.space_id,
        target_type="project",
        target_id=project.id,
        after=after,
    )


def _active_count(db: Session, project_id: uuid.UUID) -> int:
    return (
        db.scalar(
            select(func.count(ProjectSection.id)).where(
                ProjectSection.project_id == project_id, ProjectSection.archived_at.is_(None)
            )
        )
        or 0
    )


def _next_position(db: Session, project_id: uuid.UUID) -> int:
    top = db.scalar(
        select(func.max(ProjectSection.position)).where(ProjectSection.project_id == project_id)
    )
    return (top or 0) + 1


@router.get("/projects/{project_id}/sections")
def list_sections(
    project_id: uuid.UUID, membership: CurrentMembership, db: DbSession
) -> list[SectionOut]:
    project = load_project(db, membership, project_id)
    return [section_out(s) for s in _sections(db, project.id)]


@router.post("/projects/{project_id}/sections", status_code=201)
def create_section(
    project_id: uuid.UUID, body: SectionCreate, membership: CurrentMembership, db: DbSession
) -> SectionOut:
    project = load_project(db, membership, project_id, write=True)
    if _active_count(db, project.id) >= MAX_SECTIONS:
        raise HTTPException(422, f"{MAX_SECTIONS} sections au plus par projet.")
    section = ProjectSection(
        space_id=project.space_id,
        project_id=project.id,
        title=body.title,
        description=body.description or None,
        position=_next_position(db, project.id),
    )
    db.add(section)
    db.flush()
    _journal(db, membership, project, "section.created", {"section": section.title})
    db.commit()
    return section_out(section)


@router.post("/projects/{project_id}/sections/defaults", status_code=201)
def create_default_sections(
    project_id: uuid.UUID, membership: CurrentMembership, db: DbSession
) -> list[SectionOut]:
    """Ajoute les six sections types, seulement si le projet n'en a encore aucune."""
    project = load_project(db, membership, project_id, write=True)
    if _sections(db, project.id):
        raise HTTPException(409, "Ce projet a déjà des sections.")
    for position, (title, description) in enumerate(DEFAULT_SECTIONS, start=1):
        db.add(
            ProjectSection(
                space_id=project.space_id,
                project_id=project.id,
                title=title,
                description=description,
                position=position,
            )
        )
    db.flush()
    _journal(
        db, membership, project, "section.defaults", {"sections": [t for t, _ in DEFAULT_SECTIONS]}
    )
    db.commit()
    return [section_out(s) for s in _sections(db, project.id)]


@router.patch("/sections/{section_id}")
def update_section(
    section_id: uuid.UUID, body: SectionUpdate, membership: CurrentMembership, db: DbSession
) -> SectionOut:
    section, project = _load_section(db, membership, section_id)
    if section.version != body.version:
        raise HTTPException(409, CONFLICT)
    before = {"section": section.title, "description": section.description}
    sent = body.model_fields_set
    if "title" in sent and body.title:
        section.title = body.title
    if "description" in sent:
        section.description = body.description or None
    after = {"section": section.title, "description": section.description}
    if after != before:
        section.version += 1
        _journal(
            db,
            membership,
            project,
            "section.renamed",
            {"section": section.title, "previous": before["section"]},
        )
        db.commit()
    return section_out(section)


@router.put("/projects/{project_id}/sections/order")
def reorder_sections(
    project_id: uuid.UUID, body: SectionOrder, membership: CurrentMembership, db: DbSession
) -> list[SectionOut]:
    project = load_project(db, membership, project_id, write=True)
    sections = _sections(db, project.id)
    active = {s.id: s for s in sections if s.archived_at is None}
    if len(body.ids) != len(set(body.ids)) or set(body.ids) != set(active):
        raise HTTPException(
            409, "La liste des sections a changé entre-temps. Rechargez la page avant de réessayer."
        )
    for position, sid in enumerate(body.ids, start=1):
        if active[sid].position != position:
            active[sid].position = position
            active[sid].version += 1
    _journal(
        db,
        membership,
        project,
        "section.reordered",
        {"sections": [active[i].title for i in body.ids]},
    )
    db.commit()
    return [section_out(s) for s in _sections(db, project.id)]


@router.post("/sections/{section_id}/archive")
def archive_section(
    section_id: uuid.UUID, body: SectionArchive, membership: CurrentMembership, db: DbSession
) -> SectionOut:
    section, project = _load_section(db, membership, section_id)
    if section.archived_at is not None:
        return section_out(section)
    moved = 0
    target_title = None
    if not body.keep_tasks:
        target = None
        if body.move_open_tasks_to is not None:
            target = db.get(ProjectSection, body.move_open_tasks_to)
            if (
                target is None
                or target.project_id != project.id
                or target.archived_at is not None
                or target.id == section.id
            ):
                raise HTTPException(422, "Choisissez une autre section active de ce projet.")
            target_title = target.title
        result = db.execute(
            update(Task)
            .where(
                Task.section_id == section.id,
                Task.status.not_in(CLOSED_TASK_STATUSES),
            )
            .values(section_id=target.id if target else None, version=Task.version + 1)
        )
        moved = result.rowcount or 0
    section.archived_at = utcnow()
    section.version += 1
    _journal(
        db,
        membership,
        project,
        "section.archived",
        {
            "section": section.title,
            "tasks_moved": moved,
            "moved_to": target_title or ("sans section" if not body.keep_tasks else None),
        },
    )
    db.commit()
    return section_out(section)


@router.post("/sections/{section_id}/restore")
def restore_section(
    section_id: uuid.UUID, membership: CurrentMembership, db: DbSession
) -> SectionOut:
    section, project = _load_section(db, membership, section_id)
    if section.archived_at is None:
        return section_out(section)
    if _active_count(db, project.id) >= MAX_SECTIONS:
        raise HTTPException(422, f"{MAX_SECTIONS} sections au plus par projet.")
    section.archived_at = None
    section.position = _next_position(db, project.id)
    section.version += 1
    _journal(db, membership, project, "section.restored", {"section": section.title})
    db.commit()
    return section_out(section)
