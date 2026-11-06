import html
from datetime import timedelta

from fastapi import APIRouter, HTTPException, Request, Response
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from pilot_api.audit import record
from pilot_api.config import get_settings
from pilot_api.deps import SESSION_COOKIE, CurrentUser, DbSession
from pilot_api.mailer import MailError, mail_configured, send_email
from pilot_api.models import (
    AuthSession,
    EmailChange,
    LoginFailure,
    Membership,
    MembershipStatus,
    PasswordReset,
    Space,
    User,
    utcnow,
)
from pilot_api.schemas import (
    EmailChangeRequest,
    EmailChangeSent,
    InvitationToken,
    LoginIn,
    MeOut,
    PasswordChange,
    PasswordResetConfirm,
    PasswordResetRequest,
    ProfileUpdate,
    RegisterIn,
    SpaceSummary,
    UserOut,
)
from pilot_api.security import (
    hash_password,
    hash_token,
    new_token,
    normalize_email,
    spend_verification_time,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["authentification"])

# Après 8 échecs en 15 minutes pour une même adresse, la connexion est suspendue 15 minutes.
MAX_LOGIN_FAILURES = 8
LOGIN_WINDOW_MINUTES = 15


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
    email = normalize_email(body.email)
    email_key = hash_token(email)
    since = utcnow() - timedelta(minutes=LOGIN_WINDOW_MINUTES)
    failures = db.scalar(
        select(func.count())
        .select_from(LoginFailure)
        .where(LoginFailure.email_hash == email_key, LoginFailure.created_at >= since)
    )
    if failures >= MAX_LOGIN_FAILURES:
        raise HTTPException(
            429,
            f"Trop de tentatives pour cette adresse. Réessayez dans {LOGIN_WINDOW_MINUTES} "
            "minutes, ou demandez de l'aide à la propriétaire de votre espace.",
        )

    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        spend_verification_time(body.password)
    if user is None or not verify_password(user.password_hash, body.password):
        db.add(LoginFailure(email_hash=email_key))
        db.commit()
        raise HTTPException(401, "Adresse e-mail ou mot de passe incorrect.")

    db.execute(delete(LoginFailure).where(LoginFailure.email_hash == email_key))
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


# ---------- Mon compte ----------

EMAIL_CHANGE_HOURS = 24


def _check_password(user: User, password: str) -> None:
    if not verify_password(user.password_hash, password):
        raise HTTPException(400, "Mot de passe actuel incorrect.")


@router.patch("/me")
def update_profile(body: ProfileUpdate, user: CurrentUser, db: DbSession) -> MeOut:
    if body.display_name != user.display_name:
        record(
            db,
            action="user.renamed",
            actor_id=user.id,
            target_type="user",
            target_id=user.id,
            before={"display_name": user.display_name},
            after={"display_name": body.display_name},
        )
        user.display_name = body.display_name
        db.commit()
    return build_me(db, user)


@router.post("/password", status_code=204)
def change_password(
    body: PasswordChange, request: Request, user: CurrentUser, db: DbSession
) -> None:
    _check_password(user, body.current_password)
    user.password_hash = hash_password(body.new_password)
    # Par sécurité, les autres sessions ouvertes (autres appareils) sont fermées.
    current = hash_token(request.cookies.get(SESSION_COOKIE, ""))
    db.execute(
        delete(AuthSession).where(AuthSession.user_id == user.id, AuthSession.token_hash != current)
    )
    record(
        db, action="user.password_changed", actor_id=user.id, target_type="user", target_id=user.id
    )
    db.commit()


@router.post("/email-change")
def request_email_change(
    body: EmailChangeRequest, user: CurrentUser, db: DbSession
) -> EmailChangeSent:
    _check_password(user, body.password)
    new_email = normalize_email(body.new_email)
    if new_email == user.email:
        raise HTTPException(400, "C'est déjà l'adresse de votre compte.")
    if db.scalar(select(User.id).where(User.email == new_email)) is not None:
        raise HTTPException(409, "Un compte existe déjà avec cette adresse e-mail.")
    if not mail_configured():
        raise HTTPException(
            503, "L'envoi d'e-mails n'est pas disponible : impossible de confirmer l'adresse."
        )

    token, token_hash = new_token()
    db.execute(delete(EmailChange).where(EmailChange.user_id == user.id))
    db.add(
        EmailChange(
            user_id=user.id,
            new_email=new_email,
            token_hash=token_hash,
            expires_at=utcnow() + timedelta(hours=EMAIL_CHANGE_HOURS),
        )
    )
    link = f"{get_settings().app_base_url.rstrip('/')}/compte/confirmer-email?jeton={token}"
    text = (
        f"Bonjour {user.display_name},\n\n"
        f"Pour utiliser {new_email} comme adresse de votre compte PILOT, ouvrez ce lien "
        f"(valable {EMAIL_CHANGE_HOURS} heures) :\n{link}\n\n"
        "Si vous n'êtes pas à l'origine de cette demande, ignorez cet e-mail."
    )
    page = (
        "<div style='font-family:Arial,sans-serif;color:#18181B;max-width:560px'>"
        f"<p>Bonjour {html.escape(user.display_name)},</p>"
        f"<p>Pour utiliser <strong>{html.escape(new_email)}</strong> comme adresse de votre compte "
        f"PILOT, confirmez-la (lien valable {EMAIL_CHANGE_HOURS} heures) :</p>"
        f"<p><a href='{html.escape(link)}' style='background:#D0450A;color:#fff;padding:10px 18px;"
        "border-radius:10px;text-decoration:none;font-weight:700'>Confirmer mon adresse</a></p>"
        "<p style='color:#6B7280;font-size:12px'>Si vous n'êtes pas à l'origine de cette demande, "
        "ignorez cet e-mail : votre adresse actuelle reste inchangée.</p></div>"
    )
    try:
        send_email(
            to_email=new_email,
            to_name=user.display_name,
            subject="PILOT · Confirmez votre nouvelle adresse e-mail",
            html=page,
            text=text,
        )
    except MailError as error:
        db.rollback()
        raise HTTPException(502, str(error)) from None
    record(
        db,
        action="user.email_change_requested",
        actor_id=user.id,
        target_type="user",
        target_id=user.id,
        after={"new_email": new_email},
    )
    db.commit()
    return EmailChangeSent(sent_to=new_email, expires_hours=EMAIL_CHANGE_HOURS)


@router.post("/email-change/confirm")
def confirm_email_change(body: InvitationToken, user: CurrentUser, db: DbSession) -> MeOut:
    change = db.scalar(select(EmailChange).where(EmailChange.token_hash == hash_token(body.token)))
    # Le lien ne vaut que pour le compte qui a fait la demande.
    if change is None or change.user_id != user.id:
        raise HTTPException(404, "Lien de confirmation introuvable ou déjà utilisé.")
    if change.expires_at <= utcnow():
        raise HTTPException(410, "Ce lien a expiré. Refaites la demande depuis « Mon compte ».")
    if db.scalar(select(User.id).where(User.email == change.new_email)) is not None:
        raise HTTPException(409, "Un compte existe déjà avec cette adresse e-mail.")

    old_email = user.email
    memberships = db.scalars(select(Membership).where(Membership.user_id == user.id)).all()
    for membership in memberships:
        # Une invitation en attente pour la nouvelle adresse dans le même espace devient sans objet.
        db.execute(
            delete(Membership).where(
                Membership.space_id == membership.space_id,
                Membership.email == change.new_email,
                Membership.user_id.is_(None),
            )
        )
        membership.email = change.new_email
    user.email = change.new_email
    db.delete(change)
    record(
        db,
        action="user.email_changed",
        actor_id=user.id,
        target_type="user",
        target_id=user.id,
        before={"email": old_email},
        after={"email": change.new_email},
    )
    db.commit()
    return build_me(db, user)


# ---------- Mot de passe oublié ----------

RESET_MINUTES = 60
# Un seul e-mail toutes les 2 minutes par compte, pour éviter d'inonder une boîte.
RESET_COOLDOWN_SECONDS = 120
RESET_SENT = (
    "Si un compte existe avec cette adresse, un e-mail vient de lui être envoyé avec un lien "
    f"pour choisir un nouveau mot de passe (valable {RESET_MINUTES} minutes). Pensez à regarder "
    "dans les courriers indésirables."
)


@router.post("/password-reset", status_code=202)
def request_password_reset(body: PasswordResetRequest, db: DbSession) -> dict[str, str]:
    """La réponse est la même que le compte existe ou non : on ne révèle pas qui est inscrit."""
    email = normalize_email(body.email)
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        return {"message": RESET_SENT}
    if not mail_configured():
        raise HTTPException(
            503,
            "L'envoi d'e-mails n'est pas disponible pour le moment. Demandez à la propriétaire "
            "de votre espace de vous aider.",
        )
    recent = db.scalar(
        select(PasswordReset.id).where(
            PasswordReset.user_id == user.id,
            PasswordReset.created_at >= utcnow() - timedelta(seconds=RESET_COOLDOWN_SECONDS),
        )
    )
    if recent is not None:
        return {"message": RESET_SENT}

    token, token_hash = new_token()
    db.execute(delete(PasswordReset).where(PasswordReset.user_id == user.id))
    db.add(
        PasswordReset(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=utcnow() + timedelta(minutes=RESET_MINUTES),
        )
    )
    link = f"{get_settings().app_base_url.rstrip('/')}/mot-de-passe/nouveau?jeton={token}"
    text = (
        f"Bonjour {user.display_name},\n\n"
        "Pour choisir un nouveau mot de passe PILOT, ouvrez ce lien "
        f"(valable {RESET_MINUTES} minutes, une seule fois) :\n{link}\n\n"
        "Si vous n'avez rien demandé, ignorez cet e-mail : votre mot de passe reste inchangé."
    )
    page = (
        "<div style='font-family:Arial,sans-serif;color:#18181B;max-width:560px'>"
        f"<p>Bonjour {html.escape(user.display_name)},</p>"
        "<p>Pour choisir un nouveau mot de passe PILOT, cliquez sur le bouton "
        f"(lien valable {RESET_MINUTES} minutes, une seule fois) :</p>"
        f"<p><a href='{html.escape(link)}' style='background:#D0450A;color:#fff;padding:10px 18px;"
        "border-radius:10px;text-decoration:none;font-weight:700'>Choisir un nouveau mot de "
        "passe</a></p>"
        "<p style='color:#6B7280;font-size:12px'>Si vous n'avez rien demandé, ignorez cet "
        "e-mail : votre mot de passe reste inchangé.</p></div>"
    )
    try:
        send_email(
            to_email=user.email,
            to_name=user.display_name,
            subject="PILOT · Choisir un nouveau mot de passe",
            html=page,
            text=text,
        )
    except MailError as error:
        db.rollback()
        raise HTTPException(502, str(error)) from None
    record(
        db,
        action="user.password_reset_requested",
        actor_id=user.id,
        target_type="user",
        target_id=user.id,
    )
    db.commit()
    return {"message": RESET_SENT}


@router.post("/password-reset/confirm")
def confirm_password_reset(body: PasswordResetConfirm, response: Response, db: DbSession) -> MeOut:
    reset = db.scalar(
        select(PasswordReset)
        .where(PasswordReset.token_hash == hash_token(body.token))
        .with_for_update()
    )
    if reset is None:
        raise HTTPException(404, "Lien introuvable ou déjà utilisé. Refaites la demande.")
    if reset.expires_at <= utcnow():
        db.delete(reset)
        db.commit()
        raise HTTPException(410, "Ce lien a expiré. Refaites la demande « Mot de passe oublié ».")
    user = db.get(User, reset.user_id)
    user.password_hash = hash_password(body.new_password)
    # Toutes les sessions ouvertes sont fermées : si quelqu'un d'autre était connecté, il sort.
    db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
    db.execute(delete(PasswordReset).where(PasswordReset.user_id == user.id))
    db.execute(delete(LoginFailure).where(LoginFailure.email_hash == hash_token(user.email)))
    record(
        db, action="user.password_reset", actor_id=user.id, target_type="user", target_id=user.id
    )
    _open_session(db, response, user)
    db.commit()
    return build_me(db, user)
