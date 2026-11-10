"""Outils de l'assistant : lecture (avec les droits de la personne) et propositions.

Les outils de lecture renvoient des données ; les outils « proposer_… » n'appliquent rien :
ils vérifient les droits et les champs, puis enregistrent une proposition (`AiAction`) que la
personne applique ou refuse à l'écran. L'application elle-même passe par les routes
habituelles (voir apply.py), donc par exactement les mêmes contrôles.
"""

import json
import uuid
from datetime import date
from typing import Any

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from pilot_api.access import ensure_visible, ensure_writer
from pilot_api.models import (
    CLOSED_PROJECT_STATUSES,
    CLOSED_TASK_STATUSES,
    AiAction,
    AiActionState,
    Entity,
    Membership,
    MembershipStatus,
    Portfolio,
    Project,
    ProjectSection,
    ProjectType,
    Role,
    Task,
    TaskStatus,
)
from pilot_api.routers import projects as P
from pilot_api.routers.milestones import list_milestones
from pilot_api.routers.task_collab import task_detail
from pilot_api.schemas import (
    CommentCreate,
    ProjectCreate,
    ProjectStatusChange,
    ProjectUpdate,
    TaskCreate,
    TaskUpdate,
)
from pilot_api.updates.engine import STATUS_LABELS

MAX_ACTIONS_PER_TURN = 25


class ToolError(Exception):
    """Erreur renvoyée à l'assistant (il peut corriger et réessayer)."""


TASK_FIELDS = {
    "title": "Titre",
    "status": "Statut",
    "due_date": "Échéance",
    "due_certainty": "Certitude de l'échéance",
    "assignee_member_id": "Responsable",
    "assignee_label": "Responsable (nom libre)",
    "deliverable": "Livrable",
    "recurrence": "Répétition",
    "section_id": "Section",
    "priority": "Priorité",
    "start_date": "Date de début",
}
PROJECT_FIELDS = {
    "title": "Titre",
    "portfolio_id": "Portefeuille",
    "entity_id": "Filiale",
    "project_type_id": "Type de projet",
    "owner_member_id": "Responsable",
    "owner_label": "Responsable (nom libre)",
    "origin": "Origine",
    "situation": "Situation",
    "next_step": "Prochaine étape",
    "decision_needed": "Décision attendue",
    "decision_maker": "Décideur",
    "objective": "Objectif",
    "deliverables": "Livrables",
    "progress": "Avancement (%)",
    "risk_level": "Vigilance",
    "risk_note": "Note de vigilance",
    "start_date": "Date de début",
    "end_date": "Date de fin",
    "due_date": "Échéance",
    "date_certainty": "Certitude de la date",
    "country": "Pays",
    "city": "Ville",
    "external_url": "Lien externe",
}
TASK_STATUS_LABELS = P.TASK_STATUS_WORDS
RECURRENCE_LABELS = {
    "daily": "Chaque jour",
    "weekly": "Chaque semaine",
    "monthly": "Chaque mois",
    "yearly": "Chaque année",
}
RISK_LABELS = {"watch": "À surveiller", "high": "Élevée"}
PRIORITY_LABELS = {"low": "Basse", "normal": "Normale", "high": "Haute", "urgent": "Urgente"}

_NULLABLE_DATE = {
    "type": ["string", "null"],
    "description": "Date AAAA-MM-JJ, ou null pour effacer",
}
_TASK_PROPS: dict[str, Any] = {
    "title": {"type": "string", "description": "Titre de la tâche (200 caractères au plus)"},
    "status": {"type": "string", "enum": [s.value for s in TaskStatus]},
    "due_date": _NULLABLE_DATE,
    "assignee_member_id": {
        "type": ["string", "null"],
        "description": "Identifiant d'un membre (voir lister_referentiels)",
    },
    "assignee_label": {
        "type": ["string", "null"],
        "description": "Nom libre du responsable s'il n'a pas de compte",
    },
    "deliverable": {"type": ["string", "null"]},
    "recurrence": {
        "type": ["string", "null"],
        "enum": ["daily", "weekly", "monthly", "yearly", None],
        "description": "Répétition ; exige une échéance, impossible sur une sous-tâche",
    },
    "section_id": {
        "type": ["string", "null"],
        "description": "Section du projet (voir voir_projet) ; null = sans section",
    },
    "priority": {"type": ["string", "null"], "enum": ["low", "normal", "high", "urgent", None]},
    "start_date": _NULLABLE_DATE,
}
_PROJECT_PROPS: dict[str, Any] = {
    "title": {"type": "string"},
    "portfolio_id": {"type": "string"},
    "entity_id": {"type": ["string", "null"], "description": "Filiale"},
    "project_type_id": {"type": ["string", "null"]},
    "owner_member_id": {"type": ["string", "null"], "description": "Responsable (membre)"},
    "owner_label": {"type": ["string", "null"], "description": "Responsable (nom libre)"},
    "origin": {"type": ["string", "null"]},
    "situation": {"type": ["string", "null"]},
    "next_step": {"type": ["string", "null"]},
    "decision_needed": {"type": ["string", "null"]},
    "decision_maker": {"type": ["string", "null"]},
    "objective": {"type": ["string", "null"]},
    "deliverables": {"type": ["string", "null"]},
    "progress": {
        "type": ["integer", "null"],
        "description": "0 à 100, seulement si la personne l'indique (jamais estimé)",
    },
    "risk_level": {"type": ["string", "null"], "enum": ["watch", "high", None]},
    "risk_note": {"type": ["string", "null"]},
    "start_date": _NULLABLE_DATE,
    "end_date": _NULLABLE_DATE,
    "due_date": _NULLABLE_DATE,
    "country": {"type": ["string", "null"]},
    "city": {"type": ["string", "null"]},
}


def _obj(props: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": props,
        "required": required,
        "additionalProperties": False,
    }


TOOLS: list[dict[str, Any]] = [
    {
        "name": "rechercher_projets",
        "description": (
            "Liste les projets visibles par la personne (50 au plus), avec statut, responsable, "
            "échéance et tâches ouvertes ou en retard. Filtres facultatifs."
        ),
        "input_schema": _obj(
            {
                "texte": {"type": "string", "description": "Mot du titre"},
                "statut": {"type": "string", "enum": [s.value for s in STATUS_LABELS]},
                "portefeuille_id": {"type": "string"},
            },
            [],
        ),
    },
    {
        "name": "voir_projet",
        "description": "Fiche complète d'un projet : sections, tâches et jalons.",
        "input_schema": _obj({"projet_id": {"type": "string"}}, ["projet_id"]),
    },
    {
        "name": "voir_tache",
        "description": (
            "Détail d'une tâche : sous-tâches, commentaires, dépendances, fichiers joints."
        ),
        "input_schema": _obj({"tache_id": {"type": "string"}}, ["tache_id"]),
    },
    {
        "name": "lister_taches",
        "description": (
            "Tâches ouvertes de tout l'espace (200 au plus). Filtre : « mes_taches » (confiées "
            "à la personne), « en_retard », « sept_jours » (échéance dans les 7 jours) ou "
            "« toutes »."
        ),
        "input_schema": _obj(
            {
                "filtre": {
                    "type": "string",
                    "enum": ["mes_taches", "en_retard", "sept_jours", "toutes"],
                }
            },
            ["filtre"],
        ),
    },
    {
        "name": "lister_referentiels",
        "description": (
            "Membres de l'espace (identifiants pour désigner un responsable), portefeuilles, "
            "filiales et types de projet."
        ),
        "input_schema": _obj({}, []),
    },
    {
        "name": "proposer_creation_tache",
        "description": (
            "Propose de créer une tâche dans un projet (ou une sous-tâche si tache_parente_id "
            "est donné). Rien n'est créé avant la validation de la personne."
        ),
        "input_schema": _obj(
            {
                "projet_id": {"type": "string"},
                "tache_parente_id": {"type": ["string", "null"]},
                **_TASK_PROPS,
            },
            ["projet_id", "title"],
        ),
    },
    {
        "name": "proposer_modification_tache",
        "description": (
            "Propose de modifier une tâche. Ne mettre dans « modifications » que les champs à "
            "changer. Pour « supprimer » une tâche : statut « cancelled » (Annulée). Rien n'est "
            "modifié avant la validation de la personne."
        ),
        "input_schema": _obj(
            {
                "tache_id": {"type": "string"},
                "modifications": _obj(
                    {
                        **_TASK_PROPS,
                        "postpone_reason": {
                            "type": ["string", "null"],
                            "description": "Motif, si l'échéance est repoussée (à demander)",
                        },
                    },
                    [],
                ),
            },
            ["tache_id", "modifications"],
        ),
    },
    {
        "name": "proposer_creation_projet",
        "description": (
            "Propose de créer un projet (portefeuille obligatoire). Rien n'est créé avant la "
            "validation de la personne."
        ),
        "input_schema": _obj(_PROJECT_PROPS, ["title", "portfolio_id"]),
    },
    {
        "name": "proposer_modification_projet",
        "description": (
            "Propose de modifier les champs d'un projet (pas son statut : voir "
            "proposer_changement_statut_projet). Ne mettre que les champs à changer."
        ),
        "input_schema": _obj(
            {"projet_id": {"type": "string"}, "modifications": _obj(_PROJECT_PROPS, [])},
            ["projet_id", "modifications"],
        ),
    },
    {
        "name": "proposer_changement_statut_projet",
        "description": (
            "Propose de changer le statut d'un projet. « done » (Terminé) exige un bilan ; "
            "« cancelled » (Annulé, c'est ainsi qu'on supprime un projet) exige un motif et "
            "annule ses tâches ouvertes."
        ),
        "input_schema": _obj(
            {
                "projet_id": {"type": "string"},
                "statut": {"type": "string", "enum": [s.value for s in STATUS_LABELS]},
                "bilan": {"type": ["string", "null"]},
                "motif": {"type": ["string", "null"]},
            },
            ["projet_id", "statut"],
        ),
    },
    {
        "name": "proposer_commentaire",
        "description": "Propose d'ajouter un commentaire sur une tâche, au nom de la personne.",
        "input_schema": _obj(
            {"tache_id": {"type": "string"}, "texte": {"type": "string"}},
            ["tache_id", "texte"],
        ),
    },
]
READ_TOOLS = {
    "rechercher_projets",
    "voir_projet",
    "voir_tache",
    "lister_taches",
    "lister_referentiels",
}


# ---------- Outils de lecture ----------


def _clean(value: Any) -> Any:
    """Retire les valeurs vides : moins de texte envoyé, même information."""
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items() if v not in (None, [], {}, "")}
    if isinstance(value, list):
        return [_clean(v) for v in value]
    return value


def _dump(value: Any) -> str:
    return json.dumps(_clean(jsonable_encoder(value)), ensure_ascii=False)


def _uuid(value: Any, label: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except ValueError:
        raise ToolError(f"{label} invalide : {value!r}.") from None


def _person(ref: Any) -> str | None:
    return ref.name if ref else None


def _task_line(task: Any, project_titles: dict | None = None) -> dict[str, Any]:
    line = {
        "id": task.id,
        "titre": task.title,
        "statut": task.status,
        "responsable": _person(task.assignee),
        "echeance": task.due_date,
        "en_retard": task.late or None,
        "parent_id": task.parent_id,
        "repetition": task.recurrence,
        "section_id": task.section_id,
        "priorite": task.priority,
        "debut": task.start_date,
        "reports": task.postpone_count or None,
        "sous_taches": f"{task.subtasks_done}/{task.subtasks_total}"
        if task.subtasks_total
        else None,
        "version": task.version,
    }
    if project_titles is not None:
        line["projet"] = project_titles.get(task.project_id)
        line["projet_id"] = task.project_id
    return line


def _search_projects(db: Session, membership: Membership, args: dict) -> str:
    status = args.get("statut")
    portfolio = args.get("portefeuille_id")
    projects = P.list_projects(
        membership,
        db,
        status=P.ProjectStatus(status) if status else None,
        portfolio_id=_uuid(portfolio, "Portefeuille") if portfolio else None,
        q=args.get("texte") or None,
    )
    rows = [
        {
            "id": p.id,
            "titre": p.title,
            "statut": p.status,
            "portefeuille": p.portfolio.name,
            "filiale": p.entity.name if p.entity else None,
            "responsable": _person(p.owner),
            "echeance": p.due_date,
            "taches_ouvertes": p.open_tasks,
            "taches_en_retard": p.late_tasks,
            "prive": p.private or None,
        }
        for p in projects[:50]
    ]
    return _dump({"total": len(projects), "projets": rows})


def _project_for(db: Session, membership: Membership, raw_id: Any, write: bool = False) -> Project:
    project = P._load_project(db, membership.space_id, _uuid(raw_id, "Projet"))
    (ensure_writer if write else ensure_visible)(db, membership, project)
    return project


def _view_project(db: Session, membership: Membership, args: dict) -> str:
    project = _project_for(db, membership, args["projet_id"])
    out = P._project_with_counts(db, membership, project)
    tasks = P.list_tasks(project.id, membership, db)
    data = out.model_dump(exclude={"situation_source", "situation_source_label"})
    data["sections"] = [
        {"id": x.id, "titre": x.title, "archivee": x.archived_at is not None or None}
        for x in db.scalars(
            select(ProjectSection)
            .where(ProjectSection.project_id == project.id)
            .order_by(ProjectSection.position)
        )
    ]
    data["taches"] = [_task_line(t) for t in tasks[:200]]
    data["jalons"] = [
        {
            "titre": m.title,
            "date_engagee": m.due_date,
            "etat": m.state,
            "porteur": _person(m.owner),
            "critere": m.criterion,
            "reports": m.postpone_count or None,
            "a_risque": m.at_risk or None,
            "en_retard": m.late or None,
            "raisons": m.risk_reasons,
            "revue_de_cadrage_due": m.reframe_needed or None,
            "taches_liees": [t.title for t in m.tasks],
        }
        for m in list_milestones(project.id, membership, db)
    ]
    return _dump(data)


def _view_task(db: Session, membership: Membership, args: dict) -> str:
    detail = task_detail(_uuid(args["tache_id"], "Tâche"), membership, db)
    data = detail.model_dump(exclude={"followers", "following"})
    for doc in data.get("documents", []):
        for key in ("storage_key", "sha256"):
            doc.pop(key, None)
    return _dump(data)


def _list_tasks(db: Session, membership: Membership, args: dict) -> str:
    tasks = P.list_space_tasks(membership, db)
    today = P.today_in(membership.space)
    kind = args.get("filtre", "toutes")
    if kind == "mes_taches":
        tasks = [t for t in tasks if t.assignee.member_id == membership.id]
    elif kind == "en_retard":
        tasks = [t for t in tasks if t.late]
    elif kind == "sept_jours":
        tasks = [t for t in tasks if t.due_date and 0 <= (t.due_date - today).days <= 7]
    ids = {t.project_id for t in tasks if t.project_id}
    titles = dict(db.execute(select(Project.id, Project.title).where(Project.id.in_(ids))).all())
    return _dump({"total": len(tasks), "taches": [_task_line(t, titles) for t in tasks[:200]]})


def _references(db: Session, membership: Membership, _args: dict) -> str:
    sid = membership.space_id
    members = db.scalars(
        select(Membership).where(
            Membership.space_id == sid, Membership.status == MembershipStatus.ACTIVE
        )
    ).all()

    def catalog(model: type) -> list[dict]:
        rows = db.scalars(
            select(model).where(model.space_id == sid, model.archived_at.is_(None))
        ).all()
        return [{"id": r.id, "nom": r.name} for r in rows]

    return _dump(
        {
            "moi": {"membre_id": membership.id, "role": membership.role},
            "membres": [
                {
                    "membre_id": m.id,
                    "nom": (m.user.display_name if m.user else None) or m.email,
                    "role": m.role,
                }
                for m in members
            ],
            "portefeuilles": catalog(Portfolio),
            "filiales": catalog(Entity),
            "types_de_projet": catalog(ProjectType),
        }
    )


READERS = {
    "rechercher_projets": _search_projects,
    "voir_projet": _view_project,
    "voir_tache": _view_task,
    "lister_taches": _list_tasks,
    "lister_referentiels": _references,
}


# ---------- Propositions ----------


def _validation_text(error: ValidationError) -> str:
    parts = []
    for item in error.errors()[:5]:
        where = ".".join(str(p) for p in item.get("loc", ()))
        parts.append(f"{where} : {item.get('msg')}")
    return "Champs refusés — " + " ; ".join(parts)


def _member_name(db: Session, space_id: uuid.UUID, raw: Any) -> str:
    try:
        member = db.get(Membership, uuid.UUID(str(raw)))
    except ValueError:
        member = None
    if member is None or member.space_id != space_id:
        return str(raw)
    return (member.user.display_name if member.user else None) or member.email


def _catalog_name(db: Session, model: type, raw: Any) -> str:
    try:
        row = db.get(model, uuid.UUID(str(raw)))
    except ValueError:
        row = None
    return (getattr(row, "name", None) or getattr(row, "title", None)) if row else str(raw)


def display(db: Session, space_id: uuid.UUID, field: str, value: Any) -> str:
    """Valeur lisible pour l'écran de validation."""
    if value is None or value == "":
        return "—"
    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")
    text = value.value if hasattr(value, "value") else value
    if field in ("assignee_member_id", "owner_member_id"):
        return _member_name(db, space_id, text)
    if field == "portfolio_id":
        return _catalog_name(db, Portfolio, text)
    if field == "entity_id":
        return _catalog_name(db, Entity, text)
    if field == "project_type_id":
        return _catalog_name(db, ProjectType, text)
    if field in ("due_date", "start_date", "end_date") and isinstance(text, str):
        try:
            return date.fromisoformat(text).strftime("%d/%m/%Y")
        except ValueError:
            return text
    if field == "status":
        for labels in (TASK_STATUS_LABELS, STATUS_LABELS):
            for key, label in labels.items():
                if key.value == text:
                    return label
    if field == "recurrence":
        return RECURRENCE_LABELS.get(text, text)
    if field == "priority":
        return PRIORITY_LABELS.get(text, text)
    if field == "section_id":
        return _catalog_name(db, ProjectSection, text)
    if field == "risk_level":
        return RISK_LABELS.get(text, text)
    return str(text)


def _changes(
    db: Session, space_id: uuid.UUID, labels: dict, before: Any, fields: dict
) -> list[dict[str, str]]:
    rows = []
    # Ordre de l'écran : celui des libellés (le titre d'abord).
    order = list(labels)
    ordered = sorted(fields.items(), key=lambda kv: order.index(kv[0]) if kv[0] in order else 99)
    for name, value in ordered:
        old = getattr(before, name, None) if before is not None else None
        rows.append(
            {
                "field": labels.get(name, name),
                "before": display(db, space_id, name, old) if before is not None else "",
                "after": display(db, space_id, name, value),
            }
        )
    return rows


def _check(model: type, data: dict) -> Any:
    try:
        return model(**data)
    except ValidationError as error:
        raise ToolError(_validation_text(error)) from None


def _sent(body: Any, exclude: set[str]) -> dict[str, Any]:
    return body.model_dump(mode="json", include=body.model_fields_set - exclude)


def _http(error: HTTPException) -> ToolError:
    return ToolError(str(error.detail))


def _propose_task_create(db: Session, membership: Membership, args: dict) -> dict:
    project = _project_for(db, membership, args["projet_id"], write=True)
    if project.status in CLOSED_PROJECT_STATUSES:
        raise ToolError("Ce projet est clôturé : rouvrez-le avant d'y ajouter des tâches.")
    fields = {k: v for k, v in args.items() if k in TASK_FIELDS}
    body = _check(TaskCreate, fields)
    parent_raw = args.get("tache_parente_id")
    parent = None
    if parent_raw:
        parent = P._load_task(db, membership.space_id, _uuid(parent_raw, "Tâche parente"))
        if parent.project_id != project.id:
            raise ToolError("La tâche parente n'appartient pas à ce projet.")
        if parent.parent_id is not None:
            raise ToolError("Une sous-tâche ne peut pas avoir elle-même de sous-tâches.")
        if parent.status in CLOSED_TASK_STATUSES:
            raise ToolError("La tâche parente est clôturée.")
        if body.recurrence is not None:
            raise ToolError("Une sous-tâche ne peut pas se répéter.")
    sent = _sent(body, set())
    where = f"« {parent.title} »" if parent else f"le projet « {project.title} »"
    kind = "sous-tâche" if parent else "tâche"
    return {
        "kind": "create_task",
        "target_id": project.id,
        "base_version": None,
        "payload": {"parent_task_id": str(parent.id) if parent else None, "body": sent},
        "summary": f"Créer la {kind} « {body.title} » dans {where}",
        "changes": _changes(db, membership.space_id, TASK_FIELDS, None, sent),
    }


def _propose_task_update(db: Session, membership: Membership, args: dict) -> dict:
    task = P._load_task(db, membership.space_id, _uuid(args["tache_id"], "Tâche"))
    project = db.get(Project, task.project_id) if task.project_id else None
    if project is not None:
        ensure_writer(db, membership, project)
    elif membership.role in (Role.READER, Role.GUEST):
        raise ToolError("Votre rôle permet de consulter, pas de modifier.")
    mods = args.get("modifications") or {}
    fields = {k: v for k, v in mods.items() if k in TASK_FIELDS}
    reason = mods.get("postpone_reason") or None
    body = _check(TaskUpdate, {"version": task.version, **fields})
    sent = _sent(body, {"version"})
    if not sent:
        raise ToolError("Aucun champ à modifier.")
    if "recurrence" in sent and sent["recurrence"] and task.parent_id is not None:
        raise ToolError("Une sous-tâche ne peut pas se répéter.")
    sent = {k: v for k, v in sent.items() if _differs(getattr(task, k, None), v)}
    if not sent:
        raise ToolError("Ces valeurs sont déjà celles de la tâche : rien à changer.")
    changes = _changes(db, membership.space_id, TASK_FIELDS, task, sent)
    if reason and "due_date" in sent:
        sent["postpone_reason"] = str(reason)[:5000]
        changes.append({"field": "Motif du report", "before": "", "after": sent["postpone_reason"]})
    cancelling = sent.get("status") == TaskStatus.CANCELLED.value
    verb = "Annuler" if cancelling and len(sent) == 1 else "Modifier"
    return {
        "kind": "update_task",
        "target_id": task.id,
        "base_version": task.version,
        "payload": {"body": sent},
        "summary": f"{verb} la tâche « {task.title} »",
        "changes": changes,
    }


def _differs(old: Any, new: Any) -> bool:
    old = old.value if hasattr(old, "value") else old
    if isinstance(old, (date, uuid.UUID)):
        old = str(old)
    return old != new


def _propose_project_create(db: Session, membership: Membership, args: dict) -> dict:
    if membership.role not in (Role.OWNER, Role.CONTRIBUTOR):
        raise ToolError("Votre rôle ne permet pas de créer un projet.")
    fields = {k: v for k, v in args.items() if k in PROJECT_FIELDS}
    body = _check(ProjectCreate, fields)
    portfolio = db.get(Portfolio, body.portfolio_id)
    if portfolio is None or portfolio.space_id != membership.space_id:
        raise ToolError("Portefeuille introuvable : utilisez lister_referentiels.")
    sent = _sent(body, set())
    return {
        "kind": "create_project",
        "target_id": None,
        "base_version": None,
        "payload": {"body": sent},
        "summary": f"Créer le projet « {body.title} »",
        "changes": _changes(db, membership.space_id, PROJECT_FIELDS, None, sent),
    }


def _propose_project_update(db: Session, membership: Membership, args: dict) -> dict:
    project = _project_for(db, membership, args["projet_id"], write=True)
    fields = {k: v for k, v in (args.get("modifications") or {}).items() if k in PROJECT_FIELDS}
    body = _check(ProjectUpdate, {"version": project.version, **fields})
    sent = _sent(body, {"version"})
    sent = {k: v for k, v in sent.items() if _differs(getattr(project, k, None), v)}
    if not sent:
        raise ToolError("Aucun champ à changer (valeurs identiques ou absentes).")
    return {
        "kind": "update_project",
        "target_id": project.id,
        "base_version": project.version,
        "payload": {"body": sent},
        "summary": f"Modifier le projet « {project.title} »",
        "changes": _changes(db, membership.space_id, PROJECT_FIELDS, project, sent),
    }


def _propose_project_status(db: Session, membership: Membership, args: dict) -> dict:
    project = _project_for(db, membership, args["projet_id"], write=True)
    body = _check(
        ProjectStatusChange,
        {
            "version": project.version,
            "status": args.get("statut"),
            "outcome": args.get("bilan") or None,
            "reason": args.get("motif") or None,
        },
    )
    if body.status == project.status:
        raise ToolError("Le projet a déjà ce statut.")
    if body.status == P.ProjectStatus.DONE and not body.outcome:
        raise ToolError("Un bilan est nécessaire pour passer le projet à Terminé : demandez-le.")
    if body.status == P.ProjectStatus.CANCELLED and not body.reason:
        raise ToolError("Un motif est nécessaire pour annuler le projet : demandez-le.")
    changes = _changes(
        db, membership.space_id, {"status": "Statut"}, project, {"status": body.status}
    )
    if body.outcome:
        changes.append({"field": "Bilan", "before": "", "after": body.outcome})
    if body.reason:
        changes.append({"field": "Motif", "before": "", "after": body.reason})
    verb = "Annuler" if body.status == P.ProjectStatus.CANCELLED else "Changer le statut de"
    note = ""
    if body.status == P.ProjectStatus.CANCELLED:
        open_count = db.scalar(
            select(P.func.count(Task.id)).where(
                Task.project_id == project.id, Task.status.not_in(CLOSED_TASK_STATUSES)
            )
        )
        note = f" (ses {open_count} tâche(s) ouverte(s) seront annulées)" if open_count else ""
    return {
        "kind": "project_status",
        "target_id": project.id,
        "base_version": project.version,
        "payload": {"body": body.model_dump(mode="json", exclude={"version"}, exclude_none=True)},
        "summary": f"{verb} le projet « {project.title} »{note}",
        "changes": changes,
    }


def _propose_comment(db: Session, membership: Membership, args: dict) -> dict:
    task = P._load_task(db, membership.space_id, _uuid(args["tache_id"], "Tâche"))
    project = db.get(Project, task.project_id) if task.project_id else None
    if project is not None:
        ensure_writer(db, membership, project)
    body = _check(CommentCreate, {"body": args.get("texte", "")})
    return {
        "kind": "comment",
        "target_id": task.id,
        "base_version": None,
        "payload": {"body": {"body": body.body}},
        "summary": f"Commenter la tâche « {task.title} »",
        "changes": [{"field": "Commentaire", "before": "", "after": body.body}],
    }


PROPOSERS = {
    "proposer_creation_tache": _propose_task_create,
    "proposer_modification_tache": _propose_task_update,
    "proposer_creation_projet": _propose_project_create,
    "proposer_modification_projet": _propose_project_update,
    "proposer_changement_statut_projet": _propose_project_status,
    "proposer_commentaire": _propose_comment,
}


def run_tool(
    db: Session,
    membership: Membership,
    conversation_id: uuid.UUID,
    name: str,
    args: Any,
    created: list[AiAction],
) -> tuple[str, bool]:
    """Exécute un outil ; renvoie (texte pour l'assistant, est_une_erreur)."""
    if not isinstance(args, dict):
        return "Paramètres illisibles.", True
    try:
        if name in READERS:
            return READERS[name](db, membership, args), False
        if name in PROPOSERS:
            if len(created) >= MAX_ACTIONS_PER_TURN:
                raise ToolError(
                    f"{MAX_ACTIONS_PER_TURN} propositions au plus par message : demandez à la "
                    "personne de valider celles-ci d'abord."
                )
            fields = PROPOSERS[name](db, membership, args)
            action = AiAction(
                conversation_id=conversation_id,
                space_id=membership.space_id,
                user_id=membership.user_id,
                state=AiActionState.PENDING,
                **fields,
            )
            db.add(action)
            db.flush()
            created.append(action)
            return (
                f"Proposition enregistrée (n° {len(created)}) : {fields['summary']}. Elle "
                "attend la validation de la personne ; rien n'est encore appliqué.",
                False,
            )
        return f"Outil inconnu : {name}.", True
    except ToolError as error:
        return str(error), True
    except HTTPException as error:
        return str(_http(error)), True
    except KeyError as error:
        return f"Paramètre manquant : {error}.", True
