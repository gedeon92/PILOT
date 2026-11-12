"""Registre des décisions et réunions (étape F3, cahier V2 DEC01–DEC05).

- Une décision est consignée dès qu'elle est prise ; elle reste en brouillon tant qu'il
  manque un responsable nommé, une échéance ou un critère observable.
- Le responsable d'exécution (membre) accepte sa responsabilité ; un sujet sans porteur
  accepté est signalé à 30 jours.
- Les tâches d'exécution gardent le lien vers la décision.
- Clôture : Exécutée (avec preuve) ou Caduque (annulation formelle avec motif) ; rien ne se
  supprime.
- Une réunion suit son relevé : rédigé, validé, puis envoyé (déclaré) dans les 24 heures.
"""

import uuid

from fastapi import APIRouter, HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from pilot_api.access import ensure_visible, ensure_writer, visible_project_ids
from pilot_api.audit import record
from pilot_api.decision_rules import (
    accepted,
    is_late,
    mid_term,
    minutes_due,
    minutes_late,
    missing_fields,
    orphan_age,
)
from pilot_api.deps import CurrentMembership, DbSession
from pilot_api.models import (
    CLOSED_PROJECT_STATUSES,
    Decision,
    DecisionState,
    DecisionTask,
    Meeting,
    Membership,
    MinutesState,
    Project,
    Role,
    Task,
    utcnow,
)
from pilot_api.routers.projects import (
    CONFLICT,
    _person,
    _resolve_person,
    create_task_in,
    today_in,
)
from pilot_api.schemas import (
    DecisionClose,
    DecisionCreate,
    DecisionOut,
    DecisionTaskCreate,
    DecisionTaskRef,
    DecisionUpdate,
    DecisionVersion,
    MeetingCreate,
    MeetingOut,
    MeetingUpdate,
    RefOut,
    TaskCreate,
)

router = APIRouter(prefix="/api/spaces/{space_id}", tags=["décisions"])

MAX_LIST = 500
WRITERS = (Role.OWNER, Role.CONTRIBUTOR)


# ---------- Droits ----------


def _visible_filter(db: Session, membership: Membership):
    """Condition SQL : décisions que cette personne peut voir."""
    if membership.role == Role.OWNER:
        return Decision.space_id == membership.space_id
    projects = visible_project_ids(db, membership) or set()
    mine = or_(
        Decision.created_by_id == membership.user_id,
        Decision.decider_member_id == membership.id,
        Decision.executor_member_id == membership.id,
    )
    shared_scope = (
        Decision.project_id.in_(projects)
        if membership.role == Role.GUEST
        else or_(Decision.project_id.is_(None), Decision.project_id.in_(projects))
    )
    return (Decision.space_id == membership.space_id) & or_(
        mine, Decision.private.is_(False) & shared_scope
    )


def _can_write(db: Session, membership: Membership, decision: Decision) -> bool:
    if membership.role not in WRITERS:
        return False
    if decision.project_id is not None:
        project = db.get(Project, decision.project_id)
        try:
            ensure_writer(db, membership, project)
        except HTTPException:
            return False
    return True


def _query():
    return select(Decision).options(
        selectinload(Decision.decider_member).selectinload(Membership.user),
        selectinload(Decision.executor_member).selectinload(Membership.user),
    )


def _load(db: Session, membership: Membership, decision_id: uuid.UUID, write=True) -> Decision:
    decision = db.scalar(
        _query()
        .execution_options(populate_existing=True)
        .where(Decision.id == decision_id, _visible_filter(db, membership))
    )
    if decision is None:
        raise HTTPException(404, "Décision introuvable.")
    if write:
        if not _can_write(db, membership, decision):
            raise HTTPException(
                403, "Votre rôle permet de consulter cette décision, pas de la modifier."
            )
        db.refresh(decision, with_for_update={"of": Decision})
    return decision


def _check_links(db: Session, membership: Membership, project_id, meeting_id) -> None:
    if project_id is not None:
        project = db.get(Project, project_id)
        if project is None or project.space_id != membership.space_id:
            raise HTTPException(404, "Projet introuvable.")
        ensure_writer(db, membership, project)
    if meeting_id is not None:
        meeting = db.get(Meeting, meeting_id)
        if meeting is None or meeting.space_id != membership.space_id:
            raise HTTPException(404, "Réunion introuvable.")


# ---------- Sorties ----------


def decisions_out(
    db: Session, membership: Membership, decisions: list[Decision]
) -> list[DecisionOut]:
    today = today_in(membership.space)
    project_ids = {d.project_id for d in decisions if d.project_id}
    meeting_ids = {d.meeting_id for d in decisions if d.meeting_id}
    projects = dict(
        db.execute(select(Project.id, Project.title).where(Project.id.in_(project_ids))).all()
    )
    meetings = dict(
        db.execute(select(Meeting.id, Meeting.title).where(Meeting.id.in_(meeting_ids))).all()
    )
    links: dict[uuid.UUID, list[Task]] = {}
    if decisions:
        for decision_id, task in db.execute(
            select(DecisionTask.decision_id, Task)
            .join(Task, Task.id == DecisionTask.task_id)
            .where(DecisionTask.decision_id.in_([d.id for d in decisions]))
            .order_by(Task.created_at)
        ).all():
            links.setdefault(decision_id, []).append(task)
    out = []
    for d in decisions:
        open_ = d.state in (DecisionState.DRAFT, DecisionState.OPEN)
        out.append(
            DecisionOut(
                id=d.id,
                statement=d.statement,
                project=RefOut(id=d.project_id, name=projects[d.project_id])
                if d.project_id in projects
                else None,
                meeting=RefOut(id=d.meeting_id, name=meetings[d.meeting_id])
                if d.meeting_id in meetings
                else None,
                source=d.source,
                decider=_person(d.decider_member, d.decider_label),
                executor=_person(d.executor_member, d.executor_label),
                executor_accepted=accepted(d),
                due_date=d.due_date,
                criterion=d.criterion,
                private=d.private,
                state=d.state.value,
                proof=d.proof,
                cancel_reason=d.cancel_reason,
                closed_at=d.closed_at,
                created_at=d.created_at,
                missing=missing_fields(d) if open_ else [],
                late=is_late(d, today),
                reminder_on=mid_term(d) if d.state == DecisionState.OPEN else None,
                orphan_days=orphan_age(d, today),
                is_executor=d.executor_member_id == membership.id,
                can_write=_can_write(db, membership, d),
                tasks=[
                    DecisionTaskRef(
                        id=t.id, title=t.title, status=t.status, project_id=t.project_id
                    )
                    for t in links.get(d.id, [])
                ],
                arbitration=d.arbitration,
                arbitration_submitted_at=d.arbitration_submitted_at,
                version=d.version,
            )
        )
    return out


def _one(db: Session, membership: Membership, decision_id: uuid.UUID) -> DecisionOut:
    decision = db.scalar(_query().where(Decision.id == decision_id))
    return decisions_out(db, membership, [decision])[0]


def _journal(db, membership, decision: Decision, action: str, after=None, before=None):
    record(
        db,
        action=action,
        actor_id=membership.user_id,
        space_id=decision.space_id,
        target_type="decision",
        target_id=decision.id,
        before=before,
        after={"decision": decision.statement[:200], **(after or {})},
    )


# ---------- Décisions ----------


@router.get("/decisions")
def list_decisions(
    membership: CurrentMembership,
    db: DbSession,
    project_id: uuid.UUID | None = None,
    meeting_id: uuid.UUID | None = None,
) -> list[DecisionOut]:
    query = _query().where(_visible_filter(db, membership))
    if project_id:
        query = query.where(Decision.project_id == project_id)
    if meeting_id:
        query = query.where(Decision.meeting_id == meeting_id)
    decisions = db.scalars(
        query.order_by(Decision.due_date.asc().nulls_last(), Decision.created_at.desc()).limit(
            MAX_LIST
        )
    ).all()
    return decisions_out(db, membership, list(decisions))


def _apply(db: Session, membership: Membership, decision: Decision, body, sent: set[str]) -> None:
    for name in ("statement", "source", "due_date", "criterion"):
        if name in sent:
            value = getattr(body, name)
            if name == "statement" and not value:
                continue
            setattr(decision, name, value or None if name != "statement" else value)
    if "private" in sent and body.private is not None:
        decision.private = body.private
    if "project_id" in sent or "meeting_id" in sent:
        project_id = body.project_id if "project_id" in sent else decision.project_id
        meeting_id = body.meeting_id if "meeting_id" in sent else decision.meeting_id
        _check_links(db, membership, project_id, meeting_id)
        decision.project_id, decision.meeting_id = project_id, meeting_id
    if "decider_member_id" in sent or "decider_label" in sent:
        decision.decider_member_id, decision.decider_label = _resolve_person(
            db, membership.space_id, body.decider_member_id, body.decider_label
        )
    if "executor_member_id" in sent or "executor_label" in sent:
        before = (decision.executor_member_id, decision.executor_label)
        decision.executor_member_id, decision.executor_label = _resolve_person(
            db, membership.space_id, body.executor_member_id, body.executor_label
        )
        if (decision.executor_member_id, decision.executor_label) != before:
            # Nouveau porteur : il doit accepter à son tour (l'ancienneté, elle, continue).
            decision.executor_accepted_at = None


@router.post("/decisions", status_code=201)
def create_decision(
    body: DecisionCreate, membership: CurrentMembership, db: DbSession
) -> DecisionOut:
    if membership.role not in WRITERS:
        raise HTTPException(403, "Votre rôle ne permet pas de consigner une décision.")
    decision = Decision(
        space_id=membership.space_id,
        statement=body.statement,
        state=DecisionState.DRAFT,
        private=False,
        created_by_id=membership.user_id,
    )
    _apply(db, membership, decision, body, body.model_fields_set - {"statement", "validate_now"})
    if body.validate_now:
        missing = missing_fields(decision)
        if missing:
            raise HTTPException(422, "Pour valider, il manque : " + ", ".join(missing) + ".")
        decision.state = DecisionState.OPEN
        decision.validated_at = utcnow()
    if decision.executor_member_id == membership.id:
        decision.executor_accepted_at = utcnow()
    db.add(decision)
    db.flush()
    _journal(
        db,
        membership,
        decision,
        "decision.created",
        after={"state": decision.state.value, "project_id": str(decision.project_id or "") or None},
    )
    db.commit()
    return _one(db, membership, decision.id)


@router.patch("/decisions/{decision_id}")
def update_decision(
    decision_id: uuid.UUID, body: DecisionUpdate, membership: CurrentMembership, db: DbSession
) -> DecisionOut:
    decision = _load(db, membership, decision_id)
    if decision.version != body.version:
        raise HTTPException(409, CONFLICT)
    if decision.state in (DecisionState.DONE, DecisionState.CANCELLED):
        raise HTTPException(400, "Cette décision est clôturée : rouvrez-la pour la modifier.")
    sent = body.model_fields_set - {"version"}
    before = {"due_date": str(decision.due_date) if decision.due_date else None}
    _apply(db, membership, decision, body, sent)
    if decision.state == DecisionState.OPEN and missing_fields(decision):
        raise HTTPException(
            422,
            "Une décision validée garde un responsable nommé, une échéance et un critère : "
            + ", ".join(missing_fields(decision))
            + " manquant(s).",
        )
    if "due_date" in sent and str(decision.due_date) != before["due_date"]:
        # Nouvelle échéance : la relance à mi-échéance repart de zéro.
        decision.reminded_on = None
    decision.version += 1
    _journal(db, membership, decision, "decision.updated", after={"fields": sorted(sent)})
    db.commit()
    return _one(db, membership, decision.id)


@router.post("/decisions/{decision_id}/validate")
def validate_decision(
    decision_id: uuid.UUID, body: DecisionVersion, membership: CurrentMembership, db: DbSession
) -> DecisionOut:
    decision = _load(db, membership, decision_id)
    if decision.version != body.version:
        raise HTTPException(409, CONFLICT)
    if decision.state != DecisionState.DRAFT:
        raise HTTPException(400, "Seul un brouillon peut être validé.")
    missing = missing_fields(decision)
    if missing:
        raise HTTPException(422, "Pour valider, il manque : " + ", ".join(missing) + ".")
    decision.state = DecisionState.OPEN
    decision.validated_at = utcnow()
    decision.version += 1
    _journal(
        db, membership, decision, "decision.validated", after={"due_date": str(decision.due_date)}
    )
    db.commit()
    return _one(db, membership, decision.id)


@router.post("/decisions/{decision_id}/accept")
def accept_decision(
    decision_id: uuid.UUID, body: DecisionVersion, membership: CurrentMembership, db: DbSession
) -> DecisionOut:
    """Le responsable d'exécution accepte sa responsabilité (même en lecture seule ailleurs)."""
    decision = _load(db, membership, decision_id, write=False)
    if decision.executor_member_id != membership.id:
        raise HTTPException(403, "Seul le responsable désigné peut accepter cette décision.")
    db.refresh(decision, with_for_update={"of": Decision})
    if decision.version != body.version:
        raise HTTPException(409, CONFLICT)
    if decision.executor_accepted_at is None:
        decision.executor_accepted_at = utcnow()
        decision.version += 1
        _journal(db, membership, decision, "decision.accepted")
        db.commit()
    return _one(db, membership, decision.id)


@router.post("/decisions/{decision_id}/close")
def close_decision(
    decision_id: uuid.UUID, body: DecisionClose, membership: CurrentMembership, db: DbSession
) -> DecisionOut:
    decision = _load(db, membership, decision_id)
    if decision.version != body.version:
        raise HTTPException(409, CONFLICT)
    if body.state == "done" and decision.state != DecisionState.OPEN:
        raise HTTPException(400, "Validez d'abord la décision avant de la déclarer exécutée.")
    if decision.state in (DecisionState.DONE, DecisionState.CANCELLED):
        raise HTTPException(400, "Cette décision est déjà clôturée.")
    if not body.note.strip():
        raise HTTPException(422, "Indiquez la preuve ou le motif.")
    if body.state == "done":
        decision.state, decision.proof = DecisionState.DONE, body.note
    else:
        decision.state, decision.cancel_reason = DecisionState.CANCELLED, body.note
    decision.closed_at = utcnow()
    decision.version += 1
    _journal(db, membership, decision, f"decision.{body.state}", after={"note": body.note})
    db.commit()
    return _one(db, membership, decision.id)


@router.post("/decisions/{decision_id}/reopen")
def reopen_decision(
    decision_id: uuid.UUID, body: DecisionVersion, membership: CurrentMembership, db: DbSession
) -> DecisionOut:
    decision = _load(db, membership, decision_id)
    if decision.version != body.version:
        raise HTTPException(409, CONFLICT)
    if decision.state not in (DecisionState.DONE, DecisionState.CANCELLED):
        return _one(db, membership, decision.id)
    previous = decision.state.value
    decision.state = DecisionState.OPEN if decision.validated_at else DecisionState.DRAFT
    decision.closed_at = None
    decision.version += 1
    _journal(
        db,
        membership,
        decision,
        "decision.reopened",
        before={"state": previous, "note": decision.proof or decision.cancel_reason},
    )
    decision.proof = decision.cancel_reason = None
    db.commit()
    return _one(db, membership, decision.id)


@router.post("/decisions/{decision_id}/tasks", status_code=201)
def create_execution_task(
    decision_id: uuid.UUID, body: DecisionTaskCreate, membership: CurrentMembership, db: DbSession
) -> DecisionOut:
    """Crée la tâche d'exécution dans le projet de la décision (responsable et échéance repris),
    reliée à la décision."""
    decision = _load(db, membership, decision_id)
    if decision.version != body.version:
        raise HTTPException(409, CONFLICT)
    if decision.project_id is None:
        raise HTTPException(422, "Rattachez d'abord la décision à un projet.")
    project = db.get(Project, decision.project_id)
    if project.status in CLOSED_PROJECT_STATUSES:
        raise HTTPException(400, "Ce projet est clôturé : rouvrez-le pour ajouter des tâches.")
    count = db.scalar(
        select(func.count(DecisionTask.id)).where(DecisionTask.decision_id == decision.id)
    )
    if count >= 50:
        raise HTTPException(422, "50 tâches au plus par décision.")
    task = create_task_in(
        db,
        membership,
        project,
        TaskCreate(
            title=body.title or decision.statement[:200],
            deliverable=(decision.criterion or "")[:300] or None,
            due_date=decision.due_date,
            assignee_member_id=decision.executor_member_id,
            assignee_label=None if decision.executor_member_id else decision.executor_label,
        ),
    )
    db.add(DecisionTask(decision_id=decision.id, task_id=task.id))
    decision = db.get(Decision, decision.id)
    decision.version += 1
    _journal(db, membership, decision, "decision.task_created", after={"task": task.title})
    db.commit()
    return _one(db, membership, decision.id)


# ---------- Réunions ----------


def meetings_out(db: Session, meetings: list[Meeting]) -> list[MeetingOut]:
    now = utcnow()
    project_ids = {m.project_id for m in meetings if m.project_id}
    projects = dict(
        db.execute(select(Project.id, Project.title).where(Project.id.in_(project_ids))).all()
    )
    counts = (
        dict(
            db.execute(
                select(Decision.meeting_id, func.count(Decision.id))
                .where(Decision.meeting_id.in_([m.id for m in meetings]))
                .group_by(Decision.meeting_id)
            ).all()
        )
        if meetings
        else {}
    )
    return [
        MeetingOut(
            id=m.id,
            title=m.title,
            project=RefOut(id=m.project_id, name=projects[m.project_id])
            if m.project_id in projects
            else None,
            ended_at=m.ended_at,
            participants=m.participants,
            minutes_state=m.minutes_state.value,
            minutes_due_at=minutes_due(m),
            minutes_late=minutes_late(m, now),
            minutes_sent_at=m.minutes_sent_at,
            minutes_channel=m.minutes_channel,
            minutes_recipients=m.minutes_recipients,
            minutes_url=m.minutes_url,
            decisions_count=counts.get(m.id, 0),
            version=m.version,
        )
        for m in meetings
    ]


def _meeting_filter(db: Session, membership: Membership):
    if membership.role == Role.OWNER:
        return Meeting.space_id == membership.space_id
    projects = visible_project_ids(db, membership) or set()
    scope = (
        Meeting.project_id.in_(projects)
        if membership.role == Role.GUEST
        else or_(Meeting.project_id.is_(None), Meeting.project_id.in_(projects))
    )
    return (Meeting.space_id == membership.space_id) & scope


@router.get("/meetings")
def list_meetings(membership: CurrentMembership, db: DbSession) -> list[MeetingOut]:
    meetings = db.scalars(
        select(Meeting)
        .where(_meeting_filter(db, membership))
        .order_by(Meeting.ended_at.desc())
        .limit(200)
    ).all()
    return meetings_out(db, list(meetings))


@router.post("/meetings", status_code=201)
def create_meeting(body: MeetingCreate, membership: CurrentMembership, db: DbSession) -> MeetingOut:
    if membership.role not in WRITERS:
        raise HTTPException(403, "Votre rôle ne permet pas d'ajouter une réunion.")
    if body.project_id is not None:
        project = db.get(Project, body.project_id)
        if project is None or project.space_id != membership.space_id:
            raise HTTPException(404, "Projet introuvable.")
        ensure_visible(db, membership, project)
    meeting = Meeting(
        space_id=membership.space_id,
        project_id=body.project_id,
        title=body.title,
        ended_at=body.ended_at,
        participants=body.participants or None,
        minutes_state=MinutesState.TO_WRITE,
        created_by_id=membership.user_id,
    )
    db.add(meeting)
    db.flush()
    record(
        db,
        action="meeting.created",
        actor_id=membership.user_id,
        space_id=meeting.space_id,
        target_type="meeting",
        target_id=meeting.id,
        after={"meeting": meeting.title, "ended_at": meeting.ended_at.isoformat()},
    )
    db.commit()
    return meetings_out(db, [meeting])[0]


@router.patch("/meetings/{meeting_id}")
def update_meeting(
    meeting_id: uuid.UUID, body: MeetingUpdate, membership: CurrentMembership, db: DbSession
) -> MeetingOut:
    if membership.role not in WRITERS:
        raise HTTPException(403, "Votre rôle ne permet pas de modifier une réunion.")
    meeting = db.scalar(
        select(Meeting)
        .where(Meeting.id == meeting_id, _meeting_filter(db, membership))
        .with_for_update()
    )
    if meeting is None:
        raise HTTPException(404, "Réunion introuvable.")
    if meeting.version != body.version:
        raise HTTPException(409, CONFLICT)
    sent = body.model_fields_set - {"version"}
    for name in ("title", "ended_at"):
        if name in sent and getattr(body, name):
            setattr(meeting, name, getattr(body, name))
    for name in ("participants", "minutes_channel", "minutes_recipients"):
        if name in sent:
            setattr(meeting, name, getattr(body, name) or None)
    if "minutes_url" in sent:
        meeting.minutes_url = str(body.minutes_url) if body.minutes_url else None
    after: dict = {}
    if (
        "minutes_state" in sent
        and body.minutes_state
        and body.minutes_state != meeting.minutes_state.value
    ):
        meeting.minutes_state = MinutesState(body.minutes_state)
        # « Envoyé » est une déclaration (date, canal, destinataires), pas une preuve de remise.
        meeting.minutes_sent_at = utcnow() if meeting.minutes_state == MinutesState.SENT else None
        after = {"minutes_state": body.minutes_state, "channel": meeting.minutes_channel}
    meeting.version += 1
    record(
        db,
        action="meeting.minutes" if after else "meeting.updated",
        actor_id=membership.user_id,
        space_id=meeting.space_id,
        target_type="meeting",
        target_id=meeting.id,
        after={"meeting": meeting.title, **after},
    )
    db.commit()
    return meetings_out(db, [meeting])[0]
