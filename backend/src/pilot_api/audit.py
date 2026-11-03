import uuid
from typing import Any

from sqlalchemy.orm import Session

from pilot_api.models import AuditLog


def record(
    db: Session,
    *,
    action: str,
    actor_id: uuid.UUID | None,
    target_type: str,
    target_id: uuid.UUID | str | None = None,
    space_id: uuid.UUID | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> None:
    """Ajoute une ligne au journal dans la même transaction que la modification qu'elle décrit."""
    db.add(
        AuditLog(
            action=action,
            actor_id=actor_id,
            target_type=target_type,
            target_id=str(target_id) if target_id is not None else None,
            space_id=space_id,
            before=before,
            after=after,
        )
    )
