"""Champs personnalisés (étape F4, cahier V2 CHP01–CHP04).

Les propriétaires gèrent le catalogue : libellé, identifiant technique stable, type,
description, cible (projet ou tâche), portée (tous les projets ou un seul), choix, valeur
requise, bornes et formule. Les personnes qui peuvent modifier un projet remplissent les
valeurs et masquent, dans ce projet, les champs qui ne le concernent pas.

Rien n'est effacé en silence : renommer garde l'identifiant et les valeurs, une option retirée
reste lisible, un champ est archivé (jamais supprimé), et un changement de type est refusé tant
qu'une valeur existante ne peut pas être convertie (aperçu disponible avant).
"""

import re
import secrets
import unicodedata
import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from pilot_api.access import visible_project_ids
from pilot_api.audit import record
from pilot_api.custom_field_rules import (
    FORMULA_OPS,
    NUMERIC,
    InvalidValue,
    clean_value,
    compute,
    convert,
    display,
)
from pilot_api.deps import CurrentMembership, DbSession, OwnerMembership
from pilot_api.models import (
    CustomField,
    CustomFieldTarget,
    CustomFieldType,
    CustomFieldValue,
    Membership,
    MembershipStatus,
    Project,
    Task,
    utcnow,
)
from pilot_api.routers.projects import CONFLICT, load_project, load_task

router = APIRouter(prefix="/api/spaces/{space_id}", tags=["champs personnalisés"])

MAX_FIELDS = 100
MAX_OPTIONS = 50
T = CustomFieldType

Label = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Key = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{1,59}$")]
Description = Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)]


class Formula(BaseModel):
    op: Literal["difference", "sum", "ratio"]
    a: uuid.UUID
    b: uuid.UUID


class FieldConfig(BaseModel):
    max_length: Annotated[int, Field(ge=1, le=5000)] | None = None
    min: float | None = None
    max: float | None = None
    unit: Annotated[str, StringConstraints(strip_whitespace=True, max_length=20)] | None = None
    currency: Annotated[str, StringConstraints(strip_whitespace=True, max_length=10)] | None = None
    formula: Formula | None = None


class OptionIn(BaseModel):
    # Sans identifiant : nouvelle option. Avec : renommer ou (dés)activer l'option existante.
    id: str | None = None
    label: Label
    active: bool = True


class FieldCreate(BaseModel):
    label: Label
    target: CustomFieldTarget
    type: CustomFieldType
    key: Key | None = None
    description: Description | None = None
    required: bool = False
    project_id: uuid.UUID | None = None
    options: Annotated[list[Label], Field(max_length=MAX_OPTIONS)] = []
    config: FieldConfig = FieldConfig()


class FieldUpdate(BaseModel):
    version: int
    label: Label | None = None
    description: Description | None = None
    required: bool | None = None
    options: Annotated[list[OptionIn], Field(max_length=MAX_OPTIONS)] | None = None
    config: FieldConfig | None = None
    type: CustomFieldType | None = None


class FieldOrder(BaseModel):
    ids: Annotated[list[uuid.UUID], Field(max_length=MAX_FIELDS)]


class OptionOut(BaseModel):
    id: str
    label: str
    active: bool


class FieldOut(BaseModel):
    id: uuid.UUID
    key: str
    label: str
    description: str | None
    target: CustomFieldTarget
    type: CustomFieldType
    required: bool
    project_id: uuid.UUID | None
    options: list[OptionOut]
    config: dict[str, Any]
    position: int
    archived: bool
    version: int
    values_count: int = 0


class TypePreview(BaseModel):
    total: int
    convertible: int
    blocked: int
    examples: list[dict[str, str]]


class ProjectFieldsOut(BaseModel):
    fields: list[FieldOut]
    hidden_ids: list[uuid.UUID]
    values: dict[str, Any]
    task_values: dict[str, dict[str, Any]]


class ValuesIn(BaseModel):
    # Identifiant du champ → valeur (null pour vider).
    values: Annotated[dict[uuid.UUID, Any], Field(max_length=MAX_FIELDS)]


class HiddenIn(BaseModel):
    field_ids: Annotated[list[uuid.UUID], Field(max_length=MAX_FIELDS)]


# ---------- Outils ----------


def field_out(field: CustomField, values_count: int = 0) -> FieldOut:
    return FieldOut(
        id=field.id,
        key=field.key,
        label=field.label,
        description=field.description,
        target=field.target,
        type=field.type,
        required=field.required,
        project_id=field.project_id,
        options=[OptionOut(**o) for o in field.options or []],
        config=field.config or {},
        position=field.position,
        archived=field.archived_at is not None,
        version=field.version,
        values_count=values_count,
    )


def _slug(text: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "_", ascii_text.lower()).strip("_")[:50]
    if not slug or not slug[0].isalpha():
        slug = f"champ_{slug}".strip("_")
    return slug if len(slug) >= 2 else "champ"


def _unique_key(db: Session, space_id: uuid.UUID, wanted: str) -> str:
    taken = set(db.scalars(select(CustomField.key).where(CustomField.space_id == space_id)))
    key, n = wanted, 2
    while key in taken:
        key = f"{wanted[:55]}_{n}"
        n += 1
    return key


def _new_option_id() -> str:
    return f"opt_{secrets.token_hex(4)}"


def member_ids(db: Session, space_id: uuid.UUID) -> set[uuid.UUID]:
    return set(
        db.scalars(
            select(Membership.id).where(
                Membership.space_id == space_id, Membership.status == MembershipStatus.ACTIVE
            )
        )
    )


def people_names(db: Session, space_id: uuid.UUID) -> dict[str, str]:
    rows = db.scalars(
        select(Membership)
        .options(selectinload(Membership.user))
        .where(Membership.space_id == space_id)
    )
    return {str(m.id): m.user.display_name if m.user else m.email for m in rows}


def _space_fields(db: Session, space_id: uuid.UUID) -> list[CustomField]:
    return list(
        db.scalars(
            select(CustomField)
            .where(CustomField.space_id == space_id)
            .order_by(CustomField.position, CustomField.created_at)
        )
    )


def applicable_fields(
    db: Session, project: Project, target: CustomFieldTarget | None = None
) -> list[CustomField]:
    """Champs du catalogue qui concernent ce projet (y compris archivés et masqués)."""
    return [
        f
        for f in _space_fields(db, project.space_id)
        if f.project_id in (None, project.id) and (target is None or f.target == target)
    ]


def _check_config(
    db: Session, space_id: uuid.UUID, field: CustomField, config: FieldConfig
) -> dict[str, Any]:
    data = config.model_dump(exclude_none=True, mode="json")
    if field.type == T.AMOUNT and not data.get("currency"):
        raise HTTPException(422, "Un montant exige sa devise (par exemple EUR ou XOF).")
    if field.type in NUMERIC and "min" in data and "max" in data and data["min"] > data["max"]:
        raise HTTPException(422, "Le minimum dépasse le maximum.")
    if field.type == T.COMPUTED:
        formula = data.get("formula")
        if not formula or formula["op"] not in FORMULA_OPS:
            raise HTTPException(422, "Un champ calculé exige sa formule (deux champs numériques).")
        for ref in (formula["a"], formula["b"]):
            other = db.get(CustomField, uuid.UUID(ref))
            if (
                other is None
                or other.space_id != space_id
                or other.type not in NUMERIC
                or other.target != field.target
                or other.project_id not in (None, field.project_id)
            ):
                raise HTTPException(
                    422, "La formule utilise uniquement des champs numériques de la même fiche."
                )
    elif "formula" in data:
        data.pop("formula")
    return data


def _load_field(db: Session, membership: Membership, field_id: uuid.UUID) -> CustomField:
    field = db.get(CustomField, field_id, with_for_update=True, populate_existing=True)
    if field is None or field.space_id != membership.space_id:
        raise HTTPException(404, "Champ introuvable.")
    return field


def _values_count(db: Session, field_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not field_ids:
        return {}
    rows = db.execute(
        select(CustomFieldValue.field_id, func.count())
        .where(CustomFieldValue.field_id.in_(field_ids))
        .group_by(CustomFieldValue.field_id)
    ).all()
    return dict(rows)


def _journal_field(
    db: Session, membership: Membership, action: str, field: CustomField, before=None, after=None
) -> None:
    record(
        db,
        action=action,
        actor_id=membership.user_id,
        space_id=membership.space_id,
        target_type="custom_field",
        target_id=field.id,
        before=before,
        after=after or {"key": field.key, "label": field.label},
    )


# ---------- Catalogue ----------


@router.get("/custom-fields")
def list_fields(membership: CurrentMembership, db: DbSession) -> list[FieldOut]:
    visible = visible_project_ids(db, membership)
    fields = [
        f
        for f in _space_fields(db, membership.space_id)
        if f.project_id is None or visible is None or f.project_id in visible
    ]
    counts = _values_count(db, [f.id for f in fields])
    return [field_out(f, counts.get(f.id, 0)) for f in fields]


@router.post("/custom-fields", status_code=201)
def create_field(body: FieldCreate, membership: OwnerMembership, db: DbSession) -> FieldOut:
    space_id = membership.space_id
    total = db.scalar(select(func.count(CustomField.id)).where(CustomField.space_id == space_id))
    if (total or 0) >= MAX_FIELDS:
        raise HTTPException(422, f"{MAX_FIELDS} champs au plus par espace.")
    if body.project_id is not None:
        load_project(db, membership, body.project_id)
    if body.type in (T.CHOICE, T.MULTI_CHOICE) and not body.options:
        raise HTTPException(422, "Un champ à choix exige au moins une option.")
    top = db.scalar(select(func.max(CustomField.position)).where(CustomField.space_id == space_id))
    field = CustomField(
        space_id=space_id,
        project_id=body.project_id,
        target=body.target,
        key=_unique_key(db, space_id, body.key or _slug(body.label)),
        label=body.label,
        description=body.description or None,
        type=body.type,
        required=body.required and body.type != T.COMPUTED,
        options=[
            {"id": _new_option_id(), "label": label, "active": True}
            for label in dict.fromkeys(body.options)
        ]
        if body.type in (T.CHOICE, T.MULTI_CHOICE)
        else [],
        position=(top or 0) + 1,
    )
    field.config = _check_config(db, space_id, field, body.config)
    db.add(field)
    db.flush()
    _journal_field(db, membership, "custom_field.created", field)
    db.commit()
    return field_out(field)


def _merge_options(field: CustomField, wanted: list[OptionIn]) -> list[dict[str, Any]]:
    """Renommer et (dés)activer gardent l'identifiant ; une option absente de la liste reste
    telle quelle (une option n'est jamais supprimée, seulement retirée des nouvelles saisies)."""
    current = {o["id"]: dict(o) for o in field.options or []}
    order: list[str] = []
    for item in wanted:
        if item.id is not None:
            if item.id not in current:
                raise HTTPException(422, "Option inconnue.")
            current[item.id].update(label=item.label, active=item.active)
            order.append(item.id)
        else:
            new_id = _new_option_id()
            current[new_id] = {"id": new_id, "label": item.label, "active": item.active}
            order.append(new_id)
    order += [i for i in current if i not in order]
    if len(order) > MAX_OPTIONS:
        raise HTTPException(422, f"{MAX_OPTIONS} options au plus.")
    return [current[i] for i in order]


def _conversion(
    db: Session, field: CustomField, new_type: CustomFieldType, config: dict[str, Any] | None
) -> tuple[list[tuple[CustomFieldValue, Any]], list[CustomFieldValue], CustomField]:
    people = people_names(db, field.space_id)
    future = CustomField(
        space_id=field.space_id,
        label=field.label,
        type=new_type,
        options=field.options,
        config=config if config is not None else field.config,
    )
    rows = list(db.scalars(select(CustomFieldValue).where(CustomFieldValue.field_id == field.id)))
    ok: list[tuple[CustomFieldValue, Any]] = []
    blocked: list[CustomFieldValue] = []
    for row in rows:
        if field.type == T.PERSON and new_type in (T.TEXT, T.LONG_TEXT):
            converted = (True, display(field, row.value, people))
        else:
            converted = convert(field, future, row.value)
        if converted[0]:
            ok.append((row, converted[1]))
        else:
            blocked.append(row)
    return ok, blocked, future


@router.get("/custom-fields/{field_id}/type-preview")
def preview_type(
    field_id: uuid.UUID, type: CustomFieldType, membership: OwnerMembership, db: DbSession
) -> TypePreview:
    field = _load_field(db, membership, field_id)
    if type == T.COMPUTED or field.type == T.COMPUTED:
        raise HTTPException(422, "Un champ calculé ne change pas de type ; créez-en un autre.")
    ok, blocked, future = _conversion(db, field, type, None)
    examples = [
        {"before": display(field, row.value), "after": display(future, value)}
        for row, value in ok[:3]
    ] + [{"before": display(field, row.value), "after": ""} for row in blocked[:3]]
    db.rollback()
    return TypePreview(
        total=len(ok) + len(blocked), convertible=len(ok), blocked=len(blocked), examples=examples
    )


@router.patch("/custom-fields/{field_id}")
def update_field(
    field_id: uuid.UUID, body: FieldUpdate, membership: OwnerMembership, db: DbSession
) -> FieldOut:
    field = _load_field(db, membership, field_id)
    if field.version != body.version:
        raise HTTPException(409, CONFLICT)
    before = {"label": field.label, "type": field.type.value, "required": field.required}
    sent = body.model_fields_set
    if body.label is not None:
        field.label = body.label
    if "description" in sent:
        field.description = body.description or None
    if body.required is not None:
        field.required = body.required and field.type != T.COMPUTED
    if body.options is not None:
        if field.type not in (T.CHOICE, T.MULTI_CHOICE):
            raise HTTPException(422, "Ce champ n'a pas de choix.")
        field.options = _merge_options(field, body.options)
        if not any(o.get("active", True) for o in field.options):
            raise HTTPException(422, "Gardez au moins une option active.")
    if body.type is not None and body.type != field.type:
        if T.COMPUTED in (body.type, field.type):
            raise HTTPException(422, "Un champ calculé ne change pas de type ; créez-en un autre.")
        ok, blocked, _future = _conversion(db, field, body.type, None)
        if blocked:
            raise HTTPException(
                422,
                f"{len(blocked)} valeur(s) ne peuvent pas être converties vers ce type. "
                "Corrigez-les d'abord, ou créez un nouveau champ : "
                "rien n'est effacé sans votre accord.",
            )
        if body.type in (T.CHOICE, T.MULTI_CHOICE) and not field.options:
            raise HTTPException(422, "Un champ à choix exige au moins une option.")
        field.type = body.type
        for row, value in ok:
            row.value = value
            row.updated_by_id = membership.user_id
            row.updated_at = utcnow()
    if body.config is not None or (body.type is not None and "config" not in sent):
        field.config = _check_config(
            db, field.space_id, field, body.config or FieldConfig(**(field.config or {}))
        )
    field.version += 1
    _journal_field(
        db,
        membership,
        "custom_field.updated",
        field,
        before=before,
        after={"label": field.label, "type": field.type.value, "required": field.required},
    )
    db.commit()
    return field_out(field, _values_count(db, [field.id]).get(field.id, 0))


@router.post("/custom-fields/{field_id}/archive")
def archive_field(field_id: uuid.UUID, membership: OwnerMembership, db: DbSession) -> FieldOut:
    field = _load_field(db, membership, field_id)
    used_by = [
        f.label
        for f in _space_fields(db, field.space_id)
        if f.type == T.COMPUTED
        and f.archived_at is None
        and str(field.id) in ((f.config or {}).get("formula") or {}).values()
    ]
    if used_by:
        raise HTTPException(422, f"Ce champ sert au calcul de : {', '.join(used_by)}.")
    if field.archived_at is None:
        field.archived_at = utcnow()
        field.version += 1
        _journal_field(db, membership, "custom_field.archived", field)
    db.commit()
    return field_out(field, _values_count(db, [field.id]).get(field.id, 0))


@router.post("/custom-fields/{field_id}/restore")
def restore_field(field_id: uuid.UUID, membership: OwnerMembership, db: DbSession) -> FieldOut:
    field = _load_field(db, membership, field_id)
    if field.archived_at is not None:
        field.archived_at = None
        field.version += 1
        _journal_field(db, membership, "custom_field.restored", field)
    db.commit()
    return field_out(field, _values_count(db, [field.id]).get(field.id, 0))


@router.put("/custom-fields/order")
def order_fields(body: FieldOrder, membership: OwnerMembership, db: DbSession) -> list[FieldOut]:
    fields = {f.id: f for f in _space_fields(db, membership.space_id)}
    if set(body.ids) - set(fields):
        raise HTTPException(422, "Champ inconnu.")
    for position, field_id in enumerate(body.ids, start=1):
        fields[field_id].position = position
    db.commit()
    return [field_out(f) for f in _space_fields(db, membership.space_id)]


# ---------- Valeurs ----------


def _values_by_entity(
    db: Session, project_ids: list[uuid.UUID], tasks: bool
) -> dict[uuid.UUID, dict[str, Any]]:
    if not project_ids:
        return {}
    query = select(CustomFieldValue).where(CustomFieldValue.project_id.in_(project_ids))
    query = query.where(
        CustomFieldValue.task_id.is_not(None) if tasks else CustomFieldValue.task_id.is_(None)
    )
    result: dict[uuid.UUID, dict[str, Any]] = {}
    for row in db.scalars(query):
        owner = row.task_id if tasks else row.project_id
        result.setdefault(owner, {})[str(row.field_id)] = row.value
    return result


def with_computed(fields: list[CustomField], values: dict[str, Any]) -> dict[str, Any]:
    full = dict(values)
    for f in fields:
        if f.type == T.COMPUTED and f.archived_at is None:
            result = compute(f, values)
            if result is not None:
                full[str(f.id)] = result
    return full


def project_fields_out(db: Session, project: Project) -> ProjectFieldsOut:
    fields = applicable_fields(db, project)
    project_values = _values_by_entity(db, [project.id], tasks=False).get(project.id, {})
    task_values = _values_by_entity(db, [project.id], tasks=True)
    task_fields = [f for f in fields if f.target == CustomFieldTarget.TASK]
    project_fields = [f for f in fields if f.target == CustomFieldTarget.PROJECT]
    counts = _values_count(db, [f.id for f in fields])
    return ProjectFieldsOut(
        fields=[field_out(f, counts.get(f.id, 0)) for f in fields],
        hidden_ids=[uuid.UUID(i) for i in project.hidden_field_ids or []],
        values=with_computed(project_fields, project_values),
        task_values={
            str(task_id): with_computed(task_fields, values)
            for task_id, values in task_values.items()
        },
    )


def write_values(
    db: Session,
    membership: Membership,
    project: Project,
    task: Task | None,
    wanted: dict[uuid.UUID, Any],
) -> dict[str, Any]:
    """Contrôle puis enregistre des valeurs ; renvoie le journal {clé: [avant, après]}."""
    target = CustomFieldTarget.TASK if task else CustomFieldTarget.PROJECT
    fields = {f.id: f for f in applicable_fields(db, project, target)}
    query = select(CustomFieldValue).where(
        CustomFieldValue.project_id == project.id,
        CustomFieldValue.task_id == task.id if task else CustomFieldValue.task_id.is_(None),
    )
    existing = {row.field_id: row for row in db.scalars(query.with_for_update())}
    members = member_ids(db, project.space_id)
    people = people_names(db, project.space_id)
    changes: dict[str, Any] = {}
    for field_id, raw in wanted.items():
        field = fields.get(field_id)
        if field is None:
            raise HTTPException(422, "Ce champ ne concerne pas cette fiche.")
        if field.archived_at is not None:
            raise HTTPException(422, f"« {field.label} » est archivé : il ne se modifie plus.")
        row = existing.get(field_id)
        previous = row.value if row else None
        try:
            value = clean_value(field, raw, members, previous)
        except InvalidValue as exc:
            raise HTTPException(422, str(exc)) from None
        if value == previous:
            continue
        changes[field.key] = [display(field, previous, people), display(field, value, people)]
        if value is None:
            db.delete(row)
        elif row is None:
            db.add(
                CustomFieldValue(
                    space_id=project.space_id,
                    field_id=field.id,
                    project_id=project.id,
                    task_id=task.id if task else None,
                    value=value,
                    updated_by_id=membership.user_id,
                )
            )
        else:
            row.value = value
            row.updated_by_id = membership.user_id
            row.updated_at = utcnow()
    if changes:
        record(
            db,
            action="task.custom_values" if task else "project.custom_values",
            actor_id=membership.user_id,
            space_id=project.space_id,
            target_type="task" if task else "project",
            target_id=task.id if task else project.id,
            before={k: v[0] for k, v in changes.items()},
            after={k: v[1] for k, v in changes.items()},
        )
        project.updated_at = utcnow()
    return changes


@router.get("/projects/{project_id}/custom-fields")
def get_project_fields(
    project_id: uuid.UUID, membership: CurrentMembership, db: DbSession
) -> ProjectFieldsOut:
    project = load_project(db, membership, project_id)
    return project_fields_out(db, project)


@router.put("/projects/{project_id}/custom-values")
def set_project_values(
    project_id: uuid.UUID, body: ValuesIn, membership: CurrentMembership, db: DbSession
) -> ProjectFieldsOut:
    project = load_project(db, membership, project_id, write=True)
    write_values(db, membership, project, None, body.values)
    db.commit()
    return project_fields_out(db, project)


@router.put("/tasks/{task_id}/custom-values")
def set_task_values(
    task_id: uuid.UUID, body: ValuesIn, membership: CurrentMembership, db: DbSession
) -> ProjectFieldsOut:
    task = load_task(db, membership, task_id, write=True)
    project = load_project(db, membership, task.project_id)
    write_values(db, membership, project, task, body.values)
    db.commit()
    return project_fields_out(db, project)


@router.put("/projects/{project_id}/custom-fields/hidden")
def set_hidden_fields(
    project_id: uuid.UUID, body: HiddenIn, membership: CurrentMembership, db: DbSession
) -> ProjectFieldsOut:
    project = load_project(db, membership, project_id, write=True)
    known = {f.id for f in applicable_fields(db, project)}
    if set(body.field_ids) - known:
        raise HTTPException(422, "Champ inconnu pour ce projet.")
    before = project.hidden_field_ids or []
    project.hidden_field_ids = [str(i) for i in dict.fromkeys(body.field_ids)]
    if sorted(before) != sorted(project.hidden_field_ids):
        record(
            db,
            action="project.custom_fields_hidden",
            actor_id=membership.user_id,
            space_id=project.space_id,
            target_type="project",
            target_id=project.id,
            before={"hidden": before},
            after={"hidden": project.hidden_field_ids},
        )
        project.updated_at = utcnow()
    db.commit()
    return project_fields_out(db, project)


@router.get("/custom-values")
def space_values(membership: CurrentMembership, db: DbSession) -> dict[str, dict[str, Any]]:
    """Valeurs des champs de projet pour les projets visibles (filtres de la liste)."""
    visible = visible_project_ids(db, membership)
    query = select(Project.id).where(Project.space_id == membership.space_id)
    if visible is not None:
        query = query.where(Project.id.in_(visible))
    project_ids = list(db.scalars(query))
    fields = [
        f for f in _space_fields(db, membership.space_id) if f.target == CustomFieldTarget.PROJECT
    ]
    values = _values_by_entity(db, project_ids, tasks=False)
    return {
        str(pid): with_computed([f for f in fields if f.project_id in (None, pid)], v)
        for pid, v in values.items()
    }
