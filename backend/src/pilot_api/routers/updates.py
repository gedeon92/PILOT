"""Boîte de mise à jour par texte ou document (CDC §9, §10, §11, §22).

Déposer un message ou des fichiers ne modifie aucun projet : PILOT prépare des propositions,
qu'un contributeur ou la propriétaire valide champ par champ. L'application vérifie la version
du projet et ne s'applique qu'une fois, même si le bouton est cliqué deux fois.

Confidentialité : une demande est privée par défaut (visible de son seul auteur) ; partagée,
elle est visible des contributeurs et propriétaires de l'espace. Les fichiers déposés restent
des sources d'analyse : ils n'entrent dans le dossier d'un projet que sur décision explicite.
"""

import hashlib
import mimetypes
import uuid
from datetime import date
from typing import Annotated, Any
from urllib.parse import quote

from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from pilot_api.access import (
    ensure_visible,
    ensure_writer,
    visible_project_ids,
    visible_projects,
)
from pilot_api.audit import record
from pilot_api.config import get_settings
from pilot_api.deps import DbSession, WriterMembership
from pilot_api.models import (
    CLOSED_PROJECT_STATUSES,
    OPEN_PROPOSAL_STATES,
    Document,
    EventDetails,
    ExtractionStatus,
    Membership,
    MembershipStatus,
    Project,
    ProjectStatus,
    Proposal,
    ProposalState,
    RiskLevel,
    UpdateRequest,
    UpdateSource,
    UpdateVisibility,
    utcnow,
)
from pilot_api.routers.documents import (
    _document_out,
    _get_document,
    _read_limited,
    clean_filename,
)
from pilot_api.routers.projects import (
    _check_dates,
    _diff,
    _load_project,
    _project_snapshot,
    _resolve_person,
)
from pilot_api.schemas import (
    DocumentOut,
    ProposalApply,
    ProposalChangeOut,
    ProposalDiscard,
    ProposalOut,
    ProposalProjectRef,
    ProposalTarget,
    SourceShare,
    UpdateRequestOut,
    UpdateRequestPatch,
    UpdateSourceOut,
)
from pilot_api.storage import get_storage
from pilot_api.updates.engine import (
    FIELD_NAMES,
    RISK_LABELS,
    STATUS_LABELS,
    MemberInfo,
    ProjectInfo,
    TextSource,
    analyse,
)
from pilot_api.updates.extract import extract_text

router = APIRouter(prefix="/api/spaces/{space_id}", tags=["mises à jour"])

MAX_FILES = 3
MAX_MESSAGE = 30_000
TARGET_ISSUES = ("Projet non identifié", "Plusieurs projets possibles")
STALE = (
    "Le projet a été modifié depuis la préparation de cette proposition. "
    "Recalculez-la sur la version actuelle avant de valider."
)


# ---------- Lecture ----------


def _visible(membership: Membership):
    return or_(
        UpdateRequest.author_id == membership.user_id,
        UpdateRequest.visibility == UpdateVisibility.SHARED,
    )


def _request_query():
    return select(UpdateRequest).options(
        selectinload(UpdateRequest.author),
        selectinload(UpdateRequest.sources),
        selectinload(UpdateRequest.proposals).selectinload(Proposal.decided_by),
    )


def _load_request(db: Session, membership: Membership, request_id: uuid.UUID) -> UpdateRequest:
    request = db.scalar(
        _request_query()
        .execution_options(populate_existing=True)
        .where(
            UpdateRequest.id == request_id,
            UpdateRequest.space_id == membership.space_id,
            _visible(membership),
        )
    )
    if request is None:
        raise HTTPException(404, "Demande introuvable.")
    return request


def _load_proposal(
    db: Session, membership: Membership, proposal_id: uuid.UUID, lock: bool = False
) -> Proposal:
    query = (
        select(Proposal)
        .join(UpdateRequest, UpdateRequest.id == Proposal.request_id)
        .where(
            Proposal.id == proposal_id,
            Proposal.space_id == membership.space_id,
            _visible(membership),
        )
    )
    if lock:
        # Deux clics simultanés : le second attend le premier, puis voit « Appliquée ».
        query = query.with_for_update(of=Proposal)
    proposal = db.scalar(query.execution_options(populate_existing=True))
    if proposal is None:
        raise HTTPException(404, "Proposition introuvable.")
    return proposal


def _projects_by_id(db: Session, ids: set[uuid.UUID]) -> dict[uuid.UUID, Project]:
    if not ids:
        return {}
    projects = db.scalars(
        select(Project)
        .execution_options(populate_existing=True)
        .options(
            selectinload(Project.portfolio),
            selectinload(Project.entity),
            selectinload(Project.owner_member).selectinload(Membership.user),
        )
        .where(Project.id.in_(ids))
    ).all()
    return {p.id: p for p in projects}


def _ref(project: Project) -> ProposalProjectRef:
    detail = [project.portfolio.name if project.portfolio else None]
    detail += [project.entity.name if project.entity else None, project.city]
    return ProposalProjectRef(
        id=project.id, title=project.title, detail=" · ".join(d for d in detail if d) or None
    )


def _owner_name(project: Project) -> str | None:
    member = project.owner_member
    if member is not None:
        return member.user.display_name if member.user else member.email
    return project.owner_label


def _current(project: Project, field: str) -> tuple[Any, str | None]:
    """Valeur actuelle du champ (pour comparer) et son affichage."""
    if field == "status":
        return project.status.value, STATUS_LABELS[project.status]
    if field == "progress":
        return project.progress, None if project.progress is None else f"{project.progress} %"
    if field == "due_date":
        day = project.due_date
        return (day.isoformat() if day else None), (day.strftime("%d/%m/%Y") if day else None)
    if field == "owner":
        value = {
            "member_id": str(project.owner_member_id) if project.owner_member_id else None,
            "label": None if project.owner_member_id else project.owner_label,
        }
        return value, _owner_name(project)
    if field == "risk_level":
        level = project.risk_level
        return (level.value if level else None), (RISK_LABELS[level] if level else None)
    value = getattr(project, field)
    return value, value


def _same(field: str, current: Any, proposed: Any) -> bool:
    if field == "owner":
        if proposed.get("member_id"):
            return proposed["member_id"] == current["member_id"]
        return not current["member_id"] and (current["label"] or "") == (proposed["label"] or "")
    return current == proposed


def _state(proposal: Proposal, project: Project | None) -> str:
    if proposal.state == ProposalState.TO_VALIDATE and (
        project is None or project.version != proposal.base_version
    ):
        return "conflict"
    return proposal.state.value


def _proposal_out(proposal: Proposal, projects: dict[uuid.UUID, Project]) -> ProposalOut:
    project = projects.get(proposal.project_id) if proposal.project_id else None
    changes = []
    for change in proposal.changes:
        field = change["field"]
        if project is not None:
            value, shown = _current(project, field)
            unchanged = proposal.state != ProposalState.APPLIED and _same(
                field, value, change["value"]
            )
        else:
            shown, unchanged = None, False
        if proposal.state == ProposalState.APPLIED:
            shown = proposal.before.get(field)  # valeur au moment de l'application
        changes.append(
            ProposalChangeOut(
                field=field,
                label=FIELD_NAMES[field],
                current=shown,
                proposed=change["display"],
                excerpt=change["excerpt"],
                unchanged=unchanged,
            )
        )
    candidates = [
        _ref(projects[uuid.UUID(c)]) for c in proposal.candidate_ids if uuid.UUID(c) in projects
    ]
    return ProposalOut(
        id=proposal.id,
        state=_state(proposal, project),
        project=_ref(project) if project else None,
        candidates=candidates,
        source_label=proposal.source_label,
        excerpt=proposal.excerpt,
        changes=changes,
        issues=proposal.issues,
        base_version=proposal.base_version,
        applied_fields=proposal.applied_fields,
        decided_by=proposal.decided_by.display_name if proposal.decided_by else None,
        decided_at=proposal.decided_at,
        discard_reason=proposal.discard_reason,
    )


def _requests_out(
    db: Session, membership: Membership, requests: list[UpdateRequest]
) -> list[UpdateRequestOut]:
    ids: set[uuid.UUID] = set()
    for request in requests:
        for proposal in request.proposals:
            if proposal.project_id:
                ids.add(proposal.project_id)
            ids.update(uuid.UUID(c) for c in proposal.candidate_ids)
    # Lot C : les propositions sur un projet invisible pour cette personne ne sont pas montrées,
    # et un projet invisible n'apparaît pas parmi les projets possibles.
    visible = visible_project_ids(db, membership)
    projects = {
        pid: p for pid, p in _projects_by_id(db, ids).items() if visible is None or pid in visible
    }
    return [
        UpdateRequestOut(
            id=r.id,
            created_at=r.created_at,
            author_name=r.author.display_name if r.author else None,
            mine=r.author_id == membership.user_id,
            visibility=r.visibility.value,
            message=r.message,
            sources=[
                UpdateSourceOut(
                    id=s.id,
                    filename=s.filename,
                    size_bytes=s.size_bytes,
                    extraction=s.extraction.value,
                    note=s.extraction_note,
                    chars=s.extracted_chars,
                )
                for s in r.sources
            ],
            proposals=[
                _proposal_out(p, projects)
                for p in r.proposals
                if p.project_id is None or p.project_id in projects
            ],
            notes=r.notes,
        )
        for r in requests
    ]


@router.get("/updates")
def list_updates(membership: WriterMembership, db: DbSession) -> list[UpdateRequestOut]:
    requests = db.scalars(
        _request_query()
        .where(UpdateRequest.space_id == membership.space_id, _visible(membership))
        .order_by(UpdateRequest.created_at.desc())
        .limit(30)
    ).all()
    return _requests_out(db, membership, list(requests))


@router.get("/updates/{request_id}")
def get_update(
    request_id: uuid.UUID, membership: WriterMembership, db: DbSession
) -> UpdateRequestOut:
    return _requests_out(db, membership, [_load_request(db, membership, request_id)])[0]


# ---------- Dépôt et préparation ----------


def _space_projects(db: Session, membership: Membership) -> list[Project]:
    """Projets que cette personne peut voir : seuls ceux-là peuvent être reconnus (lot C)."""
    return list(
        db.scalars(
            select(Project)
            .options(
                selectinload(Project.entity),
                selectinload(Project.owner_member).selectinload(Membership.user),
                selectinload(Project.event_details).selectinload(EventDetails.program),
            )
            .where(
                Project.space_id == membership.space_id,
                Project.status != ProjectStatus.CANCELLED,
                visible_projects(membership),
            )
        ).all()
    )


def _project_info(project: Project) -> ProjectInfo:
    hints = [project.entity.name if project.entity else None, project.city, project.country]
    details = project.event_details
    if details is not None:
        hints += [details.edition_label, details.program.name if details.program else None]
    return ProjectInfo(project.id, project.title, [h for h in hints if h])


def _members(db: Session, space_id: uuid.UUID) -> list[MemberInfo]:
    memberships = db.scalars(
        select(Membership)
        .options(selectinload(Membership.user))
        .where(Membership.space_id == space_id, Membership.status == MembershipStatus.ACTIVE)
    ).all()
    return [
        MemberInfo(m.id, m.user.display_name if m.user else m.email, m.email) for m in memberships
    ]


def _snapshot_before(project: Project, changes: list[dict[str, Any]]) -> dict[str, Any]:
    return {c["field"]: _current(project, c["field"])[1] for c in changes}


def _target(proposal: Proposal, project: Project) -> None:
    proposal.project_id = project.id
    proposal.base_version = project.version
    proposal.before = _snapshot_before(project, proposal.changes)
    proposal.state = ProposalState.TO_VALIDATE
    proposal.issues = [i for i in proposal.issues if not i.startswith(TARGET_ISSUES)]


@router.post("/updates", status_code=201)
async def create_update(
    membership: WriterMembership,
    db: DbSession,
    message: Annotated[str, Form(max_length=MAX_MESSAGE)] = "",
    visibility: Annotated[UpdateVisibility, Form()] = UpdateVisibility.PRIVATE,
    client_request_id: Annotated[uuid.UUID | None, Form()] = None,
    files: Annotated[list[UploadFile] | None, File()] = None,
) -> UpdateRequestOut:
    space_id = membership.space_id
    if client_request_id is not None:
        existing = db.scalar(
            select(UpdateRequest.id).where(
                UpdateRequest.space_id == space_id,
                UpdateRequest.client_request_id == client_request_id,
            )
        )
        if existing is not None:
            return _requests_out(db, membership, [_load_request(db, membership, existing)])[0]

    files = [f for f in (files or []) if f.filename]
    message = message.strip()
    if not message and not files:
        raise HTTPException(422, "Écrivez un message ou ajoutez au moins un fichier.")
    if len(files) > MAX_FILES:
        raise HTTPException(422, f"{MAX_FILES} fichiers au maximum par demande.")

    request = UpdateRequest(
        space_id=space_id,
        author_id=membership.user_id,
        message=message or None,
        visibility=visibility,
        client_request_id=client_request_id,
        notes=[],
    )
    db.add(request)
    texts: list[TextSource] = []
    if message:
        texts.append(TextSource("Message", message))

    limit = int(get_settings().max_upload_mb * 1024 * 1024)
    storage = get_storage(db)
    for position, upload in enumerate(files):
        data = await _read_limited(upload, limit)
        filename = clean_filename(upload.filename)
        if not data:
            raise HTTPException(422, f"Le fichier « {filename} » est vide.")
        extracted = extract_text(filename, data)
        content_type = (
            upload.content_type
            if upload.content_type and upload.content_type != "application/octet-stream"
            else mimetypes.guess_type(filename)[0] or "application/octet-stream"
        )
        source = UpdateSource(
            request=request,
            space_id=space_id,
            position=position,
            filename=filename,
            content_type=content_type[:120],
            size_bytes=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
            storage_key=uuid.uuid4(),
            extraction=extracted.status,
            extraction_note=extracted.note,
            extracted_chars=len(extracted.text),
        )
        storage.put(source.storage_key, data)
        db.add(source)
        if extracted.status == ExtractionStatus.READ:
            texts.append(TextSource(filename, extracted.text, filename))

    projects = _space_projects(db, membership)
    by_id = {p.id: p for p in projects}
    analysis = analyse(texts, [_project_info(p) for p in projects], _members(db, space_id))
    notes = list(analysis.notes)
    position = 0
    for draft in analysis.drafts:
        changes = [c.as_dict() for c in draft.changes]
        project = by_id.get(draft.target_id) if draft.target_id else None
        if project is not None and all(
            _same(c["field"], _current(project, c["field"])[0], c["value"]) for c in changes
        ):
            notes.append(f"« {project.title} » : déjà à jour, rien à proposer.")
            continue
        proposal = Proposal(
            request=request,
            space_id=space_id,
            position=position,
            state=ProposalState.TO_CLARIFY,
            candidate_ids=[str(c) for c in draft.candidate_ids],
            source_label=draft.source_label[:255],
            excerpt=draft.excerpt,
            changes=changes,
            issues=draft.issues,
            before={},
            applied_fields=[],
        )
        if project is not None:
            _target(proposal, project)
        db.add(proposal)
        position += 1
    request.notes = notes
    db.flush()
    record(
        db,
        action="update_request.created",
        actor_id=membership.user_id,
        space_id=space_id,
        target_type="update_request",
        target_id=request.id,
        after={"files": len(files), "proposals": position, "visibility": visibility.value},
    )
    db.commit()
    return _requests_out(db, membership, [_load_request(db, membership, request.id)])[0]


@router.patch("/updates/{request_id}")
def change_visibility(
    request_id: uuid.UUID, body: UpdateRequestPatch, membership: WriterMembership, db: DbSession
) -> UpdateRequestOut:
    request = _load_request(db, membership, request_id)
    if request.author_id != membership.user_id:
        raise HTTPException(403, "Seul l'auteur de la demande peut changer sa visibilité.")
    request.visibility = UpdateVisibility(body.visibility)
    db.commit()
    return _requests_out(db, membership, [_load_request(db, membership, request_id)])[0]


# ---------- Décisions ----------


def _proposal_response(db: Session, membership: Membership, proposal: Proposal) -> ProposalOut:
    db.refresh(proposal)
    ids = {proposal.project_id} if proposal.project_id else set()
    ids.update(uuid.UUID(c) for c in proposal.candidate_ids)
    visible = visible_project_ids(db, membership)
    projects = {
        pid: p for pid, p in _projects_by_id(db, ids).items() if visible is None or pid in visible
    }
    return _proposal_out(proposal, projects)


@router.post("/proposals/{proposal_id}/target")
def choose_target(
    proposal_id: uuid.UUID, body: ProposalTarget, membership: WriterMembership, db: DbSession
) -> ProposalOut:
    """Précise le projet visé quand le passage ne permettait pas de conclure."""
    proposal = _load_proposal(db, membership, proposal_id, lock=True)
    if proposal.state not in OPEN_PROPOSAL_STATES:
        raise HTTPException(409, "Cette proposition est déjà traitée.")
    project = db.scalar(
        select(Project)
        .options(selectinload(Project.owner_member).selectinload(Membership.user))
        .where(Project.id == body.project_id, Project.space_id == membership.space_id)
    )
    if project is None:
        raise HTTPException(404, "Projet introuvable.")
    ensure_writer(db, membership, project)
    _target(proposal, project)
    db.commit()
    return _proposal_response(db, membership, proposal)


@router.post("/proposals/{proposal_id}/refresh")
def refresh_proposal(
    proposal_id: uuid.UUID, membership: WriterMembership, db: DbSession
) -> ProposalOut:
    """Recalcule la proposition sur la version actuelle du projet (texte conservé)."""
    proposal = _load_proposal(db, membership, proposal_id, lock=True)
    if proposal.state != ProposalState.TO_VALIDATE or proposal.project_id is None:
        raise HTTPException(409, "Seule une proposition à valider peut être recalculée.")
    project = _projects_by_id(db, {proposal.project_id}).get(proposal.project_id)
    if project is None:
        raise HTTPException(404, "Projet introuvable.")
    ensure_visible(db, membership, project)
    _target(proposal, project)
    db.commit()
    return _proposal_response(db, membership, proposal)


def _actor_name(membership: Membership) -> str | None:
    return membership.user.display_name if membership.user else None


def _apply_change(db: Session, project: Project, field: str, value: Any) -> None:
    if field == "status":
        project.status = ProjectStatus(value)
    elif field == "progress":
        project.progress = int(value)
    elif field == "due_date":
        project.due_date = date.fromisoformat(value)
    elif field == "owner":
        member_id = uuid.UUID(value["member_id"]) if value.get("member_id") else None
        project.owner_member_id, project.owner_label = _resolve_person(
            db, project.space_id, member_id, value.get("label")
        )
    elif field == "risk_level":
        project.risk_level = RiskLevel(value) if value else None
    elif field in {"situation", "next_step", "decision_needed"}:
        setattr(project, field, value or None)
        if field == "situation":
            project.situation_updated_at = utcnow()
    else:
        raise HTTPException(422, f"Champ « {field} » non modifiable par une proposition.")


@router.post("/proposals/{proposal_id}/apply")
def apply_proposal(
    proposal_id: uuid.UUID, body: ProposalApply, membership: WriterMembership, db: DbSession
) -> ProposalOut:
    proposal = _load_proposal(db, membership, proposal_id, lock=True)
    if proposal.state == ProposalState.APPLIED:
        # Clic rejoué : rien n'est appliqué une seconde fois (CDC §9, UPD04).
        return _proposal_response(db, membership, proposal)
    if proposal.state == ProposalState.DISCARDED:
        raise HTTPException(409, "Cette proposition a été écartée.")
    if proposal.state == ProposalState.TO_CLARIFY or proposal.project_id is None:
        raise HTTPException(422, "Choisissez d'abord le projet visé.")

    project = db.scalar(
        select(Project)
        .where(Project.id == proposal.project_id, Project.space_id == membership.space_id)
        .with_for_update()
    )
    if project is None:
        raise HTTPException(404, "Projet introuvable.")
    ensure_writer(db, membership, project)
    if project.version != proposal.base_version or body.base_version != proposal.base_version:
        raise HTTPException(409, STALE)
    project = _load_project(db, membership.space_id, project.id)

    wanted = set(body.fields)
    selected = [c for c in proposal.changes if c["field"] in wanted]
    if not selected:
        raise HTTPException(422, "Cochez au moins une modification à appliquer.")
    if any(c["field"] == "status" and project.status in CLOSED_PROJECT_STATUSES for c in selected):
        raise HTTPException(
            422, "Ce projet est clos : rouvrez-le depuis sa fiche avant de changer son statut."
        )

    before_all = _project_snapshot(project)
    shown_before = _snapshot_before(project, proposal.changes)
    applied = []
    for change in selected:
        current, _ = _current(project, change["field"])
        if _same(change["field"], current, change["value"]):
            continue  # déjà la bonne valeur
        _apply_change(db, project, change["field"], change["value"])
        applied.append(change["field"])
    if "situation" in applied:
        # Source et fraîcheur (CDC §21) : la situation vient de cette demande.
        project.situation_source = "update"
        project.situation_source_label = proposal.source_label[:255]
        project.situation_updated_by = _actor_name(membership)
    _check_dates(project)

    old, new = _diff(before_all, _project_snapshot(project))
    if new:
        project.updated_at = utcnow()
        project.version += 1
        record(
            db,
            action="project.updated_from_proposal",
            actor_id=membership.user_id,
            space_id=project.space_id,
            target_type="project",
            target_id=project.id,
            before=old,
            after=new,
        )
    proposal.state = ProposalState.APPLIED
    proposal.applied_fields = applied
    proposal.before = shown_before
    proposal.decided_by_id = membership.user_id
    proposal.decided_at = utcnow()
    record(
        db,
        action="proposal.applied",
        actor_id=membership.user_id,
        space_id=project.space_id,
        target_type="proposal",
        target_id=proposal.id,
        after={"project_id": str(project.id), "fields": applied},
    )
    db.commit()
    return _proposal_response(db, membership, proposal)


@router.post("/proposals/{proposal_id}/discard")
def discard_proposal(
    proposal_id: uuid.UUID, body: ProposalDiscard, membership: WriterMembership, db: DbSession
) -> ProposalOut:
    proposal = _load_proposal(db, membership, proposal_id, lock=True)
    if proposal.project_id is not None:
        ensure_visible(db, membership, db.get(Project, proposal.project_id))
    if proposal.state == ProposalState.APPLIED:
        raise HTTPException(409, "Cette proposition est déjà appliquée.")
    if proposal.state != ProposalState.DISCARDED:
        proposal.state = ProposalState.DISCARDED
        proposal.discard_reason = (body.reason or "").strip() or None
        proposal.decided_by_id = membership.user_id
        proposal.decided_at = utcnow()
        record(
            db,
            action="proposal.discarded",
            actor_id=membership.user_id,
            space_id=membership.space_id,
            target_type="proposal",
            target_id=proposal.id,
            after={"reason": proposal.discard_reason},
        )
        db.commit()
    return _proposal_response(db, membership, proposal)


# ---------- Fichiers sources ----------


def _load_source(db: Session, membership: Membership, source_id: uuid.UUID) -> UpdateSource:
    source = db.scalar(
        select(UpdateSource)
        .join(UpdateRequest, UpdateRequest.id == UpdateSource.request_id)
        .where(
            UpdateSource.id == source_id,
            UpdateSource.space_id == membership.space_id,
            _visible(membership),
        )
    )
    if source is None:
        raise HTTPException(404, "Fichier introuvable.")
    return source


@router.get("/update-sources/{source_id}/download")
def download_source(source_id: uuid.UUID, membership: WriterMembership, db: DbSession):
    source = _load_source(db, membership, source_id)
    data = get_storage(db).get(source.storage_key)
    if data is None:
        raise HTTPException(410, "Le contenu de ce fichier n'est plus disponible.")
    ascii_name = source.filename.encode("ascii", "ignore").decode().replace('"', "") or "fichier"
    return Response(
        content=data,
        media_type=source.content_type,
        headers={
            "Content-Disposition": (
                f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(source.filename)}"
            ),
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


@router.post("/update-sources/{source_id}/share", status_code=201)
def share_source(
    source_id: uuid.UUID, body: SourceShare, membership: WriterMembership, db: DbSession
) -> DocumentOut:
    """Copie, sur décision explicite, un fichier source dans le dossier partagé d'un projet."""
    source = _load_source(db, membership, source_id)
    project = db.scalar(
        select(Project).where(
            Project.id == body.project_id, Project.space_id == membership.space_id
        )
    )
    if project is None:
        raise HTTPException(404, "Projet introuvable.")
    storage = get_storage(db)
    data = storage.get(source.storage_key)
    if data is None:
        raise HTTPException(410, "Le contenu de ce fichier n'est plus disponible.")
    document = Document(
        space_id=project.space_id,
        project_id=project.id,
        filename=source.filename,
        content_type=source.content_type,
        size_bytes=source.size_bytes,
        sha256=source.sha256,
        storage_key=uuid.uuid4(),
        uploaded_by_id=membership.user_id,
    )
    storage.put(document.storage_key, data)
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
        after={
            "filename": source.filename,
            "size_bytes": source.size_bytes,
            "project_id": str(project.id),
            "from_update_source": str(source.id),
        },
    )
    db.commit()
    return _document_out(_get_document(db, project.space_id, document.id), project.title)
