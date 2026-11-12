"""Règles des champs personnalisés (étape F4, cahier V2 CHP01–CHP04).

Contrôle d'une valeur selon le type du champ, conversion lors d'un changement de type (jamais
d'effacement silencieux : une valeur non convertible bloque le changement) et calcul des champs
calculés (lecture seule ; un dénominateur nul donne « non calculable », pas 100 %).
"""

import re
import uuid
from datetime import date
from typing import Any

from pilot_api.models import CustomField, CustomFieldType

T = CustomFieldType
NUMERIC = {T.NUMBER, T.PERCENT, T.AMOUNT}
TEXTS = {T.TEXT, T.LONG_TEXT}
DEFAULT_MAX = {T.TEXT: 200, T.LONG_TEXT: 5000}
URL_RE = re.compile(r"^https?://[^\s]{3,}$", re.IGNORECASE)
FORMULA_OPS = {"difference", "sum", "ratio"}


class InvalidValue(ValueError):
    """Valeur refusée ; le message est affiché tel quel à la personne."""


def active_option_ids(field: CustomField) -> set[str]:
    return {o["id"] for o in field.options or [] if o.get("active", True)}


def option_ids(field: CustomField) -> set[str]:
    return {o["id"] for o in field.options or []}


def _number(field: CustomField, value: Any) -> float | int:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise InvalidValue(f"« {field.label} » attend un nombre.")
    cfg = field.config or {}
    low = cfg.get("min", 0 if field.type == T.PERCENT else None)
    high = cfg.get("max", 100 if field.type == T.PERCENT else None)
    if low is not None and value < low:
        raise InvalidValue(f"« {field.label} » doit être au moins {low}.")
    if high is not None and value > high:
        raise InvalidValue(f"« {field.label} » doit être au plus {high}.")
    return value


def clean_value(
    field: CustomField,
    value: Any,
    member_ids: set[uuid.UUID],
    previous: Any = None,
) -> Any:
    """Renvoie la valeur à enregistrer (None = vide), ou lève InvalidValue.

    `previous` : une option devenue inactive reste acceptée si elle était déjà choisie, pour
    qu'enregistrer la fiche sans y toucher ne soit pas refusé."""
    if field.type == T.COMPUTED:
        raise InvalidValue(f"« {field.label} » est calculé : il ne se saisit pas.")
    if value is None or value == "" or value == []:
        return None
    if field.type in TEXTS:
        if not isinstance(value, str):
            raise InvalidValue(f"« {field.label} » attend un texte.")
        value = value.strip()
        limit = (field.config or {}).get("max_length") or DEFAULT_MAX[field.type]
        if len(value) > limit:
            raise InvalidValue(f"« {field.label} » : {limit} caractères au plus.")
        return value or None
    if field.type in NUMERIC:
        return _number(field, value)
    if field.type == T.DATE:
        try:
            return date.fromisoformat(str(value)).isoformat()
        except ValueError:
            raise InvalidValue(f"« {field.label} » attend une date.") from None
    if field.type == T.BOOLEAN:
        if not isinstance(value, bool):
            raise InvalidValue(f"« {field.label} » attend oui ou non.")
        return value
    if field.type == T.URL:
        if not isinstance(value, str) or not URL_RE.match(value.strip()) or len(value) > 500:
            raise InvalidValue(f"« {field.label} » attend un lien qui commence par https://.")
        return value.strip()
    if field.type == T.PERSON:
        try:
            member = uuid.UUID(str(value))
        except ValueError:
            raise InvalidValue(f"« {field.label} » attend un membre de l'espace.") from None
        if member not in member_ids:
            raise InvalidValue(f"« {field.label} » : cette personne n'est pas membre de l'espace.")
        return str(member)
    allowed = active_option_ids(field)
    kept = set(previous if isinstance(previous, list) else [previous] if previous else [])
    if field.type == T.CHOICE:
        if not isinstance(value, str) or (value not in allowed and value not in kept):
            raise InvalidValue(f"« {field.label} » : choix inconnu ou retiré.")
        return value
    if field.type == T.MULTI_CHOICE:
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise InvalidValue(f"« {field.label} » attend une liste de choix.")
        unknown = [v for v in value if v not in allowed and v not in kept]
        if unknown:
            raise InvalidValue(f"« {field.label} » : choix inconnu ou retiré.")
        return list(dict.fromkeys(value)) or None
    raise InvalidValue(f"Type de champ inconnu : {field.type}.")


def display(field: CustomField, value: Any, people: dict[str, str] | None = None) -> str:
    """Valeur lisible (exports, assistant, conversion vers du texte)."""
    if value is None:
        return ""
    labels = {o["id"]: o["label"] for o in field.options or []}
    if field.type == T.CHOICE:
        return labels.get(value, value)
    if field.type == T.MULTI_CHOICE:
        return ", ".join(labels.get(v, v) for v in value)
    if field.type == T.BOOLEAN:
        return "oui" if value else "non"
    if field.type == T.PERSON:
        return (people or {}).get(value, "membre retiré")
    if field.type in NUMERIC or field.type == T.COMPUTED:
        cfg = field.config or {}
        unit = "%" if field.type == T.PERCENT else cfg.get("currency") or cfg.get("unit") or ""
        text = f"{value:g}" if isinstance(value, float) else str(value)
        return f"{text} {unit}".strip()
    return str(value)


def convert(old: CustomField, new: CustomField, value: Any) -> tuple[bool, Any]:
    """Conversion d'une valeur existante vers le nouveau type. (False, …) = non convertible."""
    if value is None:
        return True, None
    target = new.type
    try:
        if target in TEXTS:
            text = display(old, value) if old.type not in TEXTS else value
            return True, clean_value(new, text, set())
        if target in NUMERIC:
            if old.type in NUMERIC:
                return True, clean_value(new, value, set())
            if old.type in TEXTS:
                number = float(str(value).replace(",", ".").replace(" ", ""))
                return True, clean_value(new, int(number) if number.is_integer() else number, set())
            return False, value
        if target == T.DATE and old.type in TEXTS:
            return True, clean_value(new, value, set())
        if target == T.URL and old.type in TEXTS:
            return True, clean_value(new, value, set())
        if target == T.MULTI_CHOICE and old.type == T.CHOICE:
            return True, clean_value(new, [value], set(), previous=[value])
        if target == T.CHOICE and old.type == T.MULTI_CHOICE:
            if len(value) == 1:
                return True, clean_value(new, value[0], set(), previous=value[0])
            return False, value
        if target == old.type:
            return True, value
    except (InvalidValue, ValueError):
        return False, value
    return False, value


def compute(field: CustomField, values: dict[str, Any]) -> float | None:
    """Champ calculé : a − b, a + b ou a / b × 100 (en %). `values` est indexé par identifiant de
    champ. Une donnée manquante ou un dénominateur nul donne None (« non calculable »)."""
    formula = (field.config or {}).get("formula") or {}
    a, b = values.get(formula.get("a")), values.get(formula.get("b"))
    if not isinstance(a, int | float) or not isinstance(b, int | float):
        return None
    if formula.get("op") == "difference":
        result = a - b
    elif formula.get("op") == "sum":
        result = a + b
    elif formula.get("op") == "ratio":
        if b == 0:
            return None
        result = a / b * 100
    else:
        return None
    return round(result, 2)
