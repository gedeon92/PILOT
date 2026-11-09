"""Accès à un projet (WORKFLOW, suite « Asana », lot C).

Réservé aux propriétaires de l'espace (CDC §4 : « gérer les accès » leur appartient) :
rendre un projet privé, et donner à des personnes un rôle propre à ce projet. Chaque
changement est inscrit au journal du projet.
"""

import uuid

from fastapi import APIRouter, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from pilot_api.audit import record
from pilot_api.deps import CurrentMembership, DbSession, OwnerMembership
from pilot_api.models import Membership, ProjectMember, Role, User, utcnow
from pilot_api.routers.projects import load_project
from pilot_api.schemas import ProjectAccessIn, ProjectAccessMember, ProjectAccessOut

router = APIRouter(prefix="/api/spaces/{space_id}", tags=["projets"])

ROLE_WORDS = {"contributor": "contributeur", "reader": "lecteur"}


def _access_out(db: Session, project_id: uuid.UUID, private: bool) -> ProjectAccessOut:
    rows = db.execute(
        select(ProjectMember, Membership, User.display_name)
        .join(Membership, Membership.id == ProjectMember.member_id)
        .outerjoin(User, User.id == Membership.user_id)
        .where(ProjectMember.project_id == project_id)
        .order_by(ProjectMember.created_at)
    ).all()
    return ProjectAccessOut(
        private=private,
        members=[
            ProjectAccessMember(
                member_id=m.id,
                name=name or m.email,
                email=m.email,
                space_role=m.role,
                role=pm.role,
                has_account=m.user_id is not None,
            )
            for pm, m, name in rows
        ],
    )


@router.get("/projects/{project_id}/access")
def get_access(
    project_id: uuid.UUID, membership: CurrentMembership, db: DbSession
) -> ProjectAccessOut:
    """Visible par toute personne qui voit le projet : chacun sait qui y a accès."""
    project = load_project(db, membership, project_id)
    return _access_out(db, project.id, project.private)


@router.put("/projects/{project_id}/access")
def set_access(
    project_id: uuid.UUID, body: ProjectAccessIn, membership: OwnerMembership, db: DbSession
) -> ProjectAccessOut:
    project = load_project(db, membership, project_id)
    wanted = {m.member_id: m.role for m in body.members}
    if len(wanted) != len(body.members):
        raise HTTPException(422, "Une même personne apparaît deux fois.")
    members = {
        m.id: m
        for m in db.scalars(
            select(Membership).where(
                Membership.id.in_(wanted), Membership.space_id == membership.space_id
            )
        )
    }
    if set(members) != set(wanted):
        raise HTTPException(422, "Une des personnes n'appartient pas à l'espace.")
    # Un propriétaire voit déjà tout : inutile (et trompeur) de lui donner un rôle de projet.
    wanted = {mid: role for mid, role in wanted.items() if members[mid].role != Role.OWNER}

    before = _access_out(db, project.id, project.private)
    db.execute(delete(ProjectMember).where(ProjectMember.project_id == project.id))
    for member_id, role in wanted.items():
        db.add(ProjectMember(project_id=project.id, member_id=member_id, role=role))
    project.private = body.private
    project.updated_at = utcnow()
    db.flush()
    after = _access_out(db, project.id, project.private)

    def summary(access: ProjectAccessOut) -> dict:
        return {
            "private": access.private,
            "members": [f"{m.name} ({ROLE_WORDS[m.role.value]})" for m in access.members],
        }

    if summary(before) != summary(after):
        record(
            db,
            action="project.access_changed",
            actor_id=membership.user_id,
            space_id=project.space_id,
            target_type="project",
            target_id=project.id,
            before=summary(before),
            after=summary(after),
        )
    db.commit()
    return after
