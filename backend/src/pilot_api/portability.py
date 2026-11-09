"""Export complet d'un espace et réimport dans un nouvel espace (CDC §18, §19, EXP01).

L'export est une photographie : un ZIP qui contient `pilot-export.json` (structure, projets,
tâches, détails d'événement, catalogue des documents) et, sauf demande contraire, le contenu
des fichiers dans `fichiers/`, chacun vérifiable par son empreinte SHA-256.

Ne sont jamais exportés : mots de passe, sessions, jetons d'invitation, et les demandes de la
boîte de mise à jour (elles peuvent être privées à leur auteur).

L'import crée toujours un nouvel espace, dont la personne qui importe est propriétaire.
Les éléments de structure de même nom sont rapprochés (pas de doublon avec les types
proposés par défaut) ; réimporter le même fichier renvoie l'espace déjà créé.
"""

import hashlib
import io
import json
import unicodedata
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum as PyEnum
from typing import Any, get_args
from zoneinfo import available_timezones

from pydantic import HttpUrl, TypeAdapter, ValidationError
from sqlalchemy import Date, DateTime, Enum, select
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Session

from pilot_api.audit import record
from pilot_api.models import (
    DEFAULT_PROJECT_TYPES,
    Document,
    Entity,
    EventDetails,
    Membership,
    MembershipStatus,
    Portfolio,
    Program,
    Project,
    ProjectContributor,
    ProjectLink,
    ProjectStatus,
    ProjectType,
    Role,
    Space,
    Task,
    TaskComment,
    TaskDependency,
    User,
    utcnow,
)
from pilot_api.schemas import Color, DecisionOption
from pilot_api.storage import get_storage

FORMAT = "pilot-export"
FORMAT_VERSION = 1
DATA_NAME = "pilot-export.json"
FILES_DIR = "fichiers/"
MAX_ITEMS = 20_000  # garde-fou contre un fichier démesuré
MAX_UNZIPPED = 200 * 1024 * 1024

CATALOGS: dict[str, type] = {
    "portfolios": Portfolio,
    "entities": Entity,
    "programs": Program,
    "project_types": ProjectType,
}
# Colonnes propres à la base d'origine, jamais copiées telles quelles.
TECHNICAL = {"space_id", "version", "client_request_id", "created_by_id", "uploaded_by_id"}


class ImportError_(ValueError):
    """Fichier d'export invalide : le message est affiché à l'utilisateur."""


# ---------- Sérialisation ----------


def _json(value: Any) -> Any:
    if isinstance(value, PyEnum):
        return value.value
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


def _dump(obj: Any, exclude: set[str] = frozenset()) -> dict[str, Any]:
    return {
        c.key: _json(getattr(obj, c.key))
        for c in obj.__table__.columns
        if c.key not in exclude and c.key not in TECHNICAL
    }


def _load(model: type, data: dict[str, Any], exclude: set[str]) -> dict[str, Any]:
    """Convertit les valeurs lues dans le fichier vers les types des colonnes."""
    values: dict[str, Any] = {}
    for column in model.__table__.columns:
        key = column.key
        if key in exclude or key in TECHNICAL or key == "id" or key not in data:
            continue
        value = data[key]
        if value is not None:
            kind = column.type
            if isinstance(kind, Enum) and kind.enum_class is not None:
                value = kind.enum_class(value)
            elif isinstance(kind, DateTime):
                value = datetime.fromisoformat(value)
            elif isinstance(kind, Date):
                value = date.fromisoformat(value)
            elif isinstance(kind, UUID):
                value = uuid.UUID(str(value))
        values[key] = value
    return values


_URL = TypeAdapter(HttpUrl)
_COLORS = set(get_args(Color))


def _safe_options(value: Any) -> list[dict[str, Any]] | None:
    """Options de décision lues dans un fichier : seules les entrées valides sont gardées."""
    if not isinstance(value, list):
        return None
    options = []
    for item in value[:3]:
        try:
            options.append(DecisionOption.model_validate(item).model_dump())
        except ValidationError:
            continue
    return options or None


def _safe_url(value: Any) -> str | None:
    """Un export peut avoir été modifié : seul un vrai lien http(s) est repris."""
    if not value:
        return None
    try:
        return str(_URL.validate_python(value))[:500]
    except ValidationError:
        return None


def _fold(name: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", name.casefold()) if not unicodedata.combining(c)
    ).strip()


# ---------- Export ----------


def build_export(db: Session, space: Space, author: User, with_files: bool) -> tuple[bytes, dict]:
    """Renvoie le ZIP et un résumé (nombre d'éléments)."""
    sid = space.id
    data: dict[str, Any] = {
        "format": FORMAT,
        "format_version": FORMAT_VERSION,
        "export_id": str(uuid.uuid4()),
        "exported_at": utcnow().isoformat(),
        "exported_by": author.display_name,
        "files_included": with_files,
        "space": {"name": space.name, "timezone": space.timezone},
    }
    for key, model in CATALOGS.items():
        rows = db.scalars(select(model).where(model.space_id == sid)).all()
        data[key] = [_dump(r) for r in rows]

    members = db.scalars(select(Membership).where(Membership.space_id == sid)).all()
    users = {
        u.id: u
        for u in db.scalars(
            select(User).where(User.id.in_([m.user_id for m in members if m.user_id]))
        )
    }
    data["members"] = [
        {
            "id": str(m.id),
            "email": m.email,
            "name": users[m.user_id].display_name if m.user_id in users else None,
            "role": m.role.value,
            "status": m.status.value,
        }
        for m in members
    ]
    projects = db.scalars(select(Project).where(Project.space_id == sid)).all()
    data["projects"] = [_dump(p) for p in projects]
    project_ids = [p.id for p in projects]
    details = db.scalars(select(EventDetails).where(EventDetails.project_id.in_(project_ids))).all()
    data["event_details"] = [_dump(d) for d in details]
    data["tasks"] = [_dump(t) for t in db.scalars(select(Task).where(Task.space_id == sid)).all()]
    data["task_comments"] = [
        _dump(c, exclude={"author_id", "mentions"})
        for c in db.scalars(select(TaskComment).where(TaskComment.space_id == sid)).all()
    ]
    data["task_dependencies"] = [
        _dump(d)
        for d in db.scalars(select(TaskDependency).where(TaskDependency.space_id == sid)).all()
    ]
    data["contributors"] = [
        _dump(c)
        for c in db.scalars(
            select(ProjectContributor).where(ProjectContributor.project_id.in_(project_ids))
        ).all()
    ]
    data["project_links"] = [
        _dump(link)
        for link in db.scalars(select(ProjectLink).where(ProjectLink.space_id == sid)).all()
    ]

    documents = db.scalars(select(Document).where(Document.space_id == sid)).all()
    storage = get_storage(db)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        catalogue = []
        for doc in documents:
            entry = _dump(doc, exclude={"storage_key"})
            entry["file"] = None
            if with_files:
                content = storage.get(doc.storage_key)
                if content is not None:
                    entry["file"] = f"{FILES_DIR}{doc.id}"
                    archive.writestr(entry["file"], content)
            catalogue.append(entry)
        data["documents"] = catalogue
        data["not_included"] = [
            "Mots de passe, sessions et liens d'invitation",
            "Demandes de la boîte de mise à jour (elles peuvent être privées)",
            "Alertes et préférences d'alertes (recalculées)",
            "Abonnements aux tâches (propres à chaque compte)",
        ]
        archive.writestr(DATA_NAME, json.dumps(data, ensure_ascii=False, indent=2))
    summary = {
        "projects": len(projects),
        "tasks": len(data["tasks"]),
        "documents": len(documents),
        "files": sum(1 for d in data["documents"] if d["file"]),
    }
    return buffer.getvalue(), summary


# ---------- Import ----------


@dataclass
class ImportReport:
    space_id: uuid.UUID
    already_imported: bool = False
    counts: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def read_archive(raw: bytes) -> tuple[dict[str, Any], dict[str, bytes]]:
    """Lit un ZIP d'export (ou le seul fichier JSON) ; vérifie le format."""
    files: dict[str, bytes] = {}
    if raw[:2] == b"PK":
        try:
            archive = zipfile.ZipFile(io.BytesIO(raw))
        except zipfile.BadZipFile as exc:
            raise ImportError_("Archive ZIP illisible.") from exc
        with archive:
            infos = archive.infolist()
            if sum(i.file_size for i in infos) > MAX_UNZIPPED:
                raise ImportError_("Archive trop volumineuse une fois décompressée.")
            names = {i.filename for i in infos}
            if DATA_NAME not in names:
                raise ImportError_(f"Le fichier {DATA_NAME} manque dans l'archive.")
            text = archive.read(DATA_NAME)
            for info in infos:
                if info.filename.startswith(FILES_DIR) and not info.is_dir():
                    files[info.filename] = archive.read(info)
    else:
        text = raw
    try:
        data = json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ImportError_("Ce fichier n'est pas un export PILOT (JSON illisible).") from exc
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise ImportError_("Ce fichier n'est pas un export PILOT.")
    if data.get("format_version") != FORMAT_VERSION:
        raise ImportError_("Version d'export non prise en charge.")
    total = sum(len(v) for v in data.values() if isinstance(v, list))
    if total > MAX_ITEMS:
        raise ImportError_("Export trop volumineux pour être importé en une fois.")
    return data, files


def _general_project(db: Session, space: Space, user: User) -> uuid.UUID:
    """Projet qui accueille les tâches sans projet d'un ancien export."""
    portfolio_id = db.scalar(
        select(Portfolio.id)
        .where(Portfolio.space_id == space.id, Portfolio.archived_at.is_(None))
        .order_by(Portfolio.created_at)
        .limit(1)
    )
    if portfolio_id is None:
        portfolio = Portfolio(space_id=space.id, name="Suivi général", color="gray")
        db.add(portfolio)
        db.flush()
        portfolio_id = portfolio.id
    project = Project(
        space_id=space.id,
        portfolio_id=portfolio_id,
        title="Suivi général",
        status=ProjectStatus.IN_PROGRESS,
        created_by_id=user.id,
    )
    db.add(project)
    db.flush()
    return project.id


def import_space(
    db: Session, user: User, data: dict[str, Any], files: dict[str, bytes]
) -> ImportReport:
    try:
        export_id = uuid.UUID(str(data["export_id"]))
        source_space = data["space"]
    except (KeyError, ValueError, TypeError) as exc:
        raise ImportError_("Export incomplet : identifiant ou espace manquant.") from exc

    # Même fichier réimporté par la même personne : on renvoie l'espace déjà créé.
    existing = db.scalar(
        select(Space)
        .join(Membership, Membership.space_id == Space.id)
        .where(
            Space.imported_from == export_id,
            Membership.user_id == user.id,
            Membership.role == Role.OWNER,
        )
    )
    if existing is not None:
        return ImportReport(existing.id, already_imported=True)

    exported_on = str(data.get("exported_at", ""))[:10]
    name = f"{source_space.get('name', 'Espace')} (import {exported_on})".strip()[:120]
    timezone = source_space.get("timezone")
    if timezone not in available_timezones():
        timezone = "UTC"
    space = Space(name=name, timezone=timezone, imported_from=export_id)
    db.add(space)
    db.flush()
    me = Membership(
        space_id=space.id,
        user_id=user.id,
        email=user.email,
        role=Role.OWNER,
        status=MembershipStatus.ACTIVE,
        joined_at=utcnow(),
    )
    db.add(me)
    defaults = [ProjectType(space_id=space.id, name=n, kind=k) for n, k in DEFAULT_PROJECT_TYPES]
    db.add_all(defaults)
    db.flush()
    report = ImportReport(space.id)

    # Structure : rapprochement par nom (sans tenir compte des majuscules ni des accents).
    ids: dict[str, dict[str, uuid.UUID]] = {}
    for key, model in CATALOGS.items():
        ids[key] = {}
        known = {_fold(t.name): t.id for t in defaults} if model is ProjectType else {}
        created = 0
        for item in data.get(key, []):
            folded = _fold(str(item.get("name", "")))
            if not folded:
                continue
            if folded in known:
                ids[key][str(item["id"])] = known[folded]
                continue
            values = _load(model, item, set())
            if "color" in values and values["color"] not in _COLORS:
                values["color"] = "gray"
            if values.get("emoji"):
                values["emoji"] = str(values["emoji"])[:16]
            row = model(space_id=space.id, **values)
            db.add(row)
            db.flush()
            known[folded] = ids[key][str(item["id"])] = row.id
            created += 1
        report.counts[key] = created

    # Personnes : seule la personne qui importe a un compte dans le nouvel espace.
    # Les autres responsables deviennent des noms libres (« sans compte »), sans invitation.
    member_ids: dict[str, uuid.UUID] = {}
    member_names: dict[str, str] = {}
    for member in data.get("members", []):
        member_names[str(member["id"])] = member.get("name") or member.get("email") or "Membre"
        if str(member.get("email", "")).lower() == user.email.lower():
            member_ids[str(member["id"])] = me.id

    def person(member_id: Any, label: str | None) -> tuple[uuid.UUID | None, str | None]:
        if member_id is None:
            return None, label
        key = str(member_id)
        if key in member_ids:
            return member_ids[key], user.display_name
        return None, (label or member_names.get(key))

    project_ids: dict[str, uuid.UUID] = {}
    refs = {
        "portfolio_id": "portfolios",
        "entity_id": "entities",
        "project_type_id": "project_types",
    }
    fallback_portfolio: uuid.UUID | None = None
    for item in data.get("projects", []):
        values = _load(Project, item, set(refs) | {"owner_member_id", "owner_label"})
        for column, catalog in refs.items():
            source = item.get(column)
            values[column] = ids[catalog].get(str(source)) if source else None
        if values["portfolio_id"] is None:
            if fallback_portfolio is None:
                portfolio = Portfolio(space_id=space.id, name="Importés sans portefeuille")
                db.add(portfolio)
                db.flush()
                fallback_portfolio = portfolio.id
                report.warnings.append(
                    "Des projets sans portefeuille reconnu ont été rangés dans "
                    "« Importés sans portefeuille »."
                )
            values["portfolio_id"] = fallback_portfolio
        values["external_url"] = _safe_url(values.get("external_url"))
        values["decision_options"] = _safe_options(values.get("decision_options"))
        if values.get("situation_source") not in {"manual", "update", "import", None}:
            values["situation_source"] = None
        for column, size in (("situation_source_label", 255), ("situation_updated_by", 120)):
            if values.get(column):
                values[column] = str(values[column])[:size]
        values["owner_member_id"], values["owner_label"] = person(
            item.get("owner_member_id"), item.get("owner_label")
        )
        project = Project(space_id=space.id, created_by_id=user.id, **values)
        db.add(project)
        db.flush()
        project_ids[str(item["id"])] = project.id
    report.counts["projects"] = len(project_ids)

    for item in data.get("event_details", []):
        project_id = project_ids.get(str(item.get("project_id")))
        if project_id is None:
            continue
        values = _load(EventDetails, item, {"project_id", "program_id"})
        program = item.get("program_id")
        values["program_id"] = ids["programs"].get(str(program)) if program else None
        db.add(EventDetails(project_id=project_id, **values))

    task_ids: dict[str, Task] = {}
    parents: list[tuple[Task, str]] = []
    general_project: uuid.UUID | None = None
    for item in data.get("tasks", []):
        source_project = item.get("project_id")
        project_id = project_ids.get(str(source_project)) if source_project else None
        if source_project and project_id is None:
            continue  # tâche d'un projet absent de l'export
        if project_id is None:
            # Ancien export : les tâches sans projet sont rangées dans « Suivi général ».
            if general_project is None:
                general_project = _general_project(db, space, user)
                report.warnings.append(
                    "Les tâches sans projet ont été rangées dans le projet « Suivi général »."
                )
            project_id = general_project
        values = _load(
            Task, item, {"project_id", "assignee_member_id", "assignee_label", "parent_id"}
        )
        values["assignee_member_id"], values["assignee_label"] = person(
            item.get("assignee_member_id"), item.get("assignee_label")
        )
        task = Task(space_id=space.id, project_id=project_id, **values)
        db.add(task)
        task_ids[str(item.get("id"))] = task
        if item.get("parent_id"):
            parents.append((task, str(item["parent_id"])))
    db.flush()
    # Sous-tâches : reliées à leur tâche si elle fait partie de l'import, du même projet.
    for task, parent in parents:
        parent_task = task_ids.get(parent)
        if (
            parent_task is not None
            and parent_task.project_id == task.project_id
            and parent_task.parent_id is None
        ):
            task.parent_id = parent_task.id
    report.counts["tasks"] = len(task_ids)

    for item in data.get("task_comments", []):
        task = task_ids.get(str(item.get("task_id")))
        body = str(item.get("body") or "").strip()
        if task is None or not body:
            continue
        values = _load(TaskComment, item, {"task_id", "author_name", "body"})
        db.add(
            TaskComment(
                space_id=space.id,
                task_id=task.id,
                author_name=str(item.get("author_name") or "Membre")[:120],
                body=body[:2000],
                mentions=[],
                **{k: v for k, v in values.items() if k == "created_at"},
            )
        )
    pairs = set()
    for item in data.get("task_dependencies", []):
        task = task_ids.get(str(item.get("task_id")))
        other = task_ids.get(str(item.get("depends_on_id")))
        if task is None or other is None or task is other or (task.id, other.id) in pairs:
            continue
        if (other.id, task.id) in pairs:
            continue  # attente réciproque : écartée
        pairs.add((task.id, other.id))
        db.add(TaskDependency(space_id=space.id, task_id=task.id, depends_on_id=other.id))

    for item in data.get("contributors", []):
        project_id = project_ids.get(str(item.get("project_id")))
        if project_id is None:
            continue
        member_id, label = person(item.get("member_id"), item.get("label"))
        if member_id is None and not label:
            continue
        db.add(
            ProjectContributor(
                project_id=project_id,
                member_id=member_id,
                label=(label or "")[:120] or None,
                position=int(item.get("position") or 0),
            )
        )
    links = set()
    for item in data.get("project_links", []):
        a = project_ids.get(str(item.get("project_a_id")))
        b = project_ids.get(str(item.get("project_b_id")))
        if a is None or b is None or a == b:
            continue
        a, b = sorted([a, b], key=str)
        if (a, b) in links:
            continue
        links.add((a, b))
        note = item.get("note")
        db.add(
            ProjectLink(
                space_id=space.id,
                project_a_id=a,
                project_b_id=b,
                note=str(note)[:200] if note else None,
            )
        )

    # Pièces : restaurées seulement si le contenu est présent et conforme à son empreinte.
    storage = get_storage(db)
    restored, missing, corrupted = 0, [], []
    # Ancien identifiant -> nouvelle fiche, pour relier ensuite chaque version à la précédente.
    new_documents: dict[str, tuple[Document, str | None]] = {}
    for item in data.get("documents", []):
        project_id = project_ids.get(str(item.get("project_id")))
        if project_id is None:
            continue
        content = files.get(item.get("file") or "")
        filename = str(item.get("filename", "document"))
        if content is None:
            missing.append(filename)
            continue
        if hashlib.sha256(content).hexdigest() != item.get("sha256"):
            corrupted.append(filename)
            continue
        values = _load(
            Document, item, {"project_id", "storage_key", "size_bytes", "sha256", "previous_id"}
        )
        document = Document(
            space_id=space.id,
            project_id=project_id,
            storage_key=uuid.uuid4(),
            size_bytes=len(content),
            sha256=item["sha256"],
            uploaded_by_id=user.id,
            **values,
        )
        storage.put(document.storage_key, content)
        db.add(document)
        previous = item.get("previous_id")
        new_documents[str(item.get("id"))] = (document, str(previous) if previous else None)
        restored += 1
    db.flush()
    for document, previous in new_documents.values():
        if previous and previous in new_documents:
            document.previous_id = new_documents[previous][0].id
    report.counts["documents"] = restored
    if missing:
        report.warnings.append(
            f"{len(missing)} pièce(s) sans contenu dans l'export (catalogue seul), non "
            f"restaurée(s) : {', '.join(missing[:10])}{'…' if len(missing) > 10 else ''}."
        )
    if corrupted:
        report.warnings.append(
            f"{len(corrupted)} pièce(s) dont l'empreinte ne correspond pas, écartée(s) : "
            f"{', '.join(corrupted[:10])}."
        )
    others = [m for m in data.get("members", []) if str(m["id"]) not in member_ids]
    if others:
        report.warnings.append(
            f"{len(others)} membre(s) de l'espace d'origine ne sont pas invités : leurs noms sont "
            "gardés comme responsables « sans compte ». Invitez-les depuis Accès et membres."
        )

    record(
        db,
        action="space.imported",
        actor_id=user.id,
        space_id=space.id,
        target_type="space",
        target_id=space.id,
        after={"export_id": str(export_id), **report.counts},
    )
    return report
