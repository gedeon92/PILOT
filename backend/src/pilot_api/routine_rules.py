"""Routines de pilotage (étape F5, cahier V2 RIT01–RIT07) : dates des occurrences et routines
types préchargées.

« Deux fois par mois » (deux jours du mois) et « toutes les deux semaines » (une semaine sur
deux à partir de la date de début) sont des règles différentes. Une date de week-end peut être
ramenée au vendredi précédent. Les jours fériés ne sont pas encore pris en compte.
"""

import calendar
from datetime import date, timedelta
from typing import Any

from pilot_api.holidays import previous_workday
from pilot_api.models import Routine, RoutineFrequency

F = RoutineFrequency
# Fenêtre de génération : un mois en arrière (rattrapage après une interruption, une seule
# fois grâce à la contrainte d'unicité) et six semaines en avant.
BACKFILL_DAYS = 31
AHEAD_DAYS = 42


def _workday(day: date, enabled: bool, holidays: frozenset[date] = frozenset()) -> date:
    """Un jour de week-end ou férié est ramené au jour ouvré précédent."""
    return previous_workday(day, holidays) if enabled else day


def _month_day(year: int, month: int, day: int) -> date:
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))


def _nth_weekday(year: int, month: int, n: int, weekday: int) -> date | None:
    days = [
        date(year, month, d)
        for d in range(1, calendar.monthrange(year, month)[1] + 1)
        if date(year, month, d).weekday() == weekday
    ]
    if n == -1:
        return days[-1]
    return days[n - 1] if 1 <= n <= len(days) else None


def _months(start: date, end: date):
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        yield year, month
        month += 1
        if month > 12:
            year, month = year + 1, 1


def dates_between(
    routine: Routine, start: date, end: date, holidays: frozenset[date] = frozenset()
) -> list[date]:
    """Dates prévues par la série entre `start` et `end` inclus (jamais avant le début).
    Une routine « jours ouvrés » ne tombe ni un jour férié ni, au jour du mois, un week-end."""
    start = max(start, routine.start_date)
    if end < start:
        return []
    result: set[date] = set()
    weekdays = set(routine.weekdays or [])
    if routine.frequency in (F.DAILY, F.WEEKLY, F.BIWEEKLY):
        if not weekdays:
            weekdays = {routine.start_date.weekday()}
        anchor = routine.start_date - timedelta(days=routine.start_date.weekday())
        day = start
        while day <= end:
            skip = routine.workdays_only and day in holidays
            if day.weekday() in weekdays and not skip:
                week = (day - anchor).days // 7
                if routine.frequency != F.BIWEEKLY or week % 2 == 0:
                    result.add(day)
            day += timedelta(days=1)
        return sorted(result)
    # Fréquences au mois : on calcule chaque mois puis on garde ce qui tombe dans la fenêtre.
    for year, month in _months(start - timedelta(days=7), end + timedelta(days=7)):
        if routine.frequency == F.QUARTERLY and (month - routine.start_date.month) % 3:
            continue
        candidates: list[date] = []
        if routine.frequency == F.MONTHLY and routine.nth_weekday:
            nth = _nth_weekday(
                year,
                month,
                int(routine.nth_weekday.get("n", 1)),
                int(routine.nth_weekday.get("weekday", 0)),
            )
            candidates = [_workday(nth, routine.workdays_only, holidays)] if nth else []
        else:
            days = routine.month_days or [routine.start_date.day]
            if routine.frequency in (F.MONTHLY, F.QUARTERLY):
                days = days[:1]
            candidates = [
                _workday(_month_day(year, month, d), routine.workdays_only, holidays) for d in days
            ]
        result.update(d for d in candidates if start <= d <= end)
    return sorted(result)


def generation_window(
    routine: Routine, today: date, until: date | None = None
) -> tuple[date, date]:
    first = today - timedelta(days=BACKFILL_DAYS)
    if routine.generate_from:
        first = max(first, routine.generate_from)
    last = today + timedelta(days=AHEAD_DAYS)
    if until is not None:
        last = min(max(last, until), today + timedelta(days=120))
    return first, last


def _check(label: str, mandatory: bool = True) -> dict[str, Any]:
    return {"label": label, "mandatory": mandatory}


# Routines types (cahier V2 §08–09) : horaires et durées des routines fournies, modifiables.
# Elles ne sont créées que si la personne les choisit ; les cadences ambiguës (RIT03) restent
# à confirmer avant activation.
PROFILES: dict[str, dict[str, Any]] = {
    "preparer_journee": {
        "title": "Préparer ma journée",
        "purpose": "Agenda, objectifs des rendez-vous, dossiers, décisions du jour et alertes.",
        "frequency": F.DAILY,
        "weekdays": [0, 1, 2, 3, 4],
        "time_of_day": "08:20",
        "duration_minutes": 10,
        "checklist": [
            _check("Agenda et objectifs des rendez-vous relus"),
            _check("Décisions et alertes urgentes du jour vues"),
            _check("Priorités et délégations notées", False),
        ],
        "expected_output": "Priorités du jour et délégations proposées",
    },
    "tour_coordination": {
        "title": "Faire le tour de coordination",
        "purpose": "Point terrain, jalon proche, relance à mi-échéance ou contact externe.",
        "frequency": F.DAILY,
        "weekdays": [0, 1, 2, 3, 4],
        "duration_minutes": 30,
        "checklist": [_check("Constat noté"), _check("Action datée décidée")],
        "expected_output": "Constat et action datée",
    },
    "clore_journee": {
        "title": "Clore ma journée",
        "purpose": "Décisions nouvelles, réponses dues, engagements non tracés, lendemain.",
        "frequency": F.DAILY,
        "weekdays": [0, 1, 2, 3, 4],
        "time_of_day": "17:30",
        "duration_minutes": 10,
        "checklist": [
            _check("Décisions nouvelles consignées"),
            _check("Engagements non tracés transformés en tâches"),
            _check("Lendemain préparé", False),
        ],
        "expected_output": "Aucun sujet sans suite identifiée",
    },
    "rendez_vous_collectif": {
        "title": "Préparer le rendez-vous collectif",
        "purpose": "Ordre du jour : performance, messages, nouveautés, annonces, engagements.",
        "frequency": F.WEEKLY,
        "weekdays": [4],
        "duration_minutes": 30,
        "checklist": [
            _check("Ordre du jour diffusé"),
            _check("Engagements de la semaine passée repris"),
            _check("Relevé prévu sous 24 h après la séance"),
        ],
        "expected_output": "Ordre du jour ; relevé sous 24 h",
    },
    "point_dirigeant": {
        "title": "Préparer le point dirigeant",
        "purpose": "Trois alertes, arbitrages avec dossier, agenda sur trois semaines.",
        "frequency": F.WEEKLY,
        "weekdays": [0],
        "duration_minutes": 45,
        "checklist": [
            _check("Trois alertes retenues"),
            _check("Arbitrages avec dossier et recommandation"),
            _check("Agenda des trois semaines revu"),
            _check("Engagements externes listés", False),
        ],
        "expected_output": "Dossier du point dirigeant",
    },
    "jalons_signaux": {
        "title": "Revoir les jalons et signaux faibles",
        "purpose": "Risques à trois semaines, dépendances activées, engagements nouveaux.",
        "frequency": F.WEEKLY,
        "weekdays": [2],
        "duration_minutes": 45,
        "checklist": [
            _check("Jalons à risque à trois semaines revus"),
            _check("Dépendances activées vérifiées"),
            _check("Vérification terrain faite", False),
        ],
        "expected_output": "Risques et actions correctives",
    },
    "boucler_semaine": {
        "title": "Boucler et préparer la semaine",
        "purpose": "Relevés diffusés, relances prêtes, dossiers à 48 h, rencontres avec suite.",
        "frequency": F.WEEKLY,
        "weekdays": [4],
        "duration_minutes": 30,
        "checklist": [
            _check("Relevés de la semaine diffusés"),
            _check("Relances prêtes"),
            _check("Dossiers des rendez-vous à 48 h prêts"),
            _check("Agenda suivant protégé", False),
        ],
        "expected_output": "Semaine suivante préparée",
    },
    "revue_portefeuille": {
        "title": "Revoir le portefeuille",
        "purpose": "Prochain jalon, porteur, risque, dépendances, capacité et repriorisation.",
        "frequency": F.MONTHLY,
        "month_days": [1],
        "duration_minutes": 90,
        "checklist": [
            _check("Chaque projet : prochain jalon, porteur et risque"),
            _check("Capacité et dépendances revues"),
            _check("Propositions de repriorisation", False),
        ],
        "expected_output": "Portefeuille revu et repriorisations proposées",
    },
    "boucler_decisions": {
        "title": "Boucler les décisions",
        "purpose": "Décisions faites, à l'heure, en retard ou caduques ; corrections, escalades.",
        "frequency": F.MONTHLY,
        "month_days": [25],
        "duration_minutes": 45,
        "checklist": [
            _check("Décisions en retard revues"),
            _check("Décisions caduques annulées formellement"),
            _check("Escalades préparées", False),
        ],
        "expected_output": "Registre des décisions à jour",
    },
    "sujets_sans_porteur": {
        "title": "Attribuer les sujets sans porteur",
        "purpose": "Inventaire, porteurs proposés et acceptés, sujets de plus de 30 jours.",
        "frequency": F.MONTHLY,
        "month_days": [15],
        "duration_minutes": 45,
        "checklist": [
            _check("Inventaire des sujets sans porteur"),
            _check("Sujets de plus de 30 jours attribués ou escaladés"),
        ],
        "expected_output": "Chaque sujet a un porteur accepté",
    },
    "synthese_execution": {
        "title": "Produire la synthèse d'exécution",
        "purpose": "Instantané daté, alertes, indicateurs et décisions attendues.",
        "frequency": F.MONTHLY,
        "month_days": [4],
        "duration_minutes": 60,
        "checklist": [
            _check("Indicateurs relevés"),
            _check("Synthèse diffusée avant le 5 du mois"),
        ],
        "expected_output": "Synthèse diffusée avant le 5",
    },
    "priorites_capacite": {
        "title": "Revoir les priorités et la capacité",
        "purpose": "Que confirmer, décaler, réduire ou arrêter ? Dépendances du trimestre.",
        "frequency": F.QUARTERLY,
        "month_days": [1],
        "duration_minutes": 120,
        "checklist": [
            _check("Portefeuille arbitré"),
            _check("Objectifs actualisés"),
        ],
        "expected_output": "Portefeuille arbitrable et objectifs actualisés",
    },
}
