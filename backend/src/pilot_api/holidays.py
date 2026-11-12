"""Jours fériés de l'espace (cahier V2, RIT05 : « le calendrier ouvré du pays et la politique
de jours fériés sont configurables »).

L'espace garde sa propre liste (date + nom), gérée par un propriétaire. Pour la France et le
Sénégal, les jours à date fixe et ceux qui dépendent de Pâques peuvent être proposés
automatiquement. Les fêtes qui suivent le calendrier lunaire (Tamkharit, Maouloud, Korité,
Tabaski) ou fixées chaque année (Magal de Touba) ne se calculent pas de façon sûre : elles
sont à saisir une fois leur date annoncée.

Effets : une routine « jours ouvrés » ne tombe pas un jour férié (une routine au jour du mois
est avancée au jour ouvré précédent) ; les délais en jours ouvrés sautent les jours fériés.
"""

from datetime import date, timedelta
from typing import Any

COUNTRIES = {"FR": "France", "SN": "Sénégal"}

LUNAR_NOTE = {
    "SN": (
        "À ajouter à la main dès que leur date est annoncée : Tamkharit (Achoura), Maouloud, "
        "Korité, Tabaski et Grand Magal de Touba."
    ),
    "FR": None,
}


def easter(year: int) -> date:
    """Dimanche de Pâques (calendrier grégorien, algorithme anonyme)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    m = (32 + 2 * e + 2 * i - h - k) % 7
    n = (a + 11 * h + 22 * m) // 451
    month, day = divmod(h + m - 7 * n + 114, 31)
    return date(year, month, day + 1)


def presets(country: str, year: int) -> list[dict[str, str]]:
    """Jours fériés calculables pour ce pays et cette année."""
    e = easter(year)
    moving = [
        (e + timedelta(days=1), "Lundi de Pâques"),
        (e + timedelta(days=39), "Ascension"),
        (e + timedelta(days=50), "Lundi de Pentecôte"),
    ]
    if country == "FR":
        fixed = [
            ((1, 1), "Jour de l'an"),
            ((5, 1), "Fête du Travail"),
            ((5, 8), "Victoire 1945"),
            ((7, 14), "Fête nationale"),
            ((8, 15), "Assomption"),
            ((11, 1), "Toussaint"),
            ((11, 11), "Armistice 1918"),
            ((12, 25), "Noël"),
        ]
    elif country == "SN":
        fixed = [
            ((1, 1), "Jour de l'an"),
            ((4, 4), "Fête de l'Indépendance"),
            ((5, 1), "Fête du Travail"),
            ((8, 15), "Assomption"),
            ((11, 1), "Toussaint"),
            ((12, 25), "Noël"),
        ]
    else:
        return []
    days = [(date(year, m, d), label) for (m, d), label in fixed] + moving
    return [{"date": day.isoformat(), "label": label} for day, label in sorted(days)]


def holiday_set(holidays: list[dict[str, Any]] | None) -> frozenset[date]:
    result = set()
    for item in holidays or []:
        try:
            result.add(date.fromisoformat(str(item.get("date"))))
        except (TypeError, ValueError):
            continue
    return frozenset(result)


def is_workday(day: date, holidays: frozenset[date]) -> bool:
    return day.weekday() < 5 and day not in holidays


def add_workdays(day: date, count: int, holidays: frozenset[date] = frozenset()) -> date:
    """`count` jours ouvrés après `day` (week-ends et jours fériés exclus)."""
    current = day
    while count > 0:
        current += timedelta(days=1)
        if is_workday(current, holidays):
            count -= 1
    return current


def previous_workday(day: date, holidays: frozenset[date]) -> date:
    current = day
    for _ in range(31):
        if is_workday(current, holidays):
            return current
        current -= timedelta(days=1)
    return day
