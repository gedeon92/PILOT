import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from pilot_api.db import get_db
from pilot_api.models import AuthSession, Membership, MembershipStatus, Role, User, utcnow
from pilot_api.security import hash_token

SESSION_COOKIE = "pilot_session"
CSRF_HEADER = "X-PILOT-CSRF"

DbSession = Annotated[Session, Depends(get_db)]


def require_csrf_header(request: Request) -> None:
    """Un formulaire d'un autre site ne peut pas ajouter d'en-tête personnalisé ; une requête
    fetch d'un autre site qui le tenterait serait bloquée par le navigateur (pas de CORS ouvert)."""
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    if request.headers.get(CSRF_HEADER) != "1":
        raise HTTPException(403, "Requête refusée : en-tête de sécurité manquant.")


def get_current_user(request: Request, db: DbSession) -> User:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        session = db.scalar(select(AuthSession).where(AuthSession.token_hash == hash_token(token)))
        if session is not None and session.expires_at > utcnow():
            user = db.get(User, session.user_id)
            if user is not None:
                return user
    raise HTTPException(401, "Connexion requise.")


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_membership(space_id: uuid.UUID, user: CurrentUser, db: DbSession) -> Membership:
    """Le droit est relu en base à chaque requête : un retrait d'accès s'applique immédiatement."""
    membership = db.scalar(
        select(Membership).where(
            Membership.space_id == space_id,
            Membership.user_id == user.id,
            Membership.status == MembershipStatus.ACTIVE,
        )
    )
    if membership is None:
        # 404 plutôt que 403 : ne pas révéler l'existence d'un espace à un non-membre.
        raise HTTPException(404, "Espace introuvable.")
    return membership


CurrentMembership = Annotated[Membership, Depends(get_membership)]


def require_owner(membership: CurrentMembership) -> Membership:
    if membership.role != Role.OWNER:
        raise HTTPException(403, "Action réservée au rôle Propriétaire de l'espace.")
    return membership


OwnerMembership = Annotated[Membership, Depends(require_owner)]


def require_writer(membership: CurrentMembership) -> Membership:
    if membership.role == Role.READER:
        raise HTTPException(403, "Votre rôle Lecteur permet de consulter, pas de modifier.")
    if membership.role == Role.GUEST:
        # Un invité n'agit que dans ses projets (contrôle par projet, voir access.py).
        raise HTTPException(403, "Action réservée aux membres de l'espace.")
    return membership


WriterMembership = Annotated[Membership, Depends(require_writer)]
