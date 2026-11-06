import html
import uuid
from datetime import timedelta

from fastapi import APIRouter, HTTPException, Response
from sqlalchemy import case, select
from sqlalchemy.orm import Session, selectinload

from pilot_api.alerts import is_test_address
from pilot_api.audit import record
from pilot_api.config import get_settings
from pilot_api.deps import CurrentMembership, CurrentUser, DbSession, OwnerMembership
from pilot_api.mailer import MailError, mail_configured, send_email
from pilot_api.models import (
    DEFAULT_PROJECT_TYPES,
    Membership,
    MembershipStatus,
    ProjectType,
    Role,
    Space,
    User,
    utcnow,
)
from pilot_api.schemas import (
    InvitationCreate,
    InvitationLink,
    MemberOut,
    MemberUpdate,
    SpaceCreate,
    SpaceOut,
    SpaceUpdate,
)
from pilot_api.security import new_token, normalize_email

router = APIRouter(prefix="/api/spaces", tags=["espaces"])


def _space_out(space: Space, role: Role) -> SpaceOut:
    return SpaceOut(
        id=space.id, name=space.name, timezone=space.timezone, version=space.version, role=role
    )


def _member_out(member: Membership, me: Membership) -> MemberOut:
    return MemberOut(
        id=member.id,
        email=member.email,
        display_name=member.user.display_name if member.user else None,
        role=member.role,
        status=member.status,
        is_me=member.id == me.id,
        joined_at=member.joined_at,
        invite_expires_at=member.invite_expires_at,
        version=member.version,
    )


def _get_member(db: Session, space_id: uuid.UUID, member_id: uuid.UUID) -> Membership:
    member = db.scalar(
        select(Membership)
        .options(selectinload(Membership.user))
        .where(Membership.id == member_id, Membership.space_id == space_id)
    )
    if member is None:
        raise HTTPException(404, "Membre introuvable.")
    return member


def _check_version(current: int, sent: int) -> None:
    if current != sent:
        raise HTTPException(
            409, "Cet élément a été modifié entre-temps. Rechargez la page avant de réessayer."
        )


@router.post("", status_code=201)
def create_space(body: SpaceCreate, user: CurrentUser, db: DbSession) -> SpaceOut:
    space = Space(name=body.name, timezone=body.timezone)
    db.add(space)
    db.flush()
    db.add(
        Membership(
            space_id=space.id,
            user_id=user.id,
            email=user.email,
            role=Role.OWNER,
            status=MembershipStatus.ACTIVE,
            joined_at=utcnow(),
        )
    )
    db.add_all(
        ProjectType(space_id=space.id, name=name, kind=kind) for name, kind in DEFAULT_PROJECT_TYPES
    )
    record(
        db,
        action="space.created",
        actor_id=user.id,
        space_id=space.id,
        target_type="space",
        target_id=space.id,
        after={"name": space.name, "timezone": space.timezone},
    )
    db.commit()
    return _space_out(space, Role.OWNER)


@router.get("/{space_id}")
def get_space(membership: CurrentMembership) -> SpaceOut:
    return _space_out(membership.space, membership.role)


@router.patch("/{space_id}")
def update_space(body: SpaceUpdate, membership: OwnerMembership, db: DbSession) -> SpaceOut:
    space = membership.space
    _check_version(space.version, body.version)
    before = {"name": space.name, "timezone": space.timezone}
    if body.name is not None:
        space.name = body.name
    if body.timezone is not None:
        space.timezone = body.timezone
    after = {"name": space.name, "timezone": space.timezone}
    if after != before:
        space.version += 1
        record(
            db,
            action="space.updated",
            actor_id=membership.user_id,
            space_id=space.id,
            target_type="space",
            target_id=space.id,
            before=before,
            after=after,
        )
        db.commit()
    return _space_out(space, membership.role)


@router.get("/{space_id}/members")
def list_members(membership: CurrentMembership, db: DbSession) -> list[MemberOut]:
    members = db.scalars(
        select(Membership)
        .options(selectinload(Membership.user))
        .where(Membership.space_id == membership.space_id)
        .order_by(
            case((Membership.role == Role.OWNER, 0), else_=1),
            case((Membership.status == MembershipStatus.ACTIVE, 0), else_=1),
            Membership.email,
        )
    ).all()
    return [_member_out(member, membership) for member in members]


ROLE_NAMES = {Role.READER: "lecteur", Role.CONTRIBUTOR: "contributeur", Role.OWNER: "propriétaire"}


def _send_invitation(db: Session, member: Membership, token: str) -> tuple[bool, str | None]:
    """Envoie l'invitation par e-mail. Un échec n'annule pas l'invitation : le lien reste
    affiché à la propriétaire, qui peut le transmettre elle-même."""
    if not mail_configured():
        return False, "L'envoi d'e-mails n'est pas activé : transmettez le lien vous-même."
    if is_test_address(member.email):
        return False, "Adresse d'essai : aucun e-mail envoyé."
    space = db.get(Space, member.space_id)
    inviter = db.get(User, member.invited_by_id) if member.invited_by_id else None
    who = inviter.display_name if inviter else "Une personne"
    days = get_settings().invitation_days
    link = f"{get_settings().app_base_url.rstrip('/')}/invitation/{token}"
    role = ROLE_NAMES.get(member.role, "membre")
    text = (
        "Bonjour,\n\n"
        f"{who} vous invite à rejoindre l'espace « {space.name} » sur PILOT, "
        f"avec le rôle {role}.\n\n"
        f"Pour accepter (lien valable {days} jours) :\n{link}\n\n"
        "Si vous ne connaissez pas cette personne, ignorez cet e-mail."
    )
    page = (
        "<div style='font-family:Arial,sans-serif;color:#18181B;max-width:560px'>"
        "<p>Bonjour,</p>"
        f"<p><strong>{html.escape(who)}</strong> vous invite à rejoindre l'espace "
        f"<strong>{html.escape(space.name)}</strong> sur PILOT, avec le rôle {role}.</p>"
        f"<p><a href='{html.escape(link)}' style='background:#D0450A;color:#fff;padding:10px 18px;"
        "border-radius:10px;text-decoration:none;font-weight:700'>Rejoindre l'espace</a></p>"
        f"<p style='color:#6B7280;font-size:12px'>Lien valable {days} jours. Si vous ne "
        "connaissez pas cette personne, ignorez cet e-mail.</p></div>"
    )
    try:
        send_email(
            to_email=member.email,
            to_name=member.email,
            subject=f"PILOT · {who} vous invite dans « {space.name} »",
            html=page,
            text=text,
        )
    except MailError as error:
        return False, f"E-mail non envoyé ({error}) : transmettez le lien vous-même."
    return True, None


@router.post("/{space_id}/invitations", status_code=201)
def invite_member(
    body: InvitationCreate, membership: OwnerMembership, db: DbSession
) -> InvitationLink:
    email = normalize_email(body.email)
    existing = db.scalar(
        select(Membership.id).where(
            Membership.space_id == membership.space_id, Membership.email == email
        )
    )
    if existing is not None:
        raise HTTPException(409, "Cette personne est déjà membre de l'espace ou déjà invitée.")

    token, token_hash = new_token()
    member = Membership(
        space_id=membership.space_id,
        email=email,
        role=body.role,
        status=MembershipStatus.INVITED,
        invite_token_hash=token_hash,
        invite_expires_at=utcnow() + timedelta(days=get_settings().invitation_days),
        invited_by_id=membership.user_id,
    )
    db.add(member)
    db.flush()
    record(
        db,
        action="member.invited",
        actor_id=membership.user_id,
        space_id=membership.space_id,
        target_type="membership",
        target_id=member.id,
        after={"email": email, "role": body.role.value},
    )
    db.commit()
    emailed, note = _send_invitation(db, member, token)
    return InvitationLink(
        member=_member_out(member, membership), token=token, emailed=emailed, email_note=note
    )


@router.post("/{space_id}/members/{member_id}/invitation-link")
def renew_invitation_link(
    member_id: uuid.UUID, membership: OwnerMembership, db: DbSession
) -> InvitationLink:
    member = _get_member(db, membership.space_id, member_id)
    if member.status != MembershipStatus.INVITED:
        raise HTTPException(400, "Cette personne a déjà rejoint l'espace.")
    token, token_hash = new_token()
    member.invite_token_hash = token_hash
    member.invite_expires_at = utcnow() + timedelta(days=get_settings().invitation_days)
    member.version += 1
    record(
        db,
        action="member.invitation_renewed",
        actor_id=membership.user_id,
        space_id=membership.space_id,
        target_type="membership",
        target_id=member.id,
    )
    db.commit()
    emailed, note = _send_invitation(db, member, token)
    return InvitationLink(
        member=_member_out(member, membership), token=token, emailed=emailed, email_note=note
    )


@router.patch("/{space_id}/members/{member_id}")
def update_member(
    member_id: uuid.UUID, body: MemberUpdate, membership: OwnerMembership, db: DbSession
) -> MemberOut:
    member = _get_member(db, membership.space_id, member_id)
    if member.role == Role.OWNER:
        raise HTTPException(400, "Le rôle Propriétaire ne peut pas être modifié.")
    _check_version(member.version, body.version)
    if member.role != body.role:
        before = {"role": member.role.value}
        member.role = body.role
        member.version += 1
        record(
            db,
            action="member.role_changed",
            actor_id=membership.user_id,
            space_id=membership.space_id,
            target_type="membership",
            target_id=member.id,
            before=before,
            after={"role": body.role.value},
        )
        db.commit()
    return _member_out(member, membership)


@router.delete("/{space_id}/members/{member_id}", status_code=204)
def remove_member(member_id: uuid.UUID, membership: OwnerMembership, db: DbSession) -> Response:
    member = _get_member(db, membership.space_id, member_id)
    if member.role == Role.OWNER:
        raise HTTPException(400, "Le rôle Propriétaire ne peut pas être retiré.")
    action = (
        "member.removed"
        if member.status == MembershipStatus.ACTIVE
        else "member.invitation_revoked"
    )
    record(
        db,
        action=action,
        actor_id=membership.user_id,
        space_id=membership.space_id,
        target_type="membership",
        target_id=member.id,
        before={"email": member.email, "role": member.role.value, "status": member.status.value},
    )
    db.delete(member)
    db.commit()
    return Response(status_code=204)
