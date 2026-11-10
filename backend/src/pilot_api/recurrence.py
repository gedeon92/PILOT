"""Tâches répétées : calcul de la prochaine échéance."""

import calendar
from datetime import date, timedelta

from pilot_api.models import TaskRecurrence


def _add_months(day: date, months: int) -> date:
    """Même jour du mois, ramené au dernier jour si le mois est plus court (31 → 30, 28…)."""
    index = day.month - 1 + months
    year, month = day.year + index // 12, index % 12 + 1
    return day.replace(
        year=year, month=month, day=min(day.day, calendar.monthrange(year, month)[1])
    )


def _step(due: date, recurrence: TaskRecurrence, count: int) -> date:
    if recurrence == TaskRecurrence.DAILY:
        return due + timedelta(days=count)
    if recurrence == TaskRecurrence.WEEKLY:
        return due + timedelta(weeks=count)
    if recurrence == TaskRecurrence.MONTHLY:
        return _add_months(due, count)
    return _add_months(due, 12 * count)


def next_due_date(due: date, recurrence: TaskRecurrence, today: date) -> date:
    """Prochaine échéance après `due`, au même rythme. Si la tâche a été terminée en retard,
    on saute les échéances déjà passées : la suivante ne naît jamais en retard."""
    count = 1
    candidate = _step(due, recurrence, count)
    while candidate < today and count < 5000:
        count += 1
        candidate = _step(due, recurrence, count)
    return candidate
