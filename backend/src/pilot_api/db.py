from functools import lru_cache

from sqlalchemy import Engine, create_engine, text

from pilot_api.config import get_settings


def to_sqlalchemy_url(url: str) -> str:
    """Neon fournit une URL postgresql:// ; SQLAlchemy doit savoir qu'on utilise psycopg 3."""
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix) :]
    return url


@lru_cache
def get_engine() -> Engine | None:
    url = get_settings().database_url
    if not url:
        return None
    # pool_pre_ping : Neon met en veille les bases inactives, une connexion peut être fermée.
    return create_engine(to_sqlalchemy_url(url), pool_pre_ping=True)


def check_database() -> str:
    engine = get_engine()
    if engine is None:
        return "not_configured"
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        return "unavailable"
    return "ok"
