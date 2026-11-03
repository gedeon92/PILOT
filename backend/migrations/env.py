from alembic import context
from sqlalchemy import create_engine, pool

from pilot_api import models  # noqa: F401  (enregistre les tables dans Base.metadata)
from pilot_api.config import get_settings
from pilot_api.db import Base, to_sqlalchemy_url

target_metadata = Base.metadata


def _url() -> str:
    url = get_settings().database_url
    if not url:
        raise RuntimeError("DATABASE_URL n'est pas défini.")
    return to_sqlalchemy_url(url)


def run_migrations_offline() -> None:
    context.configure(url=_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
