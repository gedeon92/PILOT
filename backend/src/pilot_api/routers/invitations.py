from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from pilot_api.audit import record
from pilot_api.deps import CurrentUser, DbSession
from pilot_api.models import Membership, MembershipStatus, User, utcnow
from pilot_api.schemas import InvitationInfo, InvitationToken, SpaceSummary
from pilot_api.security import hash_token

# Le jeton passe dans le corps de la requête, pas dans l'URL de l'API,
# pour ne pas apparaître dans les journaux d'accès de l'hébergeur.
router = APIRouter(prefix="/api/invitations", tags=["invitations"])


def _find_invitation(db: Session, token: str) -> Membership:
    member = db.scalar(
        select(Membership).where(
            Membership.invite_token_hash == hash_token(token),
            Membership.status == MembershipStatus.INVITED,
        )
    )
    if member is None:
        raise HTTPException(404, "Invitation introuvable ou déjà utilisée.")
    return member


def _is_expired(member: Membership) -> bool:
    return member.invite_expires_at is None or member.invite_expires_at <= utcnow()


@router.post("/lookup")
def lookup_invitation(body: InvitationToken, user: CurrentUser, db: DbSession) -> InvitationInfo:
    member = _find_invitation(db, body.token)
    inviter = db.get(User, member.invited_by_id) if member.invited_by_id else None
    return InvitationInfo(
        space_name=member.space.name,
        role=member.role,
        email=member.email,
        invited_by=inviter.display_name if inviter else None,
        expired=_is_expired(member),
        email_matches=member.email == user.email,
    )


@router.post("/accept")
def accept_invitation(body: InvitationToken, user: CurrentUser, db: DbSession) -> SpaceSummary:
    member = _find_invitation(db, body.token)
    if _is_expired(member):
        raise HTTPException(410, "Cette invitation a expiré. Demandez un nouveau lien.")
    # Le lien seul ne suffit pas : il doit être ouvert par le compte de l'adresse invitée.
    if member.email != user.email:
        raise HTTPException(403, "Cette invitation est destinée à une autre adresse e-mail.")

    member.user_id = user.id
    member.status = MembershipStatus.ACTIVE
    member.invite_token_hash = None
    member.invite_expires_at = None
    member.joined_at = utcnow()
    member.version += 1
    record(
        db,
        action="member.joined",
        actor_id=user.id,
        space_id=member.space_id,
        target_type="membership",
        target_id=member.id,
        after={"role": member.role.value},
    )
    db.commit()
    return SpaceSummary(id=member.space_id, name=member.space.name, role=member.role)
