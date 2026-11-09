"""Droits par projet (WORKFLOW, suite « Asana », lot C ; CDC §4, point de gouvernance).

Règle unique, appliquée à tous les chemins de lecture et d'écriture :

- Propriétaire de l'espace : voit et modifie tout.
- Contributeur ou lecteur de l'espace :
  - projet ouvert : visible ; son rôle sur le projet est celui de l'espace, sauf si un rôle
    propre à ce projet a été donné (contributeur ou lecteur) ;
  - projet privé : visible seulement s'il est membre du projet, avec son rôle de projet.
- Invité extérieur : ne voit que les projets dont il est membre, avec son rôle de projet.

Un projet invisible répond « introuvable » (404), comme un espace dont on n'est pas membre :
son existence n'est pas révélée.
"""

import uuid

from fastapi import HTTPException
from sqlalchemy import ColumnElement, or_, select, true
from sqlalchemy.orm import Session

from pilot_api.models import Membership, Project, ProjectMember, ProjectRole, Role

WRITE_REFUSED = "Votre rôle sur ce projet permet de consulter, pas de modifier."


def visible_projects(membership: Membership) -> ColumnElement[bool]:
    """Condition SQL « ce projet est visible pour cette personne »."""
    if membership.role == Role.OWNER:
        return true()
    member_of = Project.id.in_(
        select(ProjectMember.project_id).where(ProjectMember.member_id == membership.id)
    )
    if membership.role == Role.GUEST:
        return member_of
    return or_(Project.private.is_(False), member_of)


def visible_project_ids(db: Session, membership: Membership) -> set[uuid.UUID] | None:
    """Identifiants des projets visibles ; `None` veut dire « tous » (propriétaire)."""
    if membership.role == Role.OWNER:
        return None
    return set(
        db.scalars(
            select(Project.id).where(
                Project.space_id == membership.space_id, visible_projects(membership)
            )
        )
    )


def project_role(db: Session, membership: Membership, project: Project) -> Role | None:
    """Rôle effectif sur ce projet, ou `None` s'il n'est pas visible."""
    if membership.role == Role.OWNER:
        return Role.OWNER
    override = db.scalar(
        select(ProjectMember.role).where(
            ProjectMember.project_id == project.id, ProjectMember.member_id == membership.id
        )
    )
    if override is not None:
        return Role.CONTRIBUTOR if override == ProjectRole.CONTRIBUTOR else Role.READER
    if project.private or membership.role == Role.GUEST:
        return None
    return membership.role


def ensure_visible(db: Session, membership: Membership, project: Project | None) -> None:
    if project is None or project_role(db, membership, project) is None:
        raise HTTPException(404, "Projet introuvable.")


def ensure_writer(db: Session, membership: Membership, project: Project) -> None:
    """Modifier un projet (fiche, tâches, documents, liens) : contributeur ou propriétaire."""
    role = project_role(db, membership, project)
    if role is None:
        raise HTTPException(404, "Projet introuvable.")
    if role not in (Role.OWNER, Role.CONTRIBUTOR):
        raise HTTPException(403, WRITE_REFUSED)


def can_see(
    membership: Membership,
    project_private: bool,
    overrides: dict[uuid.UUID, ProjectRole],
) -> bool:
    """Version sans requête, pour les calculs en lot (alertes) : `overrides` donne les rôles
    de projet de ce projet, par identifiant de membre."""
    if membership.role == Role.OWNER:
        return True
    if membership.id in overrides:
        return True
    return not project_private and membership.role != Role.GUEST


def project_overrides(db: Session, project_ids) -> dict[uuid.UUID, dict[uuid.UUID, ProjectRole]]:
    """Rôles de projet, par projet puis par membre."""
    result: dict[uuid.UUID, dict[uuid.UUID, ProjectRole]] = {}
    ids = list(project_ids)
    if not ids:
        return result
    for project_id, member_id, role in db.execute(
        select(ProjectMember.project_id, ProjectMember.member_id, ProjectMember.role).where(
            ProjectMember.project_id.in_(ids)
        )
    ):
        result.setdefault(project_id, {})[member_id] = role
    return result


def users_who_can_see(db: Session, project: Project, user_ids) -> set[uuid.UUID]:
    """Parmi ces comptes, ceux qui voient ce projet (notifications, alertes)."""
    users = {u for u in user_ids if u}
    if not users:
        return set()
    memberships = db.scalars(
        select(Membership).where(
            Membership.space_id == project.space_id, Membership.user_id.in_(users)
        )
    ).all()
    overrides = project_overrides(db, [project.id]).get(project.id, {})
    return {m.user_id for m in memberships if can_see(m, project.private, overrides)}
