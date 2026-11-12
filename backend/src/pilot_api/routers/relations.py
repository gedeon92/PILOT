"""Rencontres, relations et partenariats (étape F6, cahier V2 REL01–REL04).

- Une sollicitation est triée : accepter, déléguer, traiter par écrit, instruire ou refuser.
  PILOT ne touche à aucun calendrier externe.
- Un rendez-vous a son dossier (objectif, contexte, interlocuteurs, derniers échanges, options,
  risques, décision attendue, suite souhaitée), prêt au moins 48 h avant.
- Après la rencontre : compte rendu, responsable de la suite et action suivante datée. La
  séance seule ne clôture pas le dossier ; une rencontre passée sans suite est signalée.
- Une relation garde personne, organisation, type, dernier contact, potentiel, prochaine
  action et référence CRM (le CRM reste la référence du pipeline). Un partenariat ajoute
  proposition de valeur, modèle économique, risques, instruction juridique et financière,
  obligations et renouvellement. La signature reste réservée au signataire habilité.
- Un élément confidentiel n'est visible que des propriétaires, de son auteur et de ses
  responsables.
"""

import uuid
from datetime import date, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, StringConstraints
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from pilot_api.audit import record
from pilot_api.deps import CurrentMembership, DbSession
from pilot_api.models import (
    Encounter,
    EncounterTriage,
    Membership,
    Project,
    Relation,
    RelationKind,
    Role,
    utcnow,
)
from pilot_api.routers.projects import CONFLICT, _person, _resolve_person, load_project, today_in
from pilot_api.schemas import PersonRef

router = APIRouter(prefix="/api/spaces/{space_id}", tags=["relations"])

WRITERS = {Role.OWNER, Role.CONTRIBUTOR}
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Short = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]
Text = Annotated[str, StringConstraints(strip_whitespace=True, max_length=4000)]
Person = Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)]

PARTNERSHIP_KEYS = [
    "value_proposition",
    "economic_model",
    "risks",
    "legal_review",
    "financial_review",
    "effort",
    "our_obligations",
    "their_obligations",
    "renewal_date",
]
DOSSIER_KEYS = [
    "objective",
    "context",
    "people",
    "last_exchanges",
    "options",
    "risks",
    "expected_decision",
    "desired_follow_up",
]


class Partnership(BaseModel):
    value_proposition: Text | None = None
    economic_model: Text | None = None
    risks: Text | None = None
    legal_review: Text | None = None
    financial_review: Text | None = None
    effort: Text | None = None
    our_obligations: Text | None = None
    their_obligations: Text | None = None
    renewal_date: date | None = None


class Dossier(BaseModel):
    objective: Text | None = None
    context: Text | None = None
    people: Text | None = None
    last_exchanges: Text | None = None
    options: Text | None = None
    risks: Text | None = None
    expected_decision: Text | None = None
    desired_follow_up: Text | None = None


class _RelationFields(BaseModel):
    organization: Short | None = None
    kind: RelationKind | None = None
    potential: Literal["low", "medium", "high"] | None = None
    last_contact: date | None = None
    next_action: Text | None = None
    next_action_date: date | None = None
    owner_member_id: uuid.UUID | None = None
    owner_label: Person | None = None
    crm_ref: Short | None = None
    notes: Text | None = None
    partnership: Partnership | None = None
    private: bool | None = None


class RelationCreate(_RelationFields):
    name: Name


class RelationUpdate(_RelationFields):
    version: int
    name: Name | None = None
    archived: bool | None = None


class RelationOut(BaseModel):
    id: uuid.UUID
    name: str
    organization: str | None
    kind: RelationKind
    potential: str | None
    last_contact: date | None
    next_action: str | None
    next_action_date: date | None
    action_late: bool
    owner: PersonRef
    crm_ref: str | None
    notes: str | None
    partnership: dict[str, Any] | None
    private: bool
    archived: bool
    encounters: int
    can_write: bool
    version: int


class _EncounterFields(BaseModel):
    relation_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    objective: Text | None = None
    expected_decision: Text | None = None
    priority_account: bool | None = None
    urgent: bool | None = None
    is_trip: bool | None = None
    starts_on: date | None = None
    ends_on: date | None = None
    owner_member_id: uuid.UUID | None = None
    owner_label: Person | None = None
    private: bool | None = None


class EncounterCreate(_EncounterFields):
    title: Name


class EncounterUpdate(_EncounterFields):
    version: int
    title: Name | None = None
    triage: EncounterTriage | None = None
    triage_note: Text | None = None
    dossier: Dossier | None = None
    dossier_ready: bool | None = None
    report: Text | None = None
    follow_owner_member_id: uuid.UUID | None = None
    follow_owner_label: Person | None = None
    next_action: Text | None = None
    next_action_date: date | None = None


class EncounterClose(BaseModel):
    version: int
    # Sans compte rendu ni suite, la clôture exige un motif (abandon motivé, REL03).
    reason: Text | None = None


class EncounterOut(BaseModel):
    id: uuid.UUID
    title: str
    relation: dict[str, Any] | None
    project: dict[str, Any] | None
    objective: str | None
    expected_decision: str | None
    priority_account: bool
    urgent: bool
    triage: EncounterTriage
    triage_note: str | None
    is_trip: bool
    starts_on: date | None
    ends_on: date | None
    dossier: dict[str, Any] | None
    dossier_ready_at: datetime | None
    dossier_due: bool
    report: str | None
    report_at: datetime | None
    report_due_on: date | None
    follow_owner: PersonRef
    next_action: str | None
    next_action_date: date | None
    without_follow_up: bool
    closed_at: datetime | None
    close_reason: str | None
    owner: PersonRef
    private: bool
    can_write: bool
    version: int


# ---------- Droits ----------


def _ensure_member(membership: Membership) -> None:
    if membership.role == Role.GUEST:
        raise HTTPException(403, "Les rencontres et relations ne sont pas ouvertes aux invités.")


def _visible(model, membership: Membership):
    base = model.space_id == membership.space_id
    if membership.role == Role.OWNER:
        return base
    return base & or_(
        model.private.is_(False),
        model.created_by_id == membership.user_id,
        model.owner_member_id == membership.id,
    )


def _can_write(membership: Membership) -> bool:
    return membership.role in WRITERS


def _writer(membership: Membership) -> None:
    if not _can_write(membership):
        raise HTTPException(403, "Votre rôle permet de consulter, pas de modifier.")


# ---------- Relations ----------


def _relation_out(r: Relation, counts: dict, today: date, membership: Membership) -> RelationOut:
    return RelationOut(
        id=r.id,
        name=r.name,
        organization=r.organization,
        kind=r.kind,
        potential=r.potential,
        last_contact=r.last_contact,
        next_action=r.next_action,
        next_action_date=r.next_action_date,
        action_late=r.next_action_date is not None and r.next_action_date < today,
        owner=_person(r.owner_member, r.owner_label),
        crm_ref=r.crm_ref,
        notes=r.notes,
        partnership=r.partnership,
        private=r.private,
        archived=r.archived_at is not None,
        encounters=counts.get(r.id, 0),
        can_write=_can_write(membership),
        version=r.version,
    )


def _relations(db: Session, membership: Membership, ids=None) -> list[RelationOut]:
    query = (
        select(Relation)
        .options(selectinload(Relation.owner_member).selectinload(Membership.user))
        .where(_visible(Relation, membership))
        .order_by(Relation.name)
    )
    if ids is not None:
        query = query.where(Relation.id.in_(ids))
    relations = list(db.scalars(query))
    counts: dict[uuid.UUID, int] = {}
    for e in db.scalars(
        select(Encounter).where(
            _visible(Encounter, membership),
            Encounter.relation_id.in_([r.id for r in relations]),
        )
    ):
        counts[e.relation_id] = counts.get(e.relation_id, 0) + 1
    today = today_in(membership.space)
    return [_relation_out(r, counts, today, membership) for r in relations]


def _apply_relation(db: Session, membership: Membership, r: Relation, body: _RelationFields):
    sent = body.model_fields_set
    for name in (
        "organization",
        "potential",
        "last_contact",
        "next_action",
        "next_action_date",
        "crm_ref",
        "notes",
    ):
        if name in sent:
            value = getattr(body, name)
            setattr(r, name, value if value != "" else None)
    if body.kind is not None:
        r.kind = body.kind
    if body.private is not None:
        r.private = body.private
    if "partnership" in sent:
        data = (
            body.partnership.model_dump(mode="json", exclude_none=True) if body.partnership else {}
        )
        r.partnership = {k: v for k, v in data.items() if v != ""} or None
    if "owner_member_id" in sent or "owner_label" in sent:
        r.owner_member_id, r.owner_label = _resolve_person(
            db, membership.space_id, body.owner_member_id, body.owner_label
        )


def _journal(db, membership, kind: str, target, action: str, after=None):
    record(
        db,
        action=f"{kind}.{action}",
        actor_id=membership.user_id,
        space_id=membership.space_id,
        target_type=kind,
        target_id=target.id,
        after=after,
    )


@router.get("/relations")
def list_relations(membership: CurrentMembership, db: DbSession) -> list[RelationOut]:
    _ensure_member(membership)
    return _relations(db, membership)


@router.post("/relations", status_code=201)
def create_relation(
    body: RelationCreate, membership: CurrentMembership, db: DbSession
) -> RelationOut:
    _ensure_member(membership)
    _writer(membership)
    r = Relation(
        space_id=membership.space_id,
        name=body.name,
        kind=body.kind or RelationKind.OTHER,
        private=False,
        created_by_id=membership.user_id,
    )
    _apply_relation(db, membership, r, body)
    db.add(r)
    db.flush()
    _journal(db, membership, "relation", r, "created", {"name": r.name})
    db.commit()
    return _relations(db, membership, [r.id])[0]


def _load_relation(db: Session, membership: Membership, relation_id: uuid.UUID) -> Relation:
    r = db.scalar(
        select(Relation)
        .execution_options(populate_existing=True)
        .where(Relation.id == relation_id, _visible(Relation, membership))
        .with_for_update()
    )
    if r is None:
        raise HTTPException(404, "Relation introuvable.")
    return r


@router.patch("/relations/{relation_id}")
def update_relation(
    relation_id: uuid.UUID, body: RelationUpdate, membership: CurrentMembership, db: DbSession
) -> RelationOut:
    _ensure_member(membership)
    _writer(membership)
    r = _load_relation(db, membership, relation_id)
    if r.version != body.version:
        raise HTTPException(409, CONFLICT)
    if body.name is not None:
        r.name = body.name
    _apply_relation(db, membership, r, body)
    if body.archived is not None:
        r.archived_at = utcnow() if body.archived else None
    r.version += 1
    _journal(db, membership, "relation", r, "updated", {"name": r.name})
    db.commit()
    return _relations(db, membership, [r.id])[0]


# ---------- Rencontres ----------


def _report_due(e: Encounter) -> date | None:
    """Compte rendu attendu : sous 72 h après la fin d'un déplacement, sinon le jour même."""
    end = e.ends_on or e.starts_on
    if end is None:
        return None
    from datetime import timedelta

    return end + timedelta(days=3) if e.is_trip else end


def _encounter_out(
    e: Encounter, today: date, membership: Membership, projects: dict, relations: dict
) -> EncounterOut:
    from datetime import timedelta

    end = e.ends_on or e.starts_on
    passed = end is not None and end < today
    return EncounterOut(
        id=e.id,
        title=e.title,
        relation={"id": e.relation_id, "name": relations[e.relation_id]}
        if e.relation_id in relations
        else None,
        project={"id": e.project_id, "title": projects[e.project_id]}
        if e.project_id in projects
        else None,
        objective=e.objective,
        expected_decision=e.expected_decision,
        priority_account=e.priority_account,
        urgent=e.urgent,
        triage=e.triage,
        triage_note=e.triage_note,
        is_trip=e.is_trip,
        starts_on=e.starts_on,
        ends_on=e.ends_on,
        dossier=e.dossier,
        dossier_ready_at=e.dossier_ready_at,
        dossier_due=e.closed_at is None
        and e.dossier_ready_at is None
        and e.starts_on is not None
        and e.triage == EncounterTriage.ACCEPT
        and e.starts_on - timedelta(days=2) <= today <= e.starts_on,
        report=e.report,
        report_at=e.report_at,
        report_due_on=_report_due(e),
        follow_owner=_person(e.follow_owner_member, e.follow_owner_label),
        next_action=e.next_action,
        next_action_date=e.next_action_date,
        without_follow_up=e.closed_at is None
        and passed
        and e.triage == EncounterTriage.ACCEPT
        and not (e.report and e.next_action and e.next_action_date),
        closed_at=e.closed_at,
        close_reason=e.close_reason,
        owner=_person(e.owner_member, e.owner_label),
        private=e.private,
        can_write=_can_write(membership),
        version=e.version,
    )


def _encounters(db: Session, membership: Membership, ids=None) -> list[EncounterOut]:
    query = (
        select(Encounter)
        .options(
            selectinload(Encounter.owner_member).selectinload(Membership.user),
            selectinload(Encounter.follow_owner_member).selectinload(Membership.user),
        )
        .where(_visible(Encounter, membership))
        .order_by(Encounter.starts_on.desc().nulls_first(), Encounter.created_at.desc())
    )
    if ids is not None:
        query = query.where(Encounter.id.in_(ids))
    rows = list(db.scalars(query))
    from pilot_api.access import visible_project_ids

    visible = visible_project_ids(db, membership)
    projects = {
        pid: title
        for pid, title in db.execute(
            select(Project.id, Project.title).where(Project.space_id == membership.space_id)
        )
        if visible is None or pid in visible
    }
    relations = {
        rid: name
        for rid, name in db.execute(
            select(Relation.id, Relation.name).where(_visible(Relation, membership))
        )
    }
    today = today_in(membership.space)
    return [_encounter_out(e, today, membership, projects, relations) for e in rows]


def _apply_encounter(db: Session, membership: Membership, e: Encounter, body: _EncounterFields):
    sent = body.model_fields_set
    for name in ("objective", "expected_decision", "starts_on", "ends_on"):
        if name in sent:
            value = getattr(body, name)
            setattr(e, name, value if value != "" else None)
    for name in ("priority_account", "urgent", "is_trip", "private"):
        if getattr(body, name) is not None:
            setattr(e, name, getattr(body, name))
    if "relation_id" in sent:
        if body.relation_id is not None:
            _load_relation(db, membership, body.relation_id)
        e.relation_id = body.relation_id
    if "project_id" in sent:
        if body.project_id is not None:
            load_project(db, membership, body.project_id)
        e.project_id = body.project_id
    if "owner_member_id" in sent or "owner_label" in sent:
        e.owner_member_id, e.owner_label = _resolve_person(
            db, membership.space_id, body.owner_member_id, body.owner_label
        )
    if e.starts_on and e.ends_on and e.ends_on < e.starts_on:
        raise HTTPException(422, "La fin précède le début.")


@router.get("/encounters")
def list_encounters(membership: CurrentMembership, db: DbSession) -> list[EncounterOut]:
    _ensure_member(membership)
    return _encounters(db, membership)


@router.post("/encounters", status_code=201)
def create_encounter(
    body: EncounterCreate, membership: CurrentMembership, db: DbSession
) -> EncounterOut:
    _ensure_member(membership)
    _writer(membership)
    e = Encounter(
        space_id=membership.space_id,
        title=body.title,
        triage=EncounterTriage.TO_TRIAGE,
        priority_account=False,
        urgent=False,
        is_trip=False,
        private=False,
        created_by_id=membership.user_id,
    )
    _apply_encounter(db, membership, e, body)
    db.add(e)
    db.flush()
    _journal(db, membership, "encounter", e, "created", {"title": e.title})
    db.commit()
    return _encounters(db, membership, [e.id])[0]


def _load_encounter(db: Session, membership: Membership, encounter_id: uuid.UUID) -> Encounter:
    e = db.scalar(
        select(Encounter)
        .execution_options(populate_existing=True)
        .where(Encounter.id == encounter_id, _visible(Encounter, membership))
        .with_for_update()
    )
    if e is None:
        raise HTTPException(404, "Rencontre introuvable.")
    return e


@router.patch("/encounters/{encounter_id}")
def update_encounter(
    encounter_id: uuid.UUID, body: EncounterUpdate, membership: CurrentMembership, db: DbSession
) -> EncounterOut:
    _ensure_member(membership)
    _writer(membership)
    e = _load_encounter(db, membership, encounter_id)
    if e.version != body.version:
        raise HTTPException(409, CONFLICT)
    sent = body.model_fields_set
    if body.title is not None:
        e.title = body.title
    _apply_encounter(db, membership, e, body)
    journal: dict[str, Any] = {"title": e.title}
    if body.triage is not None and body.triage != e.triage:
        if body.triage in (EncounterTriage.DELEGATE, EncounterTriage.REFUSE) and not (
            body.triage_note or e.triage_note
        ):
            raise HTTPException(422, "Déléguer ou refuser demande une note (à qui, ou pourquoi).")
        e.triage = body.triage
        journal["triage"] = body.triage.value
    if "triage_note" in sent:
        e.triage_note = body.triage_note or None
    if "dossier" in sent:
        data = body.dossier.model_dump(exclude_none=True) if body.dossier else {}
        e.dossier = {k: v for k, v in data.items() if v} or None
    if body.dossier_ready is not None:
        if body.dossier_ready and not (e.dossier or {}).get("objective"):
            raise HTTPException(422, "Le dossier doit au moins donner l'objectif en une phrase.")
        e.dossier_ready_at = (e.dossier_ready_at or utcnow()) if body.dossier_ready else None
        journal["dossier_ready"] = body.dossier_ready
    if "report" in sent:
        e.report = body.report or None
        e.report_at = utcnow() if e.report else None
    if "follow_owner_member_id" in sent or "follow_owner_label" in sent:
        e.follow_owner_member_id, e.follow_owner_label = _resolve_person(
            db, membership.space_id, body.follow_owner_member_id, body.follow_owner_label
        )
    for name in ("next_action", "next_action_date"):
        if name in sent:
            value = getattr(body, name)
            setattr(e, name, value if value != "" else None)
    if e.relation_id and e.report and ("report" in sent):
        relation = db.get(Relation, e.relation_id)
        day = e.ends_on or e.starts_on
        if relation is not None and day and (relation.last_contact or date.min) < day:
            relation.last_contact = day
    e.version += 1
    _journal(db, membership, "encounter", e, "updated", journal)
    db.commit()
    return _encounters(db, membership, [e.id])[0]


@router.post("/encounters/{encounter_id}/close")
def close_encounter(
    encounter_id: uuid.UUID, body: EncounterClose, membership: CurrentMembership, db: DbSession
) -> EncounterOut:
    _ensure_member(membership)
    _writer(membership)
    e = _load_encounter(db, membership, encounter_id)
    if e.version != body.version:
        raise HTTPException(409, CONFLICT)
    complete = (
        e.report
        and e.next_action
        and e.next_action_date
        and (e.follow_owner_member_id or e.follow_owner_label)
    )
    declined = e.triage in (
        EncounterTriage.DELEGATE,
        EncounterTriage.IN_WRITING,
        EncounterTriage.REFUSE,
    )
    if not complete and not declined and not (body.reason or "").strip():
        raise HTTPException(
            422,
            "Pour clôturer, il faut un compte rendu, un responsable et une action suivante "
            "datée — ou un motif d'abandon.",
        )
    e.closed_at = utcnow()
    e.close_reason = body.reason or None
    e.version += 1
    _journal(db, membership, "encounter", e, "closed", {"title": e.title, "reason": body.reason})
    db.commit()
    return _encounters(db, membership, [e.id])[0]


@router.post("/encounters/{encounter_id}/reopen")
def reopen_encounter(
    encounter_id: uuid.UUID, body: EncounterClose, membership: CurrentMembership, db: DbSession
) -> EncounterOut:
    _ensure_member(membership)
    _writer(membership)
    e = _load_encounter(db, membership, encounter_id)
    if e.version != body.version:
        raise HTTPException(409, CONFLICT)
    e.closed_at = None
    e.close_reason = None
    e.version += 1
    _journal(db, membership, "encounter", e, "reopened", {"title": e.title})
    db.commit()
    return _encounters(db, membership, [e.id])[0]
