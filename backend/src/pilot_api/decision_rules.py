"""Règles des décisions et des réunions (étape F3, cahier V2 DEC01–DEC05).

Partagées par les routes et le calcul des alertes. Les délais viennent des fiches sources :
relevé sous 24 h, relance unique à mi-échéance, sujet sans porteur accepté au plus tard à
30 jours.
"""

import unicodedata
from datetime import date, datetime, timedelta

from pilot_api.models import Decision, DecisionState, Meeting, MinutesState

MINUTES_HOURS = 24
ORPHAN_DAYS = 30
# « L'équipe » n'est pas un responsable nommé (DEC01).
VAGUE_PEOPLE = {
    "equipe",
    "l'equipe",
    "l equipe",
    "lequipe",
    "tous",
    "tout le monde",
    "nous",
    "on",
    "a definir",
    "a voir",
    "personne",
    "?",
    "tbd",
}
MIN_CRITERION = 10


def _plain(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.strip().lower())
    return "".join(c for c in text if not unicodedata.combining(c)).replace("’", "'")


def missing_fields(decision: Decision) -> list[str]:
    """Ce qui manque pour valider la décision (elle reste en brouillon sinon)."""
    missing = []
    label = (decision.executor_label or "").strip()
    if not decision.executor_member_id and not label:
        missing.append("un responsable d'exécution nommé")
    elif not decision.executor_member_id and _plain(label) in VAGUE_PEOPLE:
        missing.append(f"un responsable nommé (« {label} » ne désigne personne)")
    if decision.due_date is None:
        missing.append("une échéance datée")
    if len((decision.criterion or "").strip()) < MIN_CRITERION:
        missing.append("un critère observable (ce qui prouvera l'exécution)")
    return missing


def accepted(decision: Decision) -> bool:
    """Un nom libre n'a pas de compte : sa désignation vaut acceptation déclarée. Un membre
    doit accepter lui-même (DEC05)."""
    if decision.executor_member_id:
        return decision.executor_accepted_at is not None
    label = (decision.executor_label or "").strip()
    return bool(label) and _plain(label) not in VAGUE_PEOPLE


def orphan_age(decision: Decision, today: date) -> int | None:
    """Jours depuis la création d'un sujet encore sans porteur accepté ; None sinon."""
    if decision.state in (DecisionState.DONE, DecisionState.CANCELLED) or accepted(decision):
        return None
    return (today - decision.created_at.date()).days


def mid_term(decision: Decision) -> date | None:
    """Jour de la relance unique : milieu entre la validation (ou la création) et l'échéance."""
    if decision.due_date is None:
        return None
    start = (decision.validated_at or decision.created_at).date()
    if decision.due_date <= start:
        return None
    return start + timedelta(days=(decision.due_date - start).days // 2)


def is_late(decision: Decision, today: date) -> bool:
    return (
        decision.state == DecisionState.OPEN
        and decision.due_date is not None
        and decision.due_date < today
    )


def minutes_due(meeting: Meeting) -> datetime:
    return meeting.ended_at + timedelta(hours=MINUTES_HOURS)


def minutes_late(meeting: Meeting, now: datetime) -> bool:
    return meeting.minutes_state != MinutesState.SENT and now > minutes_due(meeting)
