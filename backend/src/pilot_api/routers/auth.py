from datetime import timedelta

from fastapi import APIRouter, HTTPException, Request, Response
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from pilot_api.audit import record
from pilot_api.config import get_settings
from pilot_api.deps import SESSION_COOKIE, CurrentUser, DbSession
from pilot_api.models import AuthSession, Membership, MembershipStatus, Space, User, utcnow
from pilot_api.schemas import LoginIn, MeOut, RegisterIn, SpaceSummary, UserOut
from pilot_api.security import (
    hash_password,
    hash_token,
    new_token,
    normalize_email,
    spend_verification_time,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["authentification"])


def _open_session(db: Session, response: Response, user: User) -> None:
    settings = get_settings()
    token, token_hash = new_token()
    lifetime = timedelta(days=settings.session_days)
    db.add(AuthSession(token_hash=token_hash, user_id=user.id, expires_at=utcnow() + lifetime))
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=int(lifetime.total_seconds()),
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def build_me(db: Session, user: User) -> MeOut:
    rows = db.execute(
        select(Space, Membership.role)
        .join(Membership, Membership.space_id == Space.id)
        .where(Membership.user_id == user.id, Membership.status == MembershipStatus.ACTIVE)
        .order_by(Space.name)
    ).all()
    return MeOut(
        user=UserOut(id=user.id, email=user.email, display_name=user.display_name),
        spaces=[SpaceSummary(id=space.id, name=space.name, role=role) for space, role in rows],
    )


@router.post("/register", status_code=201)
def register(body: RegisterIn, response: Response, db: DbSession) -> MeOut:
    email = normalize_email(body.email)
    if db.scalar(select(User.id).where(User.email == email)) is not None:
        raise HTTPException(409, "Un compte existe déjà avec cette adresse e-mail.")

    user = User(
        email=email, password_hash=hash_password(body.password), display_name=body.display_name
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        # Deux inscriptions simultanées avec la même adresse.
        db.rollback()
        raise HTTPException(409, "Un compte existe déjà avec cette adresse e-mail.") from None
    record(db, action="user.registered", actor_id=user.id, target_type="user", target_id=user.id)
    _open_session(db, response, user)
    db.commit()
    return build_me(db, user)


@router.post("/login")
def login(body: LoginIn, response: Response, db: DbSession) -> MeOut:
    user = db.scalar(select(User).where(User.email == normalize_email(body.email)))
    if user is None:
        spend_verification_time(body.password)
        raise HTTPException(401, "Adresse e-mail ou mot de passe incorrect.")
    if not verify_password(user.password_hash, body.password):
        raise HTTPException(401, "Adresse e-mail ou mot de passe incorrect.")

    _open_session(db, response, user)
    db.commit()
    return build_me(db, user)


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, db: DbSession) -> None:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        db.execute(delete(AuthSession).where(AuthSession.token_hash == hash_token(token)))
        db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.get("/me")
def me(user: CurrentUser, db: DbSession) -> MeOut:
    return build_me(db, user)
