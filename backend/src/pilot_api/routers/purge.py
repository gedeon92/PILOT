"""Suppression définitive de projets (demande du 11 nov. 2026).

Seule exception à la règle « rien ne se supprime » : un propriétaire de l'espace peut effacer
des projets pour de bon (par exemple des projets d'essai), avec tout ce qu'ils contiennent :
tâches, sections, jalons, décisions du projet, documents et leurs fichiers, liens, accès,
propositions et historique. Il doit taper « SUPPRIMER » pour confirmer. Les réunions restent
(elles ne sont plus rattachées au projet) ; le journal de l'espace garde une seule ligne.
"""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, or_, select

from pilot_api.audit import record
from pilot_api.deps import DbSession, OwnerMembership
from pilot_api.models import (
    AuditLog,
    Decision,
    Document,
    Milestone,
    Project,
    Task,
)
from pilot_api.storage import get_storage

router = APIRouter(prefix="/api/spaces/{space_id}", tags=["suppression définitive"])

CONFIRM_WORD = "SUPPRIMER"


class PurgeIn(BaseModel):
    project_ids: Annotated[list[uuid.UUID], Field(min_length=1, max_length=500)]
    # Le mot tapé par la personne : une suppression n'arrive jamais par un clic distrait.
    confirm: Literal["SUPPRIMER"]


class PurgeOut(BaseModel):
    deleted: int
    titles: list[str]


@router.post("/projects/purge")
def purge_projects(body: PurgeIn, membership: OwnerMembership, db: DbSession) -> PurgeOut:
    ids = list(dict.fromkeys(body.project_ids))
    projects = db.scalars(
        select(Project)
        .where(Project.id.in_(ids), Project.space_id == membership.space_id)
        .with_for_update()
    ).all()
    if len(projects) != len(ids):
        raise HTTPException(404, "Un des projets est introuvable dans cet espace.")

    task_ids = list(db.scalars(select(Task.id).where(Task.project_id.in_(ids))))
    documents = db.scalars(select(Document).where(Document.project_id.in_(ids))).all()
    milestone_ids = list(db.scalars(select(Milestone.id).where(Milestone.project_id.in_(ids))))
    decision_ids = list(db.scalars(select(Decision.id).where(Decision.project_id.in_(ids))))

    # Historique propre à ces projets (le journal de l'espace garde le résumé ci-dessous).
    targets = [str(x) for x in [*ids, *task_ids, *milestone_ids, *decision_ids]] + [
        str(d.id) for d in documents
    ]
    if targets:
        db.execute(
            delete(AuditLog).where(
                AuditLog.space_id == membership.space_id,
                or_(
                    *[
                        AuditLog.target_id.in_(targets[i : i + 1000])
                        for i in range(0, len(targets), 1000)
                    ]
                ),
            )
        )
    storage = get_storage(db)
    for document in documents:
        storage.delete(document.storage_key)
    if decision_ids:
        db.execute(delete(Decision).where(Decision.id.in_(decision_ids)))
    titles = sorted(p.title for p in projects)
    # Le reste suit par les liens de la base (ON DELETE CASCADE : tâches, sections, jalons,
    # documents, liens, accès, propositions, alertes).
    db.execute(delete(Project).where(Project.id.in_(ids)))
    record(
        db,
        action="projects.purged",
        actor_id=membership.user_id,
        space_id=membership.space_id,
        target_type="space",
        target_id=membership.space_id,
        after={"count": len(projects), "titles": titles[:50]},
    )
    db.commit()
    return PurgeOut(deleted=len(projects), titles=titles)
