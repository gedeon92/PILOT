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
import re
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
    CustomField,
    CustomFieldTarget,
    CustomFieldType,
    CustomFieldValue,
    Decision,
    DecisionTask,
    Document,
    Entity,
    EventDetails,
    Meeting,
    Membership,
    MembershipStatus,
    Milestone,
    MilestoneTask,
    OccurrenceLink,
    Portfolio,
    Program,
    Project,
    ProjectContributor,
    ProjectLink,
    ProjectSection,
    ProjectStatus,
    ProjectTemplate,
    ProjectType,
    Role,
    Routine,
    RoutineOccurrence,
    Space,
    Task,
    TaskComment,
    TaskDependency,
    User,
    utcnow,
)
from pilot_api.routers.documents import clean_filename
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
    data["project_sections"] = [
        _dump(x)
        for x in db.scalars(select(ProjectSection).where(ProjectSection.space_id == sid)).all()
    ]
    data["tasks"] = [_dump(t) for t in db.scalars(select(Task).where(Task.space_id == sid)).all()]
    data["meetings"] = [
        _dump(x, exclude={"created_by_id"})
        for x in db.scalars(select(Meeting).where(Meeting.space_id == sid)).all()
    ]
    decisions = db.scalars(select(Decision).where(Decision.space_id == sid)).all()
    data["decisions"] = [_dump(x, exclude={"created_by_id"}) for x in decisions]
    data["decision_tasks"] = [
        {"decision_id": str(link.decision_id), "task_id": str(link.task_id)}
        for link in db.scalars(
            select(DecisionTask).where(DecisionTask.decision_id.in_([d.id for d in decisions]))
        ).all()
    ]
    milestones = db.scalars(select(Milestone).where(Milestone.space_id == sid)).all()
    data["milestones"] = [_dump(m) for m in milestones]
    data["milestone_tasks"] = [
        {"milestone_id": str(link.milestone_id), "task_id": str(link.task_id)}
        for link in db.scalars(
            select(MilestoneTask).where(MilestoneTask.milestone_id.in_([m.id for m in milestones]))
        ).all()
    ]
    # Champs personnalisés (étape F4) : définitions (clé technique, options aux identifiants
    # stables) et valeurs des projets et des tâches.
    data["custom_fields"] = [
        _dump(f) for f in db.scalars(select(CustomField).where(CustomField.space_id == sid)).all()
    ]
    data["custom_field_values"] = [
        _dump(v, exclude={"updated_by_id"})
        for v in db.scalars(select(CustomFieldValue).where(CustomFieldValue.space_id == sid)).all()
    ]
    # Routines (étape F5) : modèles, occurrences et liens vers les suites créées.
    routines = db.scalars(select(Routine).where(Routine.space_id == sid)).all()
    data["routines"] = [_dump(r) for r in routines]
    occurrences = db.scalars(
        select(RoutineOccurrence).where(RoutineOccurrence.space_id == sid)
    ).all()
    data["routine_occurrences"] = [_dump(o, exclude={"closed_by_id"}) for o in occurrences]
    data["occurrence_links"] = [
        {
            "occurrence_id": str(link.occurrence_id),
            "task_id": str(link.task_id) if link.task_id else None,
            "decision_id": str(link.decision_id) if link.decision_id else None,
        }
        for link in db.scalars(
            select(OccurrenceLink).where(
                OccurrenceLink.occurrence_id.in_([o.id for o in occurrences])
            )
        ).all()
    ]
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
    data["project_templates"] = [
        _dump(t)
        for t in db.scalars(select(ProjectTemplate).where(ProjectTemplate.space_id == sid)).all()
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
            "Accès par projet (propres à chaque compte : à redonner après l'import ; un projet "
            "privé le reste)",
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


def _template_milestones(raw: Any, person) -> list[dict[str, Any]]:
    """Jalons d'un modèle importé, nettoyés (étape F2)."""
    if not isinstance(raw, list):
        return []
    cleaned = []
    for entry in raw[:100]:
        if not isinstance(entry, dict) or not str(entry.get("title") or "").strip():
            continue
        offset = entry.get("offset_days")
        member, label = person(entry.get("owner_member_id"), entry.get("owner_label"))
        cleaned.append(
            {
                "title": str(entry["title"]).strip()[:200],
                "criterion": str(entry["criterion"])[:5000] if entry.get("criterion") else None,
                "offset_days": max(-3650, min(3650, offset))
                if isinstance(offset, int) and not isinstance(offset, bool)
                else None,
                "section": str(entry["section"])[:120] if entry.get("section") else None,
                "critical": bool(entry.get("critical")),
                "tasks": [str(r)[:20] for r in entry.get("tasks") or []][:100]
                if isinstance(entry.get("tasks"), list)
                else [],
                "owner_member_id": str(member) if member else None,
                "owner_label": (label or "")[:120] or None,
            }
        )
    return cleaned


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
    ) or db.scalar(
        # Un portefeuille archivé du même nom existe déjà : on le réutilise (nom unique).
        select(Portfolio.id).where(
            Portfolio.space_id == space.id, Portfolio.name == "Suivi général"
        )
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
        values = _load(
            Project, item, set(refs) | {"owner_member_id", "owner_label", "hidden_field_ids"}
        )
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

    # Sections (étape F1) : recréées avant les tâches, qui y sont ensuite rattachées.
    section_ids: dict[str, ProjectSection] = {}
    for item in data.get("project_sections", []):
        project_id = project_ids.get(str(item.get("project_id")))
        title = str(item.get("title") or "").strip()[:120]
        if project_id is None or not title:
            continue
        values = _load(ProjectSection, item, {"project_id", "title"})
        section = ProjectSection(space_id=space.id, project_id=project_id, title=title, **values)
        db.add(section)
        section_ids[str(item.get("id"))] = section
    db.flush()
    report.counts["project_sections"] = len(section_ids)

    task_ids: dict[str, Task] = {}
    parents: list[tuple[Task, str]] = []
    following: list[tuple[Task, str]] = []
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
            Task,
            item,
            {
                "project_id",
                "assignee_member_id",
                "assignee_label",
                "parent_id",
                "next_task_id",
                "section_id",
            },
        )
        section = section_ids.get(str(item.get("section_id"))) if item.get("section_id") else None
        values["section_id"] = (
            section.id if section is not None and section.project_id == project_id else None
        )
        values["assignee_member_id"], values["assignee_label"] = person(
            item.get("assignee_member_id"), item.get("assignee_label")
        )
        task = Task(space_id=space.id, project_id=project_id, **values)
        db.add(task)
        task_ids[str(item.get("id"))] = task
        if item.get("parent_id"):
            parents.append((task, str(item["parent_id"])))
        if item.get("next_task_id"):
            following.append((task, str(item["next_task_id"])))
    db.flush()
    # Tâche répétée : relie chaque tâche terminée à la suivante, si elle est dans l'import.
    for task, next_id in following:
        if next_id in task_ids:
            task.next_task_id = task_ids[next_id].id
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
    pairs: set[tuple[uuid.UUID, uuid.UUID]] = set()
    waits: dict[uuid.UUID, set[uuid.UUID]] = {}

    def reaches(start: uuid.UUID, goal: uuid.UUID) -> bool:
        """Vrai si `start` attend déjà (directement ou non) `goal` : la boucle est refusée."""
        seen, todo = set(), [start]
        while todo:
            current = todo.pop()
            if current == goal:
                return True
            if current not in seen:
                seen.add(current)
                todo.extend(waits.get(current, ()))
        return False

    for item in data.get("task_dependencies", []):
        task = task_ids.get(str(item.get("task_id")))
        other = task_ids.get(str(item.get("depends_on_id")))
        if task is None or other is None or task is other or (task.id, other.id) in pairs:
            continue
        if reaches(other.id, task.id):
            continue  # attente en boucle (fichier modifié) : écartée
        pairs.add((task.id, other.id))
        waits.setdefault(task.id, set()).add(other.id)
        db.add(TaskDependency(space_id=space.id, task_id=task.id, depends_on_id=other.id))

    # Jalons (étape F2) et tâches dont ils dépendent.
    milestone_ids: dict[str, Milestone] = {}
    for item in data.get("milestones", []):
        project_id = project_ids.get(str(item.get("project_id")))
        title = str(item.get("title") or "").strip()[:200]
        if project_id is None or not title or not item.get("due_date"):
            continue
        values = _load(
            Milestone,
            item,
            {"project_id", "title", "section_id", "owner_member_id", "owner_label"},
        )
        values["owner_member_id"], values["owner_label"] = person(
            item.get("owner_member_id"), item.get("owner_label")
        )
        section = section_ids.get(str(item.get("section_id"))) if item.get("section_id") else None
        milestone = Milestone(
            space_id=space.id,
            project_id=project_id,
            title=title,
            section_id=section.id if section and section.project_id == project_id else None,
            **values,
        )
        db.add(milestone)
        milestone_ids[str(item.get("id"))] = milestone
    db.flush()
    seen_links: set[tuple] = set()
    for item in data.get("milestone_tasks", []):
        milestone = milestone_ids.get(str(item.get("milestone_id")))
        task = task_ids.get(str(item.get("task_id")))
        if milestone is None or task is None or task.project_id != milestone.project_id:
            continue
        if (milestone.id, task.id) in seen_links:
            continue
        seen_links.add((milestone.id, task.id))
        db.add(MilestoneTask(milestone_id=milestone.id, task_id=task.id))
    report.counts["milestones"] = len(milestone_ids)

    # Réunions et décisions (étape F3). L'acceptation d'un membre n'est pas reprise : la
    # personne rapprochée dans le nouvel espace doit accepter à nouveau.
    meeting_ids: dict[str, Meeting] = {}
    for item in data.get("meetings", []):
        title = str(item.get("title") or "").strip()[:200]
        if not title or not item.get("ended_at"):
            continue
        values = _load(Meeting, item, {"project_id", "title"})
        source_project = item.get("project_id")
        meeting = Meeting(
            space_id=space.id,
            title=title,
            project_id=project_ids.get(str(source_project)) if source_project else None,
            created_by_id=user.id,
            **values,
        )
        db.add(meeting)
        meeting_ids[str(item.get("id"))] = meeting
    db.flush()
    decision_ids: dict[str, Decision] = {}
    for item in data.get("decisions", []):
        statement = str(item.get("statement") or "").strip()[:2000]
        if not statement:
            continue
        values = _load(
            Decision,
            item,
            {
                "project_id",
                "meeting_id",
                "statement",
                "decider_member_id",
                "decider_label",
                "executor_member_id",
                "executor_label",
                "executor_accepted_at",
            },
        )
        values["decider_member_id"], values["decider_label"] = person(
            item.get("decider_member_id"), item.get("decider_label")
        )
        values["executor_member_id"], values["executor_label"] = person(
            item.get("executor_member_id"), item.get("executor_label")
        )
        source_project = item.get("project_id")
        meeting = meeting_ids.get(str(item.get("meeting_id"))) if item.get("meeting_id") else None
        decision = Decision(
            space_id=space.id,
            statement=statement,
            project_id=project_ids.get(str(source_project)) if source_project else None,
            meeting_id=meeting.id if meeting else None,
            created_by_id=user.id,
            **values,
        )
        db.add(decision)
        decision_ids[str(item.get("id"))] = decision
    db.flush()
    seen_decision_links: set[tuple] = set()
    for item in data.get("decision_tasks", []):
        decision = decision_ids.get(str(item.get("decision_id")))
        task = task_ids.get(str(item.get("task_id")))
        if decision is None or task is None or (decision.id, task.id) in seen_decision_links:
            continue
        seen_decision_links.add((decision.id, task.id))
        db.add(DecisionTask(decision_id=decision.id, task_id=task.id))
    report.counts["meetings"] = len(meeting_ids)
    report.counts["decisions"] = len(decision_ids)

    _import_custom_fields(db, space, data, project_ids, task_ids, member_ids, report)
    _import_routines(db, space, data, task_ids, decision_ids, person, report)

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
            Document,
            item,
            {"project_id", "storage_key", "size_bytes", "sha256", "previous_id", "task_id"},
        )
        joined = task_ids.get(str(item.get("task_id"))) if item.get("task_id") else None
        values["task_id"] = joined.id if joined and joined.project_id == project_id else None
        # Nom et type venus du fichier : nettoyés comme lors d'un envoi normal.
        values["filename"] = clean_filename(values.get("filename"))
        values["content_type"] = str(values.get("content_type") or "application/octet-stream")[:120]
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
    templates = 0
    for item in data.get("project_templates", [])[:200]:
        name = str(item.get("name") or "").strip()[:120]
        tasks = item.get("tasks")
        if not name or not isinstance(tasks, list):
            continue
        cleaned = []
        for entry in tasks[:500]:
            if not isinstance(entry, dict) or not str(entry.get("title") or "").strip():
                continue
            member, label = person(entry.get("assignee_member_id"), entry.get("assignee_label"))
            offset = entry.get("offset_days")
            cleaned.append(
                {
                    "ref": str(entry.get("ref"))[:20],
                    "title": str(entry["title"]).strip()[:200],
                    "deliverable": str(entry["deliverable"])[:300]
                    if entry.get("deliverable")
                    else None,
                    "offset_days": max(-3650, min(3650, offset))
                    if isinstance(offset, int) and not isinstance(offset, bool)
                    else None,
                    "parent": str(entry["parent"])[:20] if entry.get("parent") else None,
                    "waits_for": [str(r)[:20] for r in entry.get("waits_for") or []][:20]
                    if isinstance(entry.get("waits_for"), list)
                    else [],
                    "recurrence": entry.get("recurrence")
                    if entry.get("recurrence") in {"daily", "weekly", "monthly", "yearly"}
                    else None,
                    "assignee_member_id": str(member) if member else None,
                    "assignee_label": (label or "")[:120] or None,
                    "section": str(entry["section"])[:120] if entry.get("section") else None,
                    "priority": entry.get("priority")
                    if entry.get("priority") in {"low", "normal", "high", "urgent"}
                    else None,
                }
            )
        description = item.get("description")
        db.add(
            ProjectTemplate(
                space_id=space.id,
                name=name,
                description=str(description)[:5000] if description else None,
                tasks=cleaned,
                sections=[
                    str(x).strip()[:120] for x in item.get("sections") or [] if str(x).strip()
                ][:50]
                if isinstance(item.get("sections"), list)
                else None,
                milestones=_template_milestones(item.get("milestones"), person) or None,
                created_by_id=user.id,
            )
        )
        templates += 1
    report.counts["project_templates"] = templates
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


def _import_custom_fields(
    db: Session,
    space: Space,
    data: dict[str, Any],
    project_ids: dict[str, uuid.UUID],
    task_ids: dict[str, Task],
    member_ids: dict[str, uuid.UUID],
    report: ImportReport,
) -> None:
    """Champs personnalisés (étape F4) : définitions, puis valeurs contrôlées comme une saisie.
    Une valeur refusée (personne sans compte dans le nouvel espace, par exemple) n'est pas
    reprise, et le rapport d'import le dit."""
    from pilot_api.custom_field_rules import InvalidValue, clean_value
    from pilot_api.routers.custom_fields import FieldConfig, _slug

    field_ids: dict[str, CustomField] = {}
    formulas: list[tuple[CustomField, dict[str, Any]]] = []
    taken: set[str] = set()
    for item in data.get("custom_fields", []):
        try:
            kind = CustomFieldType(item.get("type"))
            target = CustomFieldTarget(item.get("target"))
        except ValueError:
            continue
        label = str(item.get("label") or "").strip()[:120]
        if not label:
            continue
        source_project = item.get("project_id")
        project_id = project_ids.get(str(source_project)) if source_project else None
        if source_project and project_id is None:
            continue
        key = str(item.get("key") or "")
        if not re.fullmatch(r"[a-z][a-z0-9_]{1,59}", key) or key in taken:
            key = _slug(label)
            base, n = key, 2
            while key in taken:
                key, n = f"{base[:55]}_{n}", n + 1
        taken.add(key)
        options = [
            {
                "id": str(o["id"])[:40],
                "label": str(o["label"])[:120],
                "active": bool(o.get("active", True)),
            }
            for o in item.get("options") or []
            if isinstance(o, dict) and o.get("id") and str(o.get("label") or "").strip()
        ][:50]
        try:
            config = FieldConfig(**(item.get("config") or {})).model_dump(
                exclude_none=True, mode="json"
            )
        except ValueError:
            config = {}
        formula = config.pop("formula", None)
        archived = item.get("archived_at")
        field = CustomField(
            space_id=space.id,
            project_id=project_id,
            target=target,
            key=key,
            label=label,
            description=str(item["description"])[:1000] if item.get("description") else None,
            type=kind,
            options=options
            if kind in (CustomFieldType.CHOICE, CustomFieldType.MULTI_CHOICE)
            else [],
            config=config,
            required=bool(item.get("required")),
            position=int(item.get("position") or 0),
            archived_at=datetime.fromisoformat(archived) if archived else None,
        )
        db.add(field)
        field_ids[str(item.get("id"))] = field
        if formula:
            formulas.append((field, formula))
    db.flush()
    for field, formula in formulas:
        a, b = field_ids.get(formula.get("a")), field_ids.get(formula.get("b"))
        if a is not None and b is not None:
            field.config = {
                **field.config,
                "formula": {"op": formula.get("op"), "a": str(a.id), "b": str(b.id)},
            }
    report.counts["custom_fields"] = len(field_ids)

    members = set(member_ids.values())
    kept = refused = 0
    seen: set[tuple] = set()
    for item in data.get("custom_field_values", []):
        field = field_ids.get(str(item.get("field_id")))
        project_id = project_ids.get(str(item.get("project_id")))
        if field is None or project_id is None or field.type == CustomFieldType.COMPUTED:
            continue
        task = task_ids.get(str(item.get("task_id"))) if item.get("task_id") else None
        if item.get("task_id") and (task is None or task.project_id != project_id):
            continue
        if (task is None) != (field.target == CustomFieldTarget.PROJECT):
            continue
        if field.project_id not in (None, project_id):
            continue
        slot = (field.id, task.id if task else project_id)
        if slot in seen:
            continue
        value = item.get("value")
        if field.type == CustomFieldType.PERSON and value is not None:
            value = str(member_ids.get(str(value), value))
        try:
            value = clean_value(field, value, members, previous=value)
        except InvalidValue:
            refused += 1
            continue
        if value is None:
            continue
        seen.add(slot)
        db.add(
            CustomFieldValue(
                space_id=space.id,
                field_id=field.id,
                project_id=project_id,
                task_id=task.id if task else None,
                value=value,
            )
        )
        kept += 1
    report.counts["custom_field_values"] = kept
    if refused:
        report.warnings.append(
            f"{refused} valeur(s) de champs personnalisés n'ont pas été reprises "
            "(par exemple une personne sans compte dans ce nouvel espace)."
        )
    # Champs masqués par projet : identifiants convertis vers les nouveaux champs.
    by_new_project = {v: k for k, v in project_ids.items()}
    hidden_source = {str(p.get("id")): p.get("hidden_field_ids") for p in data.get("projects", [])}
    for project in db.scalars(select(Project).where(Project.id.in_(list(project_ids.values())))):
        raw = hidden_source.get(by_new_project.get(project.id, "")) or []
        if isinstance(raw, list):
            hidden = [str(field_ids[str(i)].id) for i in raw if str(i) in field_ids]
            project.hidden_field_ids = hidden or None


def _import_routines(
    db: Session,
    space: Space,
    data: dict[str, Any],
    task_ids: dict[str, Task],
    decision_ids: dict[str, Any],
    person: Any,
    report: ImportReport,
) -> None:
    """Routines (étape F5) : modèles, occurrences (mêmes dates, mêmes états) et liens."""
    from pilot_api.models import OccurrenceState, RoutineFrequency

    routine_ids: dict[str, Routine] = {}
    for item in data.get("routines", []):
        title = str(item.get("title") or "").strip()[:160]
        try:
            frequency = RoutineFrequency(item.get("frequency"))
        except ValueError:
            continue
        if not title or not item.get("start_date"):
            continue
        values = _load(
            Routine,
            item,
            {"title", "frequency", "owner_member_id", "owner_label", "weekdays", "month_days"},
        )
        values["owner_member_id"], values["owner_label"] = person(
            item.get("owner_member_id"), item.get("owner_label")
        )
        weekdays = [d for d in item.get("weekdays") or [] if isinstance(d, int) and 0 <= d <= 6]
        month_days = [
            d for d in item.get("month_days") or [] if isinstance(d, int) and 1 <= d <= 31
        ][:2]
        checklist = [
            {
                "id": str(c["id"])[:40],
                "label": str(c["label"])[:200],
                "mandatory": bool(c.get("mandatory")),
            }
            for c in item.get("checklist") or []
            if isinstance(c, dict) and c.get("id") and str(c.get("label") or "").strip()
        ][:20]
        values["checklist"] = checklist
        nth = item.get("nth_weekday")
        values["nth_weekday"] = (
            {"n": int(nth.get("n", 1)), "weekday": int(nth.get("weekday", 0))}
            if isinstance(nth, dict)
            else None
        )
        if values.get("time_of_day") and len(str(values["time_of_day"])) != 5:
            values["time_of_day"] = None
        routine = Routine(
            space_id=space.id,
            title=title,
            frequency=frequency,
            weekdays=weekdays,
            month_days=month_days,
            **values,
        )
        db.add(routine)
        routine_ids[str(item.get("id"))] = routine
    db.flush()
    report.counts["routines"] = len(routine_ids)

    occurrence_ids: dict[str, RoutineOccurrence] = {}
    seen: set[tuple] = set()
    for item in data.get("routine_occurrences", []):
        routine = routine_ids.get(str(item.get("routine_id")))
        if routine is None or not item.get("scheduled_date") or not item.get("due_date"):
            continue
        try:
            state = OccurrenceState(item.get("state"))
        except ValueError:
            continue
        values = _load(
            RoutineOccurrence,
            item,
            {"routine_id", "state", "owner_member_id", "owner_label", "checks", "closed_by_id"},
        )
        if (routine.id, values["scheduled_date"]) in seen:
            continue
        seen.add((routine.id, values["scheduled_date"]))
        values["owner_member_id"], values["owner_label"] = person(
            item.get("owner_member_id"), item.get("owner_label")
        )
        known = {c["id"] for c in routine.checklist}
        checks = item.get("checks") if isinstance(item.get("checks"), dict) else {}
        occurrence = RoutineOccurrence(
            space_id=space.id,
            routine_id=routine.id,
            state=state,
            checks={k: bool(v) for k, v in checks.items() if k in known},
            **values,
        )
        db.add(occurrence)
        occurrence_ids[str(item.get("id"))] = occurrence
    db.flush()
    report.counts["routine_occurrences"] = len(occurrence_ids)

    for item in data.get("occurrence_links", []):
        occurrence = occurrence_ids.get(str(item.get("occurrence_id")))
        task = task_ids.get(str(item.get("task_id"))) if item.get("task_id") else None
        decision = (
            decision_ids.get(str(item.get("decision_id"))) if item.get("decision_id") else None
        )
        if occurrence is None or (task is None and decision is None):
            continue
        db.add(
            OccurrenceLink(
                occurrence_id=occurrence.id,
                task_id=task.id if task else None,
                decision_id=decision.id if decision and not task else None,
            )
        )
