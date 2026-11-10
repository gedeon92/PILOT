"""Assistant IA (lot E, décisions du 10 nov. 2026).

- Éteint par défaut ; seul un propriétaire l'allume pour son espace (Paramètres).
- Chaque personne a ses propres conversations, privées ; l'assistant lit avec ses droits.
- Les changements sont des propositions : la personne clique « Appliquer » ou « Refuser ».
"""

import uuid
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from datetime import datetime, time
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from pilot_api.ai import assistant
from pilot_api.ai.apply import apply_action, reject_action
from pilot_api.audit import record
from pilot_api.config import get_settings
from pilot_api.db import _session_factory, get_engine
from pilot_api.deps import CurrentMembership, DbSession, OwnerMembership
from pilot_api.models import (
    AiAction,
    AiConversation,
    AiUsage,
    Membership,
    Role,
    Task,
    utcnow,
)
from pilot_api.schemas import (
    AiActionOut,
    AiChange,
    AiConversationOut,
    AiConversationSummary,
    AiMessageIn,
    AiStatusOut,
    AiToggle,
    AiTurnOut,
)

router = APIRouter(prefix="/api/spaces/{space_id}/ai", tags=["assistant IA"])

MAX_CONVERSATIONS = 100
OFF = "L'assistant n'est pas allumé pour cet espace (Paramètres, réservé aux propriétaires)."
NO_KEY = "L'assistant n'est pas encore configuré sur le serveur (clé Anthropic manquante)."


def get_session_opener() -> Callable[[], AbstractContextManager[Session]]:
    """Sessions pour le travail en arrière-plan (les tests la remplacent)."""

    @contextmanager
    def _open() -> Iterator[Session]:
        engine = get_engine()
        if engine is None:
            raise RuntimeError("Base non configurée")
        with _session_factory(engine)() as session:
            yield session

    return _open


SessionOpener = Annotated[
    Callable[[], AbstractContextManager[Session]], Depends(get_session_opener)
]


def _available() -> bool:
    return bool(get_settings().anthropic_api_key)


def _used_today(db: Session, membership: Membership) -> int:
    start = datetime.combine(utcnow().date(), time.min, tzinfo=utcnow().tzinfo)
    return (
        db.scalar(
            select(func.count(AiUsage.id)).where(
                AiUsage.space_id == membership.space_id,
                AiUsage.user_id == membership.user_id,
                AiUsage.at >= start,
            )
        )
        or 0
    )


def _require_on(membership: Membership) -> None:
    if not _available():
        raise HTTPException(503, NO_KEY)
    if not membership.space.ai_enabled:
        raise HTTPException(403, OFF)


def _status(db: Session, membership: Membership) -> AiStatusOut:
    return AiStatusOut(
        available=_available(),
        enabled=bool(membership.space.ai_enabled),
        can_toggle=membership.role == Role.OWNER,
        daily_limit=get_settings().ai_daily_limit,
        used_today=_used_today(db, membership),
    )


@router.get("/status")
def ai_status(membership: CurrentMembership, db: DbSession) -> AiStatusOut:
    return _status(db, membership)


@router.put("/status")
def toggle_ai(body: AiToggle, membership: OwnerMembership, db: DbSession) -> AiStatusOut:
    space = membership.space
    db.refresh(space, with_for_update=True)
    if bool(space.ai_enabled) != body.enabled:
        space.ai_enabled = body.enabled
        record(
            db,
            action="space.ai_enabled" if body.enabled else "space.ai_disabled",
            actor_id=membership.user_id,
            space_id=space.id,
            target_type="space",
            target_id=space.id,
        )
        db.commit()
    return _status(db, membership)


def _own(db: Session, membership: Membership, conversation_id: uuid.UUID) -> AiConversation:
    conversation = db.get(AiConversation, conversation_id, populate_existing=True)
    if (
        conversation is None
        or conversation.user_id != membership.user_id
        or conversation.space_id != membership.space_id
    ):
        raise HTTPException(404, "Conversation introuvable.")
    return conversation


def _action_out(action: AiAction, task_projects: dict[uuid.UUID, uuid.UUID | None]) -> AiActionOut:
    project_id = task_id = None
    if action.kind in ("update_task", "comment"):
        task_id = action.target_id
        project_id = task_projects.get(action.target_id)
    elif action.target_id is not None:
        project_id = action.target_id
    return AiActionOut(
        id=action.id,
        kind=action.kind,
        summary=action.summary,
        changes=[AiChange(**c) for c in action.changes or []],
        state=action.state.value,
        result=action.result,
        project_id=project_id,
        task_id=task_id,
    )


def _conversation_out(db: Session, conversation: AiConversation) -> AiConversationOut:
    actions = db.scalars(select(AiAction).where(AiAction.conversation_id == conversation.id)).all()
    task_ids = [a.target_id for a in actions if a.kind in ("update_task", "comment")]
    task_projects = (
        dict(db.execute(select(Task.id, Task.project_id).where(Task.id.in_(task_ids))).all())
        if task_ids
        else {}
    )
    by_id = {str(a.id): _action_out(a, task_projects) for a in actions}
    turns = []
    for turn in conversation.turns or []:
        turns.append(
            AiTurnOut(
                role=turn.get("role", "assistant"),
                text=turn.get("text", ""),
                at=turn.get("at"),
                error=bool(turn.get("error")),
                actions=[by_id[i] for i in turn.get("action_ids", []) if i in by_id],
            )
        )
    return AiConversationOut(
        id=conversation.id,
        title=conversation.title,
        status=conversation.status,
        updated_at=conversation.updated_at,
        turns=turns,
    )


@router.get("/conversations")
def list_conversations(membership: CurrentMembership, db: DbSession) -> list[AiConversationSummary]:
    rows = db.scalars(
        select(AiConversation)
        .where(
            AiConversation.space_id == membership.space_id,
            AiConversation.user_id == membership.user_id,
        )
        .order_by(AiConversation.updated_at.desc())
        .limit(MAX_CONVERSATIONS)
    ).all()
    return [
        AiConversationSummary(id=c.id, title=c.title, status=c.status, updated_at=c.updated_at)
        for c in rows
    ]


@router.get("/conversations/{conversation_id}")
def get_conversation(
    conversation_id: uuid.UUID, membership: CurrentMembership, db: DbSession
) -> AiConversationOut:
    conversation = _own(db, membership, conversation_id)
    assistant.reset_if_stale(db, conversation)
    return _conversation_out(db, conversation)


@router.delete("/conversations/{conversation_id}", status_code=204)
def delete_conversation(
    conversation_id: uuid.UUID, membership: CurrentMembership, db: DbSession
) -> Response:
    conversation = _own(db, membership, conversation_id)
    db.delete(conversation)
    db.commit()
    return Response(status_code=204)


def _title(text: str) -> str:
    first = " ".join(text.split())
    return first if len(first) <= 80 else first[:79].rstrip() + "…"


def _start(
    db: Session,
    membership: Membership,
    conversation: AiConversation,
    text: str,
    background: BackgroundTasks,
    opener: Callable[[], AbstractContextManager[Session]],
) -> None:
    now = utcnow()
    conversation.history = [*conversation.history, {"role": "user", "content": text}]
    conversation.turns = [
        *conversation.turns,
        {"role": "user", "text": text, "at": now.isoformat()},
    ]
    conversation.status = "thinking"
    conversation.error = None
    conversation.updated_at = now
    db.commit()
    background.add_task(assistant.run_turn, opener, conversation.id)


def _check_quota(db: Session, membership: Membership) -> None:
    limit = get_settings().ai_daily_limit
    if _used_today(db, membership) >= limit:
        raise HTTPException(
            429, f"Limite atteinte : {limit} questions par jour. Elle repart demain."
        )


@router.post("/conversations", status_code=201)
def start_conversation(
    body: AiMessageIn,
    membership: CurrentMembership,
    db: DbSession,
    background: BackgroundTasks,
    opener: SessionOpener,
) -> AiConversationOut:
    _require_on(membership)
    _check_quota(db, membership)
    count = db.scalar(
        select(func.count(AiConversation.id)).where(
            AiConversation.space_id == membership.space_id,
            AiConversation.user_id == membership.user_id,
        )
    )
    if count >= MAX_CONVERSATIONS:
        raise HTTPException(
            422, f"{MAX_CONVERSATIONS} conversations au plus : supprimez-en d'anciennes."
        )
    conversation = AiConversation(
        space_id=membership.space_id,
        user_id=membership.user_id,
        title=_title(body.text),
        history=[],
        turns=[],
    )
    db.add(conversation)
    db.flush()
    _start(db, membership, conversation, body.text, background, opener)
    return _conversation_out(db, conversation)


@router.post("/conversations/{conversation_id}/messages")
def send_message(
    conversation_id: uuid.UUID,
    body: AiMessageIn,
    membership: CurrentMembership,
    db: DbSession,
    background: BackgroundTasks,
    opener: SessionOpener,
) -> AiConversationOut:
    _require_on(membership)
    conversation = db.get(AiConversation, conversation_id, with_for_update=True)
    if (
        conversation is None
        or conversation.user_id != membership.user_id
        or conversation.space_id != membership.space_id
    ):
        raise HTTPException(404, "Conversation introuvable.")
    assistant.reset_if_stale(db, conversation)
    if conversation.status == "thinking":
        raise HTTPException(409, "L'assistant prépare encore sa réponse précédente.")
    _check_quota(db, membership)
    _start(db, membership, conversation, body.text, background, opener)
    return _conversation_out(db, conversation)


@router.post("/actions/{action_id}/apply")
def apply(action_id: uuid.UUID, membership: CurrentMembership, db: DbSession) -> AiActionOut:
    _require_on(membership)
    action = apply_action(db, membership, action_id)
    return _single(db, action)


@router.post("/actions/{action_id}/reject")
def reject(action_id: uuid.UUID, membership: CurrentMembership, db: DbSession) -> AiActionOut:
    action = reject_action(db, membership, action_id)
    return _single(db, action)


def _single(db: Session, action: AiAction) -> AiActionOut:
    task_projects = {}
    if action.kind in ("update_task", "comment"):
        task = db.get(Task, action.target_id)
        task_projects = {action.target_id: task.project_id if task else None}
    return _action_out(action, task_projects)
