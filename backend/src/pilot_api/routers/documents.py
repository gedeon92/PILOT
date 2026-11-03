"""Documents des projets (CDC §11).

Tous les membres consultent et téléchargent ; contributeurs et propriétaires ajoutent et retirent.
Un fichier n'est jamais exécuté ni affiché dans la page : il est toujours servi en téléchargement.
"""

import hashlib
import mimetypes
import re
import unicodedata
import uuid
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from pilot_api.audit import record
from pilot_api.config import get_settings
from pilot_api.deps import CurrentMembership, DbSession, WriterMembership
from pilot_api.models import Document, Project, utcnow
from pilot_api.schemas import DocumentOut
from pilot_api.storage import get_storage

router = APIRouter(prefix="/api/spaces/{space_id}", tags=["documents"])

CHUNK = 1024 * 1024


def clean_filename(name: str | None) -> str:
    """Garde un nom lisible sans chemin ni caractère de contrôle (le nom n'est qu'un libellé)."""
    base = re.split(r"[\\/]", name or "")[-1]
    base = "".join(
        c for c in unicodedata.normalize("NFC", base) if unicodedata.category(c)[0] != "C"
    )
    base = base.strip().strip(".") or "document"
    if len(base) > 255:
        stem, dot, ext = base.rpartition(".")
        base = (stem[: 250 - len(ext)] + dot + ext) if dot and len(ext) <= 10 else base[:255]
    return base


def _document_out(document: Document, project_title: str) -> DocumentOut:
    return DocumentOut(
        id=document.id,
        project_id=document.project_id,
        project_title=project_title,
        filename=document.filename,
        content_type=document.content_type,
        size_bytes=document.size_bytes,
        uploaded_by=document.uploaded_by.display_name if document.uploaded_by else None,
        created_at=document.created_at,
        archived=document.archived_at is not None,
    )


def _get_project(db: Session, space_id: uuid.UUID, project_id: uuid.UUID) -> Project:
    project = db.scalar(
        select(Project).where(Project.id == project_id, Project.space_id == space_id)
    )
    if project is None:
        raise HTTPException(404, "Projet introuvable.")
    return project


def _get_document(db: Session, space_id: uuid.UUID, document_id: uuid.UUID) -> Document:
    document = db.scalar(
        select(Document)
        .options(selectinload(Document.uploaded_by))
        .where(Document.id == document_id, Document.space_id == space_id)
    )
    if document is None:
        raise HTTPException(404, "Document introuvable.")
    return document


async def _read_limited(upload: UploadFile, limit: int) -> bytes:
    """Lit le fichier par morceaux et s'arrête dès que la limite est dépassée."""
    parts: list[bytes] = []
    total = 0
    while chunk := await upload.read(CHUNK):
        total += len(chunk)
        if total > limit:
            raise HTTPException(
                413, f"Fichier trop volumineux : {limit // (1024 * 1024)} Mo au maximum."
            )
        parts.append(chunk)
    return b"".join(parts)


@router.get("/projects/{project_id}/documents")
def list_project_documents(
    project_id: uuid.UUID, membership: CurrentMembership, db: DbSession
) -> list[DocumentOut]:
    project = _get_project(db, membership.space_id, project_id)
    documents = db.scalars(
        select(Document)
        .options(selectinload(Document.uploaded_by))
        .where(Document.project_id == project.id, Document.archived_at.is_(None))
        .order_by(Document.created_at.desc())
    ).all()
    return [_document_out(d, project.title) for d in documents]


@router.get("/documents")
def list_space_documents(
    membership: CurrentMembership, db: DbSession, q: str | None = None
) -> list[DocumentOut]:
    query = (
        select(Document, Project.title)
        .join(Project, Project.id == Document.project_id)
        .options(selectinload(Document.uploaded_by))
        .where(Document.space_id == membership.space_id, Document.archived_at.is_(None))
    )
    if q:
        query = query.where(Document.filename.ilike(f"%{q.strip()}%"))
    rows = db.execute(query.order_by(Document.created_at.desc()).limit(500)).all()
    return [_document_out(document, title) for document, title in rows]


@router.post("/projects/{project_id}/documents", status_code=201)
async def upload_document(
    project_id: uuid.UUID, file: UploadFile, membership: WriterMembership, db: DbSession
) -> DocumentOut:
    project = _get_project(db, membership.space_id, project_id)
    limit = int(get_settings().max_upload_mb * 1024 * 1024)
    data = await _read_limited(file, limit)
    if not data:
        raise HTTPException(422, "Le fichier est vide.")

    filename = clean_filename(file.filename)
    content_type = (
        file.content_type
        if file.content_type and file.content_type != "application/octet-stream"
        else mimetypes.guess_type(filename)[0] or "application/octet-stream"
    )
    document = Document(
        space_id=project.space_id,
        project_id=project.id,
        filename=filename,
        content_type=content_type[:120],
        size_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        storage_key=uuid.uuid4(),
        uploaded_by_id=membership.user_id,
    )
    get_storage(db).put(document.storage_key, data)
    db.add(document)
    db.flush()
    project.updated_at = utcnow()
    record(
        db,
        action="document.uploaded",
        actor_id=membership.user_id,
        space_id=project.space_id,
        target_type="document",
        target_id=document.id,
        after={"filename": filename, "size_bytes": len(data), "project_id": str(project.id)},
    )
    db.commit()
    return _document_out(_get_document(db, project.space_id, document.id), project.title)


@router.get("/documents/{document_id}/download")
def download_document(document_id: uuid.UUID, membership: CurrentMembership, db: DbSession):
    document = _get_document(db, membership.space_id, document_id)
    data = get_storage(db).get(document.storage_key)
    if data is None:
        raise HTTPException(410, "Le contenu de ce document n'est plus disponible.")
    ascii_name = document.filename.encode("ascii", "ignore").decode() or "document"
    ascii_name = ascii_name.replace('"', "")
    return Response(
        content=data,
        media_type=document.content_type,
        headers={
            # Toujours en pièce jointe : le navigateur n'interprète jamais le fichier dans la page.
            "Content-Disposition": (
                f'attachment; filename="{ascii_name}"; '
                f"filename*=UTF-8''{quote(document.filename)}"
            ),
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


@router.post("/documents/{document_id}/archive")
def archive_document(
    document_id: uuid.UUID, membership: WriterMembership, db: DbSession
) -> DocumentOut:
    document = _get_document(db, membership.space_id, document_id)
    project = db.get(Project, document.project_id)
    if document.archived_at is None:
        document.archived_at = utcnow()
        record(
            db,
            action="document.archived",
            actor_id=membership.user_id,
            space_id=document.space_id,
            target_type="document",
            target_id=document.id,
            before={"filename": document.filename},
        )
        db.commit()
    return _document_out(document, project.title if project else "")
