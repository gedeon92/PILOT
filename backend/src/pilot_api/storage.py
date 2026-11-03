"""Stockage du contenu des fichiers.

Toute l'application passe par `FileStorage` : pour passer à un stockage objet
(S3, R2…), il suffira d'écrire une autre implémentation de ces trois méthodes.
"""

import uuid
from typing import Protocol

from sqlalchemy import delete
from sqlalchemy.orm import Session

from pilot_api.models import StoredFile


class FileStorage(Protocol):
    def put(self, key: uuid.UUID, data: bytes) -> None: ...
    def get(self, key: uuid.UUID) -> bytes | None: ...
    def delete(self, key: uuid.UUID) -> None: ...


class DatabaseStorage:
    """Fichiers dans PostgreSQL, dans la même transaction que leur fiche : un document
    n'existe jamais sans son contenu, ni l'inverse."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def put(self, key: uuid.UUID, data: bytes) -> None:
        self.db.add(StoredFile(key=key, data=data))

    def get(self, key: uuid.UUID) -> bytes | None:
        stored = self.db.get(StoredFile, key)
        return stored.data if stored else None

    def delete(self, key: uuid.UUID) -> None:
        self.db.execute(delete(StoredFile).where(StoredFile.key == key))


def get_storage(db: Session) -> FileStorage:
    return DatabaseStorage(db)
