import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

_hasher = PasswordHasher()
# Vérifié quand l'adresse est inconnue, pour que la réponse prenne le même temps
# et ne révèle pas quelles adresses ont un compte.
_DUMMY_HASH = _hasher.hash("pilot-mot-de-passe-factice")


def normalize_email(email: str) -> str:
    return email.strip().lower()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def spend_verification_time(password: str) -> None:
    verify_password(_DUMMY_HASH, password)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_token() -> tuple[str, str]:
    """Retourne le jeton à remettre à l'utilisateur et son empreinte à stocker."""
    token = secrets.token_urlsafe(32)
    return token, hash_token(token)
