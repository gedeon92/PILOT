"""Règles des jalons (étape F2), partagées par les routes et le calcul des alertes."""

from datetime import date

from pilot_api.models import CLOSED_TASK_STATUSES, Milestone, MilestoneState, Task, TaskStatus

# Horizon de risque (cahier V2 : trois semaines) et nombre de reports avant revue de cadrage.
RISK_HORIZON_DAYS = 21
REFRAME_AFTER = 2
STATE_WORDS = {
    MilestoneState.PLANNED: "à venir",
    MilestoneState.REACHED: "atteint",
    MilestoneState.MISSED: "manqué",
    MilestoneState.CANCELLED: "annulé",
}


def risk(milestone: Milestone, tasks: list[Task], today: date) -> tuple[bool, bool, list[str]]:
    """(en retard, à risque, raisons) — sans rien inventer : seuls des faits enregistrés."""
    if milestone.state != MilestoneState.PLANNED:
        return False, False, []
    days = (milestone.due_date - today).days
    late = days < 0
    reasons: list[str] = []
    open_tasks = [t for t in tasks if t.status not in CLOSED_TASK_STATUSES]
    overdue = [t for t in open_tasks if t.due_date and t.due_date < today]
    blocked = [t for t in open_tasks if t.status == TaskStatus.BLOCKED]
    after = [t for t in open_tasks if t.due_date and t.due_date > milestone.due_date]
    if overdue:
        reasons.append(f"{len(overdue)} tâche(s) liée(s) en retard")
    if blocked:
        reasons.append(f"{len(blocked)} tâche(s) liée(s) bloquée(s)")
    if after:
        reasons.append(f"{len(after)} tâche(s) prévue(s) après la date du jalon")
    if not (milestone.owner_member_id or milestone.owner_label):
        reasons.append("sans porteur")
    if milestone.postpone_count >= REFRAME_AFTER:
        reasons.append(f"déjà reporté {milestone.postpone_count} fois")
    at_risk = not late and days <= RISK_HORIZON_DAYS and bool(reasons)
    return late, at_risk, reasons if (late or at_risk) else []
