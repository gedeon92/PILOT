"""Documents des projets (CDC §11).

Tous les membres consultent et téléchargent ; contributeurs et propriétaires ajoutent et retirent.
Un fichier n'est jamais exécuté ni affiché dans la page : il est toujours servi en téléchargement.
"""

import hashlib
import mimetypes
import re
import unicodedata
import uuid
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from pilot_api.access import ensure_visible, ensure_writer, visible_projects
from pilot_api.audit import record
from pilot_api.config import get_settings
from pilot_api.deps import CurrentMembership, DbSession
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
        revision=document.revision,
        replaced_at=document.replaced_at,
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


def _read_limited(upload: UploadFile, limit: int) -> bytes:
    """Lit le fichier par morceaux et s'arrête dès que la limite est dépassée.
    Lecture synchrone : les routes d'envoi sont des fonctions ordinaires, exécutées par FastAPI
    hors de la boucle principale, pour qu'un gros fichier ne ralentisse pas les autres."""
    parts: list[bytes] = []
    total = 0
    while chunk := upload.file.read(CHUNK):
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
    ensure_visible(db, membership, project)
    documents = db.scalars(
        select(Document)
        .options(selectinload(Document.uploaded_by))
        .where(
            Document.project_id == project.id,
            Document.archived_at.is_(None),
            Document.replaced_at.is_(None),
        )
        .order_by(Document.created_at.desc())
    ).all()
    return [_document_out(d, project.title) for d in documents]


@router.get("/documents")
def list_space_documents(
    membership: CurrentMembership,
    db: DbSession,
    q: str | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[DocumentOut]:
    """Pièces de l'espace, les plus récentes d'abord, par pages (le contenu n'est jamais
    chargé ici : il se télécharge à la demande)."""
    query = (
        select(Document, Project.title)
        .join(Project, Project.id == Document.project_id)
        .options(selectinload(Document.uploaded_by))
        .where(
            Document.space_id == membership.space_id,
            Document.archived_at.is_(None),
            Document.replaced_at.is_(None),
            visible_projects(membership),
        )
    )
    if q:
        query = query.where(Document.filename.ilike(f"%{q.strip()}%"))
    rows = db.execute(
        query.order_by(Document.created_at.desc(), Document.id).offset(offset).limit(limit)
    ).all()
    return [_document_out(document, title) for document, title in rows]


def _store(
    file: UploadFile,
    project: Project,
    user_id: uuid.UUID,
    db: Session,
    previous: Document | None = None,
) -> Document:
    """Lit, vérifie et enregistre un fichier comme nouvelle fiche du projet."""
    limit = int(get_settings().max_upload_mb * 1024 * 1024)
    data = _read_limited(file, limit)
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
        uploaded_by_id=user_id,
        revision=previous.revision + 1 if previous else 1,
        previous_id=previous.id if previous else None,
    )
    get_storage(db).put(document.storage_key, data)
    db.add(document)
    db.flush()
    project.updated_at = utcnow()
    return document


@router.post("/projects/{project_id}/documents", status_code=201)
def upload_document(
    project_id: uuid.UUID, file: UploadFile, membership: CurrentMembership, db: DbSession
) -> DocumentOut:
    project = _get_project(db, membership.space_id, project_id)
    ensure_writer(db, membership, project)
    document = _store(file, project, membership.user_id, db)
    record(
        db,
        action="document.uploaded",
        actor_id=membership.user_id,
        space_id=project.space_id,
        target_type="document",
        target_id=document.id,
        after={
            "filename": document.filename,
            "size_bytes": document.size_bytes,
            "project_id": str(project.id),
        },
    )
    db.commit()
    return _document_out(_get_document(db, project.space_id, document.id), project.title)


@router.post("/documents/{document_id}/replace", status_code=201)
def replace_document(
    document_id: uuid.UUID, file: UploadFile, membership: CurrentMembership, db: DbSession
) -> DocumentOut:
    """Dépose une nouvelle version : l'ancienne est gardée et reste téléchargeable."""
    # Verrou : deux remplacements simultanés ne peuvent pas créer deux « versions courantes ».
    current = db.scalar(
        select(Document)
        .where(Document.id == document_id, Document.space_id == membership.space_id)
        .with_for_update()
    )
    if current is None:
        raise HTTPException(404, "Document introuvable.")
    ensure_writer(db, membership, db.get(Project, current.project_id))
    if current.archived_at is not None:
        raise HTTPException(409, "Ce document a été retiré : il ne peut plus être remplacé.")
    if current.replaced_at is not None:
        raise HTTPException(
            409, "Ce document a déjà été remplacé par une version plus récente. Rechargez la page."
        )
    project = db.get(Project, current.project_id)
    document = _store(file, project, membership.user_id, db, previous=current)
    current.replaced_at = utcnow()
    record(
        db,
        action="document.replaced",
        actor_id=membership.user_id,
        space_id=project.space_id,
        target_type="document",
        target_id=document.id,
        before={"filename": current.filename, "revision": current.revision},
        after={
            "filename": document.filename,
            "revision": document.revision,
            "size_bytes": document.size_bytes,
            "project_id": str(project.id),
        },
    )
    db.commit()
    return _document_out(_get_document(db, project.space_id, document.id), project.title)


MAX_VERSIONS = 100


@router.get("/documents/{document_id}/versions")
def document_versions(
    document_id: uuid.UUID, membership: CurrentMembership, db: DbSession
) -> list[DocumentOut]:
    """La version demandée puis toutes les précédentes, de la plus récente à la plus ancienne."""
    document = _get_document(db, membership.space_id, document_id)
    project = db.get(Project, document.project_id)
    ensure_visible(db, membership, project)
    title = project.title
    versions = [document]
    while versions[-1].previous_id and len(versions) < MAX_VERSIONS:
        previous = _get_document(db, membership.space_id, versions[-1].previous_id)
        versions.append(previous)
    return [_document_out(v, title) for v in versions]


@router.get("/documents/{document_id}/download")
def download_document(document_id: uuid.UUID, membership: CurrentMembership, db: DbSession):
    document = _get_document(db, membership.space_id, document_id)
    ensure_visible(db, membership, db.get(Project, document.project_id))
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
    document_id: uuid.UUID, membership: CurrentMembership, db: DbSession
) -> DocumentOut:
    document = _get_document(db, membership.space_id, document_id)
    project = db.get(Project, document.project_id)
    ensure_writer(db, membership, project)
    if document.replaced_at is not None:
        raise HTTPException(409, "Seule la version actuelle d'un document peut être retirée.")
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
