"""Moteur de reconnaissance déterministe (CDC §10).

Il découpe le texte en passages, rattache chaque passage à un projet quand c'est sûr,
et lit les libellés explicites (statut, avancement, échéance…). Il ne devine pas :
- plusieurs projets possibles → candidats à départager, rien n'est choisi au hasard ;
- « 24 % de l'objectif commercial » n'est pas un avancement ;
- « sera terminé demain », « n'est pas terminé » ne donnent jamais le statut Terminé ;
- une date relative (« demain », « lundi prochain ») n'est jamais convertie ;
- deux valeurs différentes pour un même champ sont mises de côté ;
- un projet cité dans une prochaine étape ne change pas le projet du passage.
Le moteur est pur (aucun accès à la base) : il se teste seul.
"""

import re
import unicodedata
import uuid
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from pilot_api.models import ProjectStatus, RiskLevel

# ---------- Normalisation ----------

_QUOTES = str.maketrans({"’": "'", "‘": "'", "`": "'", " ": " ", " ": " "})


def fold(text: str) -> str:
    """Minuscules sans accents, même longueur que le texte d'origine (positions conservées)."""
    return "".join(unicodedata.normalize("NFKD", c)[0].lower() for c in text.translate(_QUOTES))


STOPWORDS = {
    "le", "la", "les", "l", "de", "des", "du", "d", "un", "une", "et", "en", "au", "aux",
    "a", "pour", "sur", "par", "the", "of", "and", "projet", "project", "concernant",
}  # fmt: skip
# Mots qui ne suffisent pas à reconnaître un projet à eux seuls.
WEAK_WORDS = {"point", "suivi", "mise", "jour", "compte", "rendu", "reunion", "cr", "note"}


def tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", fold(text))


def significant(words: list[str]) -> list[str]:
    return [w for w in words if w not in STOPWORDS]


# ---------- Entrées et sorties ----------


@dataclass
class ProjectInfo:
    id: uuid.UUID
    title: str
    # Éléments discriminants : filiale, ville, pays, édition, programme.
    hints: list[str] = field(default_factory=list)


@dataclass
class MemberInfo:
    id: uuid.UUID
    name: str
    email: str


@dataclass
class TextSource:
    label: str  # « Message » ou nom du fichier
    text: str
    filename: str | None = None


@dataclass
class Change:
    field: str
    value: Any  # valeur à enregistrer (texte, nombre, date ISO, identifiant…)
    display: str
    excerpt: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "value": self.value,
            "display": self.display,
            "excerpt": self.excerpt,
        }


@dataclass
class Draft:
    source_label: str
    excerpt: str
    target_id: uuid.UUID | None
    candidate_ids: list[uuid.UUID]
    changes: list[Change]
    issues: list[str]


@dataclass
class Analysis:
    drafts: list[Draft]
    notes: list[str]


# ---------- Libellés reconnus ----------

FIELD_LABELS: dict[str, list[str]] = {
    "status": ["statut", "etat", "status"],
    "progress": ["etat d'avancement", "taux d'avancement", "avancement", "progression"],
    "due_date": ["echeance", "date limite", "date butoir", "deadline"],
    "owner": [
        "responsable du suivi",
        "responsable",
        "chef de projet",
        "suivi par",
        "pilote",
        "porteur",
    ],
    "situation": ["point de situation", "situation", "commentaires", "commentaire", "resume"],
    "next_step": [
        "prochaines etapes",
        "prochaine etape",
        "prochaine action",
        "action suivante",
        "next step",
    ],
    "decision_needed": [
        "decision attendue",
        "decision a prendre",
        "arbitrage attendu",
        "arbitrage",
        "decision",
    ],
    "blocker": ["point bloquant", "bloque par", "blocages", "blocage"],
    "risk_level": ["niveau de risque", "vigilance", "risque"],
}
FIELD_NAMES = {
    "status": "Statut",
    "progress": "Avancement",
    "due_date": "Échéance",
    "owner": "Responsable du suivi",
    "situation": "Situation",
    "next_step": "Prochaine étape",
    "decision_needed": "Décision attendue",
    "risk_level": "Vigilance",
}
_LABEL_TO_FIELD = {label: name for name, labels in FIELD_LABELS.items() for label in labels}
_LABELS = sorted(_LABEL_TO_FIELD, key=len, reverse=True)
_ALT = "|".join(re.escape(label) for label in _LABELS)
# Un libellé ouvre la phrase ou suit une ponctuation ; il est suivi de « : », « = » ou d'un tiret.
LABEL_RE = re.compile(
    rf"(?:^|(?<=[\s,;.(•*\-]))({_ALT})(?:\s*\([^)]{{0,40}}\))?\s*(?::|=|\s[-–—]\s)\s*"
)
LABEL_ONLY_RE = re.compile(rf"^\s*({_ALT})\s*$")

STATUS_LABELS = {
    ProjectStatus.TO_FRAME: "À cadrer",
    ProjectStatus.TO_LAUNCH: "À lancer",
    ProjectStatus.PREPARING: "En préparation",
    ProjectStatus.IN_PROGRESS: "En cours",
    ProjectStatus.AWAITING_VALIDATION: "En attente de validation",
    ProjectStatus.BLOCKED: "Bloqué",
    ProjectStatus.SUSPENDED: "Suspendu",
    ProjectStatus.DONE: "Terminé",
    ProjectStatus.CANCELLED: "Annulé",
}
RISK_LABELS = {RiskLevel.WATCH: "À surveiller", RiskLevel.HIGH: "Élevé", None: "Aucune"}

# Ordre important : les expressions longues avant les courtes.
STATUS_WORDS: list[tuple[str, ProjectStatus]] = [
    (r"en attente de validation|attente de validation|en validation|a valider",
     ProjectStatus.AWAITING_VALIDATION),
    (r"en preparation|preparation", ProjectStatus.PREPARING),
    (r"en cours|en execution|demarre", ProjectStatus.IN_PROGRESS),
    (r"a lancer", ProjectStatus.TO_LAUNCH),
    (r"a cadrer|en cadrage|cadrage", ProjectStatus.TO_FRAME),
    (r"bloquee?s?", ProjectStatus.BLOCKED),
    (r"suspendue?s?|en pause|gelee?", ProjectStatus.SUSPENDED),
    (r"terminee?s?|achevee?s?|cloturee?s?|finie?s?|realisee?s?", ProjectStatus.DONE),
    (r"annulee?s?|abandonnee?s?", ProjectStatus.CANCELLED),
]  # fmt: skip
NEGATION_RE = re.compile(r"\b(pas|plus|non|jamais|ne|n'|aucun|aucune)\b|n'")
FUTURE_RE = re.compile(
    r"\b(sera|seront|serait|devrait|devraient|va etre|vont etre|prevue?s?|bientot|d'ici"
    r"|avant|apres|si|presque|quasi)\b"
)
# « 24 % de l'objectif » n'est pas un avancement du projet (CDC §10).
NOT_PROGRESS_RE = re.compile(
    r"objectif|cible|vente|chiffre|budget|\bca\b|taux de|conversion|commercial|remplissage"
    r"|inscri|participant|satisfaction|marge|part de marche|audience|frequentation"
)
RELATIVE_DATE_RE = re.compile(
    r"\b(demain|apres-demain|aujourd'hui|hier|lundi|mardi|mercredi|jeudi|vendredi|samedi"
    r"|dimanche|semaine|prochaine?|dans \d+|fin du mois|fin de mois|debut du mois|quinzaine"
    r"|asap|des que possible)\b"
)
MONTHS = {
    "janvier": 1, "janv": 1, "jan": 1, "fevrier": 2, "fevr": 2, "fev": 2, "mars": 3,
    "avril": 4, "avr": 4, "mai": 5, "juin": 6, "juillet": 7, "juil": 7, "aout": 8,
    "septembre": 9, "sept": 9, "sep": 9, "octobre": 10, "oct": 10, "novembre": 11, "nov": 11,
    "decembre": 12, "dec": 12,
}  # fmt: skip
_MONTH_ALT = "|".join(sorted(MONTHS, key=len, reverse=True))
DATE_PATTERNS = [
    (re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b"), "ymd"),
    (re.compile(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{4}|\d{2})\b"), "dmy"),
    (re.compile(rf"\b(1er|\d{{1,2}})\s+({_MONTH_ALT})\.?\s+(\d{{4}})\b"), "dMy"),
]
DAY_MONTH_NO_YEAR = re.compile(rf"\b(1er|\d{{1,2}})\s+({_MONTH_ALT})\b\.?(?!\s*\d)")

MAX_TEXT = 2000
MAX_EXCERPT = 1500
MAX_NARRATIVE = 600


# ---------- Découpage ----------

SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-ZÀ-ÖØ-Þ#•*\-–—])")
BULLET_RE = re.compile(r"^\s*(?:[#>]+|[-*•–—]|\d+[.)]|[a-z][.)])\s*", re.IGNORECASE)
HEAD_PREFIX_RE = re.compile(
    r"^(?:(?:pour|concernant|sur|cote|au sujet de|point sur|suivi)\s+)?"
    r"(?:(?:le|la|les|l')\s*)?(?:projet|evenement|programme)?\s*",
)
HEAD_SEPARATOR_RE = re.compile(r"\s[-–—]\s|\s*:\s|\s*[-–—]$|:$")


@dataclass
class Clause:
    text: str  # texte d'origine
    heading: bool  # ligne seule (titre) ou précédée d'un symbole de titre


def split_clauses(text: str) -> list[Clause]:
    clauses: list[Clause] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        is_heading = line.startswith("#")
        for sentence in SENTENCE_SPLIT.split(line):
            sentence = sentence.strip()
            if sentence:
                clauses.append(Clause(sentence, is_heading))
    return clauses


# ---------- Reconnaissance des projets ----------


class ProjectMatcher:
    def __init__(self, projects: list[ProjectInfo]) -> None:
        self.projects = projects
        self.words = {
            p.id: set(significant(tokens(p.title))) or set(tokens(p.title)) for p in projects
        }
        self.acronyms: dict[uuid.UUID, str] = {}
        for p in projects:
            alpha = [w for w in significant(tokens(p.title)) if w.isalpha()]
            if len(alpha) >= 2:
                self.acronyms[p.id] = "".join(w[0] for w in alpha)
        self.hints = {
            p.id: [set(significant(tokens(h))) for h in p.hints if significant(tokens(h))]
            for p in projects
        }

    def match(self, text: str) -> tuple[list[ProjectInfo], list[ProjectInfo]]:
        """Projets entièrement cités dans `text`, puis projets cités en partie."""
        words = set(significant(tokens(text)))
        if not words:
            return [], []
        full, partial = [], []
        for p in self.projects:
            title_words = self.words[p.id]
            if (title_words and title_words <= words) or self.acronyms.get(p.id) in words:
                full.append(p)
            else:
                shared = {w for w in title_words & words if w not in WEAK_WORDS and not w.isdigit()}
                if any(len(w) >= 4 for w in shared):
                    partial.append(p)
        # « Atlas Maroc » plutôt que « Atlas » quand les deux sont entièrement cités.
        full = [
            p
            for p in full
            if not any(q is not p and self.words[p.id] < self.words[q.id] for q in full)
        ]
        return full, partial

    def narrow(self, candidates: list[ProjectInfo], context: str) -> list[ProjectInfo]:
        """Départage par une filiale, une ville, un pays ou une édition cités dans le passage."""
        words = set(significant(tokens(context)))
        kept = [p for p in candidates if any(h <= words for h in self.hints[p.id])]
        return kept if kept else candidates


def _head(clause: str) -> tuple[str, str, bool] | None:
    """Sépare « Projet Atlas — Statut : en cours » en tête (« Atlas »), contenu et présence
    d'un séparateur. Renvoie None si la phrase commence par un libellé (« Statut : … »)."""
    text = BULLET_RE.sub("", clause).strip()
    folded = fold(text)
    sep = HEAD_SEPARATOR_RE.search(folded)
    if sep:
        head, rest = text[: sep.start()], text[sep.end() :]
    else:
        head, rest = text, ""
    head_folded = HEAD_PREFIX_RE.sub("", fold(head).strip()).strip()
    if not head_folded or LABEL_ONLY_RE.match(head_folded) or LABEL_RE.match(fold(head).strip()):
        return None
    if len(tokens(head_folded)) > 8:
        return None
    return head, rest.strip(), bool(sep)


@dataclass
class Segment:
    source: TextSource
    clauses: list[str]
    content: list[str]
    target: ProjectInfo | None = None
    candidates: list[ProjectInfo] = field(default_factory=list)
    identified: bool = False  # un projet (ou des candidats) a été cité en tête


def segment_source(source: TextSource, matcher: ProjectMatcher) -> list[Segment]:
    segments: list[Segment] = []
    current = Segment(source, [], [])
    for clause in split_clauses(source.text):
        head = _head(clause.text)
        full, partial = matcher.match(head[0]) if head else ([], [])
        if head and not (head[2] or clause.heading):
            # Phrase sans séparateur : seulement un nom de projet presque seul (« Atlas »),
            # jamais une phrase qui cite un projet en passant (« Orion doit d'abord livrer »).
            head_words = set(significant(tokens(head[0])))
            full = [p for p in full if len(matcher.words[p.id]) * 2 >= len(head_words)]
            partial = []
        elif head and len(significant(tokens(head[0]))) > 4:
            partial = []
        if head and (full or partial):
            segments.append(current)
            current = Segment(source, [clause.text], [head[1]] if head[1] else [], identified=True)
            context = clause.text
            if len(full) == 1:
                current.target = full[0]
            elif full:
                narrowed = matcher.narrow(full, context)
                if len(narrowed) == 1:
                    current.target = narrowed[0]
                else:
                    current.candidates = narrowed
            else:
                narrowed = matcher.narrow(partial, context)
                if len(narrowed) == 1 and len(partial) > 1:
                    current.target = narrowed[0]  # une ville ou une filiale a départagé
                else:
                    current.candidates = narrowed[:6]
        else:
            current.clauses.append(clause.text)
            current.content.append(clause.text)
    segments.append(current)
    return [s for s in segments if s.clauses]


# ---------- Lecture des champs ----------


def _clean_value(value: str) -> str:
    return value.strip().strip(" .;,").strip()


def labelled_values(clause: str) -> tuple[list[tuple[str, str]], str]:
    """[(champ, valeur)] lus dans la phrase, et le texte libre qui précède le premier libellé."""
    folded = fold(clause)
    matches = list(LABEL_RE.finditer(folded))
    if not matches:
        return [], clause
    found = []
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(clause)
        value = _clean_value(clause[m.end() : end])
        if value:
            found.append((_LABEL_TO_FIELD[m.group(1)], value))
    return found, clause[: matches[0].start()]


def read_status(value: str) -> tuple[ProjectStatus | None, str | None]:
    folded = fold(value)
    hits = []
    for pattern, status in STATUS_WORDS:
        m = re.search(rf"\b(?:{pattern})\b", folded)
        if m:
            hits.append((m.start(), status))
            folded = folded[: m.start()] + " " * (m.end() - m.start()) + folded[m.end() :]
    if not hits:
        return None, f"Statut « {value} » non reconnu : rien n'est proposé pour le statut."
    if len({s for _, s in hits}) > 1:
        return None, f"Statut « {value} » ambigu : rien n'est proposé pour le statut."
    if NEGATION_RE.search(fold(value)) or FUTURE_RE.search(fold(value)):
        return None, (f"« {value} » décrit un statut à venir ou nié : le statut n'est pas modifié.")
    return hits[0][1], None


def read_progress(value: str) -> tuple[int | None, str | None]:
    folded = fold(value)
    if NOT_PROGRESS_RE.search(folded):
        return None, (
            f"« {value} » mesure un objectif ou un résultat, pas l'avancement du projet : "
            "non repris."
        )
    if NEGATION_RE.search(folded) or FUTURE_RE.search(folded):
        return None, f"Avancement « {value} » conditionnel ou à venir : non repris."
    m = re.search(r"(\d{1,3})(?:[.,]\d+)?\s*(?:%|pour ?cent|pourcent)", folded)
    if m is None and re.fullmatch(r"\s*\d{1,3}\s*", folded):
        m = re.search(r"\d{1,3}", folded)
    if m is None:
        return None, f"Avancement « {value} » sans pourcentage lisible : non repris."
    number = int(m.group(1) if m.groups() else m.group(0))
    if number > 100:
        return None, f"Avancement « {value} » supérieur à 100 % : non repris."
    return number, None


def read_date(value: str) -> tuple[date | None, str | None]:
    folded = fold(value)
    found: list[date] = []
    for pattern, kind in DATE_PATTERNS:
        for m in pattern.finditer(folded):
            try:
                if kind == "ymd":
                    found.append(date(int(m.group(1)), int(m.group(2)), int(m.group(3))))
                elif kind == "dmy":
                    year = int(m.group(3))
                    year = year + 2000 if year < 100 else year
                    found.append(date(year, int(m.group(2)), int(m.group(1))))
                else:
                    day = 1 if m.group(1) == "1er" else int(m.group(1))
                    found.append(date(int(m.group(3)), MONTHS[m.group(2)], day))
            except ValueError:
                return None, f"Date « {value} » impossible : non reprise."
    if len(set(found)) == 1:
        return found[0], None
    if len(set(found)) > 1:
        return None, f"Plusieurs dates dans « {value} » : précisez l'échéance."
    if RELATIVE_DATE_RE.search(folded):
        return None, (
            f"Date relative « {value} » non convertie : indiquez une date précise "
            "(par exemple 20/11/2026)."
        )
    if DAY_MONTH_NO_YEAR.search(folded):
        return None, f"Année manquante dans « {value} » : indiquez la date complète."
    return None, f"Échéance « {value} » non reconnue : indiquez une date (20/11/2026)."


def read_risk(value: str) -> tuple[RiskLevel | None, bool, str | None]:
    folded = fold(value)
    if re.search(r"\b(eleve|elevee|fort|forte|haut|haute|critique|important)\b", folded):
        return RiskLevel.HIGH, True, None
    if re.search(r"\b(a surveiller|moyen|moyenne|modere|moderee|attention)\b", folded):
        return RiskLevel.WATCH, True, None
    if re.search(r"\b(faible|aucun|aucune|bas|basse|nul|nulle|rien)\b", folded):
        return None, True, None
    return None, False, f"Vigilance « {value} » non reconnue : non reprise."


def read_owner(value: str, members: list[MemberInfo]) -> tuple[dict[str, Any], str]:
    name = re.sub(r"\s*\(.*?\)\s*", " ", value).strip()[:120]
    wanted = " ".join(tokens(name))
    exact = [m for m in members if " ".join(tokens(m.name)) == wanted or fold(m.email) == wanted]
    if not exact and wanted:
        first = [
            m for m in members if tokens(m.name)[:1] == tokens(name)[:1] and len(tokens(name)) == 1
        ]
        exact = first if len(first) == 1 else []
    if len(exact) == 1:
        member = exact[0]
        return {"member_id": str(member.id), "label": None}, member.name
    return {"member_id": None, "label": name}, f"{name} (sans compte)"


# ---------- Analyse ----------


def _text(value: str) -> str:
    return value.strip()[:MAX_TEXT]


def _changes_for(
    segment: Segment, members: list[MemberInfo], allow_narrative: bool
) -> tuple[list[Change], list[str]]:
    collected: dict[str, list[Change]] = {}
    issues: list[str] = []
    narrative: list[str] = []
    blockers: list[tuple[str, str]] = []

    def add(name: str, value: Any, display: str, excerpt: str) -> None:
        collected.setdefault(name, []).append(Change(name, value, display, excerpt))

    for clause in segment.content:
        values, free = labelled_values(clause)
        if _clean_value(free):
            narrative.append(_clean_value(free))
        for name, value in values:
            if name == "status":
                status, issue = read_status(value)
                if issue:
                    issues.append(issue)
                elif status in (ProjectStatus.DONE, ProjectStatus.CANCELLED):
                    issues.append(
                        f"« {value} » : le passage à {STATUS_LABELS[status]} se fait depuis la "
                        "fiche du projet, car il demande un "
                        + ("bilan." if status == ProjectStatus.DONE else "motif.")
                    )
                else:
                    add(name, status.value, STATUS_LABELS[status], clause)
            elif name == "progress":
                number, issue = read_progress(value)
                if issue:
                    issues.append(issue)
                else:
                    add(name, number, f"{number} %", clause)
            elif name == "due_date":
                day, issue = read_date(value)
                if issue:
                    issues.append(issue)
                else:
                    add(name, day.isoformat(), day.strftime("%d/%m/%Y"), clause)
            elif name == "owner":
                person, display = read_owner(value, members)
                add(name, person, display, clause)
            elif name == "risk_level":
                level, ok, issue = read_risk(value)
                if not ok:
                    issues.append(issue)
                else:
                    add(name, level.value if level else None, RISK_LABELS[level], clause)
            elif name == "blocker":
                blockers.append((value, clause))
            else:
                add(name, _text(value), _text(value), clause)

    for value, clause in blockers:
        add("status", ProjectStatus.BLOCKED.value, STATUS_LABELS[ProjectStatus.BLOCKED], clause)
        if "situation" not in collected:
            add("situation", _text(f"Blocage : {value}"), _text(f"Blocage : {value}"), clause)
    # Information narrative gardée comme proposition de situation (CDC §10).
    if allow_narrative and narrative and "situation" not in collected:
        joined = " ".join(narrative)
        if len(joined) > MAX_NARRATIVE:
            issues.append(
                "Texte libre trop long pour devenir la situation : écrivez « Situation : … » "
                "pour la proposer."
            )
        elif len(joined) >= 3:
            add("situation", _text(joined), _text(joined), joined)

    changes: list[Change] = []
    for name, items in collected.items():
        distinct = {repr(c.value) for c in items}
        if len(distinct) > 1:
            shown = " », « ".join(dict.fromkeys(c.display for c in items))
            issues.append(
                f"Deux valeurs différentes pour {FIELD_NAMES[name]} (« {shown} ») : "
                "rien n'est proposé pour ce champ, précisez-le."
            )
            continue
        changes.append(items[0])
    order = list(FIELD_NAMES)
    changes.sort(key=lambda c: order.index(c.field))
    return changes, list(dict.fromkeys(issues))


def analyse(
    sources: list[TextSource], projects: list[ProjectInfo], members: list[MemberInfo]
) -> Analysis:
    matcher = ProjectMatcher(projects)
    titles = {p.id: p.title for p in projects}
    drafts: list[Draft] = []
    notes: list[str] = []
    for source in sources:
        segments = segment_source(source, matcher)
        cites_projects = any(s.identified for s in segments)
        # Sans projet cité dans le texte, le nom du fichier peut désigner le projet.
        file_target: ProjectInfo | None = None
        file_candidates: list[ProjectInfo] = []
        if source.filename:
            full, partial = matcher.match(re.sub(r"[_.\-]+", " ", source.filename))
            if len(full) == 1:
                file_target = full[0]
            else:
                file_candidates = (full or partial)[:6]
        merged: dict[Any, Draft] = {}
        for index, segment in enumerate(segments):
            if not segment.identified:
                if cites_projects:
                    continue  # préambule (titre, date…) d'un texte qui cite ses projets
                segment.target = file_target
                segment.candidates = [] if file_target else file_candidates
            # Un texte libre ne devient une situation que pour un projet reconnu.
            changes, issues = _changes_for(segment, members, segment.target is not None)
            key = segment.target.id if segment.target else ("passage", index)
            excerpt = "\n".join(segment.clauses)
            draft = merged.get(key)
            if draft is None:
                merged[key] = Draft(
                    source_label=source.label,
                    excerpt=excerpt[:MAX_EXCERPT],
                    target_id=segment.target.id if segment.target else None,
                    candidate_ids=[p.id for p in segment.candidates],
                    changes=changes,
                    issues=issues,
                )
                continue
            draft.excerpt = (draft.excerpt + "\n" + excerpt)[:MAX_EXCERPT]
            known = {c.field: c for c in draft.changes}
            for change in changes:
                other = known.get(change.field)
                if other is None:
                    draft.changes.append(change)
                elif other.value != change.value:
                    draft.changes.remove(other)
                    draft.issues.append(
                        f"Deux valeurs différentes pour {FIELD_NAMES[change.field]} "
                        f"(« {other.display} », « {change.display} ») : rien n'est proposé "
                        "pour ce champ, précisez-le."
                    )
            draft.issues.extend(i for i in issues if i not in draft.issues)

        for draft in merged.values():
            name = titles[draft.target_id] if draft.target_id else None
            if not draft.changes:
                # Rien à valider : on dit pourquoi, sans créer de proposition vide.
                where = f"« {name} »" if name else source.label
                if draft.issues:
                    notes.extend(f"{where} : {issue}" for issue in draft.issues)
                elif name:
                    notes.append(f"{where} : projet cité, mais aucune information reconnue.")
                else:
                    notes.append(
                        f"{source.label} : texte reçu, mais aucun projet ni libellé reconnu "
                        "(statut, avancement, échéance, prochaine étape…)."
                    )
                continue
            if not draft.target_id and not draft.candidate_ids:
                draft.issues.insert(
                    0,
                    "Projet non identifié : ajoutez le nom du projet, une filiale ou un autre "
                    "mot-clé distinctif, ou choisissez le projet.",
                )
            elif not draft.target_id:
                draft.issues.insert(
                    0, "Plusieurs projets possibles : choisissez le bon projet avant de valider."
                )
            drafts.append(draft)
    return Analysis(drafts, notes)
