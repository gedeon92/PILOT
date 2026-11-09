"""Export d'un espace (propriétaire) et import dans un nouvel espace (CDC §18, §19)."""

import re
import unicodedata

from fastapi import APIRouter, HTTPException, Response, UploadFile
from sqlalchemy.exc import DataError, IntegrityError

from pilot_api.audit import record
from pilot_api.deps import CurrentUser, DbSession, OwnerMembership
from pilot_api.models import Space, utcnow
from pilot_api.portability import ImportError_, build_export, import_space, read_archive
from pilot_api.routers.documents import _read_limited
from pilot_api.schemas import ImportResult

router = APIRouter(tags=["export"])

MAX_IMPORT_BYTES = 60 * 1024 * 1024


def _slug(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-zA-Z0-9]+", "-", ascii_name).strip("-").lower()[:40] or "espace"


@router.get("/api/spaces/{space_id}/export")
def export_space(
    membership: OwnerMembership, user: CurrentUser, db: DbSession, files: bool = True
) -> Response:
    """Photographie complète de l'espace, téléchargée en ZIP (propriétaire seulement)."""
    space = membership.space
    content, summary = build_export(db, space, user, with_files=files)
    record(
        db,
        action="space.exported",
        actor_id=user.id,
        space_id=space.id,
        target_type="space",
        target_id=space.id,
        after={**summary, "files_included": files},
    )
    db.commit()
    day = utcnow().date().isoformat()
    filename = f"pilot-{_slug(space.name)}-{day}.zip"
    return Response(
        content=content,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


@router.post("/api/space-imports", status_code=201)
def import_export(file: UploadFile, user: CurrentUser, db: DbSession) -> ImportResult:
    """Recrée un espace à partir d'un export, dans un nouvel espace dont on devient propriétaire."""
    raw = _read_limited(file, MAX_IMPORT_BYTES)
    if not raw:
        raise HTTPException(422, "Le fichier est vide.")
    try:
        data, files = read_archive(raw)
        report = import_space(db, user, data, files)
        db.commit()
    except ImportError_ as exc:
        db.rollback()
        raise HTTPException(422, str(exc)) from exc
    except (ValueError, TypeError, KeyError, AttributeError, DataError, IntegrityError) as exc:
        db.rollback()
        raise HTTPException(
            422, "Export invalide ou modifié : certaines valeurs ne peuvent pas être importées."
        ) from exc
    space = db.get(Space, report.space_id)
    return ImportResult(
        space_id=report.space_id,
        space_name=space.name if space else "",
        already_imported=report.already_imported,
        counts=report.counts,
        warnings=report.warnings,
    )
