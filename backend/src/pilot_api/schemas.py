import uuid
from datetime import date, datetime
from typing import Annotated, Literal
from zoneinfo import available_timezones

from pydantic import BaseModel, EmailStr, Field, HttpUrl, StringConstraints, field_validator

from pilot_api.models import (
    CLOSED_PROJECT_STATUSES,
    DateCertainty,
    MembershipStatus,
    ProjectKind,
    ProjectRole,
    ProjectStatus,
    RiskLevel,
    Role,
    TaskPriority,
    TaskRecurrence,
    TaskStatus,
)

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Password = Annotated[str, StringConstraints(min_length=10, max_length=128)]
# Lot C : un invité extérieur ne voit que les projets auxquels on l'ajoute.
InvitableRole = Literal[Role.READER, Role.CONTRIBUTOR, Role.GUEST]


class RegisterIn(BaseModel):
    email: EmailStr
    password: Password
    display_name: Name


class LoginIn(BaseModel):
    email: EmailStr
    password: Annotated[str, StringConstraints(min_length=1, max_length=128)]


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str


class SpaceSummary(BaseModel):
    id: uuid.UUID
    name: str
    role: Role


class MeOut(BaseModel):
    user: UserOut
    spaces: list[SpaceSummary]


class _TimezoneMixin(BaseModel):
    @field_validator("timezone", check_fields=False)
    @classmethod
    def _known_timezone(cls, value: str | None) -> str | None:
        if value is not None and value not in available_timezones():
            raise ValueError("Fuseau horaire inconnu.")
        return value


class SpaceCreate(_TimezoneMixin):
    name: Name
    timezone: str = "UTC"


class SpaceUpdate(_TimezoneMixin):
    version: int
    name: Name | None = None
    timezone: str | None = None


class SpaceOut(BaseModel):
    id: uuid.UUID
    name: str
    timezone: str
    version: int
    role: Role


class MemberOut(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str | None
    role: Role
    status: MembershipStatus
    is_me: bool
    joined_at: datetime | None
    invite_expires_at: datetime | None
    version: int


class InvitationCreate(BaseModel):
    email: EmailStr
    role: InvitableRole


class InvitationLink(BaseModel):
    """Le jeton n'est montré qu'une fois : PILOT n'en garde que l'empreinte."""

    member: MemberOut
    token: str
    # L'invitation est aussi envoyée par e-mail quand c'est possible ; sinon, le lien est à
    # transmettre à la main et `email_note` dit pourquoi.
    emailed: bool = False
    email_note: str | None = None


class MemberUpdate(BaseModel):
    version: int
    role: InvitableRole


class InvitationToken(BaseModel):
    token: Annotated[str, Field(min_length=20, max_length=128)]


class InvitationInfo(BaseModel):
    space_name: str
    role: Role
    email: str
    invited_by: str | None
    expired: bool
    email_matches: bool


Color = Literal["orange", "blue", "violet", "green", "teal", "pink", "gray"]
Description = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]
Country = Annotated[str, StringConstraints(strip_whitespace=True, max_length=80)]
Emoji = Annotated[str, StringConstraints(strip_whitespace=True, max_length=16)]


class _CatalogUpdate(BaseModel):
    """Seuls les champs envoyés sont modifiés ; `archived` archive ou restaure l'élément."""

    version: int
    name: Name | None = None
    archived: bool | None = None


class PortfolioCreate(BaseModel):
    name: Name
    description: Description | None = None
    color: Color = "orange"
    emoji: Emoji | None = None


class PortfolioUpdate(_CatalogUpdate):
    description: Description | None = None
    color: Color | None = None
    emoji: Emoji | None = None


class PortfolioOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    color: str
    emoji: str | None = None
    archived: bool
    version: int


class EntityCreate(BaseModel):
    name: Name
    country: Country | None = None


class EntityUpdate(_CatalogUpdate):
    country: Country | None = None


class EntityOut(BaseModel):
    id: uuid.UUID
    name: str
    country: str | None
    archived: bool
    version: int


class ProjectTypeCreate(BaseModel):
    name: Name
    kind: ProjectKind = ProjectKind.STANDARD


class ProjectTypeUpdate(_CatalogUpdate):
    kind: ProjectKind | None = None


class ProjectTypeOut(BaseModel):
    id: uuid.UUID
    name: str
    kind: ProjectKind
    archived: bool
    version: int


class ProgramCreate(BaseModel):
    name: Name
    description: Description | None = None


class ProgramUpdate(_CatalogUpdate):
    description: Description | None = None


class ProgramOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    archived: bool
    version: int


# ---------- Projets et tâches ----------

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
LongText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=5000)]
Label = Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)]
Progress = Annotated[int, Field(ge=0, le=100)]


class PersonRef(BaseModel):
    """Responsable : un membre de l'espace (`member_id`) ou un simple nom saisi."""

    member_id: uuid.UUID | None
    name: str | None
    has_account: bool


class RefOut(BaseModel):
    id: uuid.UUID
    name: str


class PortfolioRef(RefOut):
    color: str
    emoji: str | None = None


class PersonIn(BaseModel):
    """Un membre de l'espace (`member_id`) ou un nom libre (`label`)."""

    member_id: uuid.UUID | None = None
    label: Label | None = None


class DecisionOption(BaseModel):
    label: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    consequence: Description | None = None


class ProjectTypeRef(RefOut):
    kind: ProjectKind


class EventIn(BaseModel):
    """Détails d'un événement ; seuls les champs envoyés sont modifiés."""

    venue: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] | None = None
    audience: Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)] | None = None
    expected_attendance: Annotated[int, Field(ge=0, le=10_000_000)] | None = None
    program_id: uuid.UUID | None = None
    edition_label: (
        Annotated[str, StringConstraints(strip_whitespace=True, max_length=40)] | None
    ) = None


class EventOut(BaseModel):
    venue: str | None
    audience: str | None
    expected_attendance: int | None
    program: RefOut | None
    edition_label: str | None
    # Fin du suivi après l'événement (J+15) ; vide tant que la date n'est pas connue.
    follow_up_until: date | None


class _ProjectFields(BaseModel):
    """Champs modifiables d'un projet. Seuls les champs envoyés sont pris en compte ;
    `null` efface une valeur (une information inconnue reste vide)."""

    entity_id: uuid.UUID | None = None
    project_type_id: uuid.UUID | None = None
    owner_member_id: uuid.UUID | None = None
    owner_label: Label | None = None
    # Liste complète des contributeurs : elle remplace la précédente (vingt au plus).
    contributors: Annotated[list[PersonIn], Field(max_length=20)] | None = None
    origin: LongText | None = None
    situation: LongText | None = None
    next_step: LongText | None = None
    decision_needed: LongText | None = None
    decision_maker: Label | None = None
    decision_options: Annotated[list[DecisionOption], Field(max_length=3)] | None = None
    objective: LongText | None = None
    deliverables: LongText | None = None
    progress: Progress | None = None
    risk_level: RiskLevel | None = None
    risk_note: LongText | None = None
    start_date: date | None = None
    end_date: date | None = None
    due_date: date | None = None
    date_certainty: DateCertainty | None = None
    window_start: date | None = None
    window_end: date | None = None
    country: Country | None = None
    city: Label | None = None
    external_url: HttpUrl | None = None
    event: EventIn | None = None


class ProjectCreate(_ProjectFields):
    title: Title
    portfolio_id: uuid.UUID
    status: ProjectStatus = ProjectStatus.TO_FRAME
    client_request_id: uuid.UUID | None = None
    # Modèle de projet : ses tâches sont copiées dans le nouveau projet.
    template_id: uuid.UUID | None = None

    @field_validator("status")
    @classmethod
    def _not_closed(cls, value: ProjectStatus) -> ProjectStatus:
        if value in CLOSED_PROJECT_STATUSES:
            raise ValueError("Un projet ne peut pas être créé déjà terminé ou annulé.")
        return value


class ProjectUpdate(_ProjectFields):
    version: int
    title: Title | None = None
    portfolio_id: uuid.UUID | None = None


class ProjectStatusChange(BaseModel):
    version: int
    status: ProjectStatus
    outcome: LongText | None = None
    reason: LongText | None = None


class ProjectOut(BaseModel):
    id: uuid.UUID
    title: str
    status: ProjectStatus
    portfolio: PortfolioRef
    entity: RefOut | None
    project_type: ProjectTypeRef | None
    owner: PersonRef
    contributors: list[PersonRef] = []
    event: EventOut | None
    origin: str | None = None
    situation: str | None
    situation_updated_at: datetime | None
    # « manual » (fiche), « update » (boîte de mise à jour) ou « import » ; vide si inconnu.
    situation_source: str | None = None
    situation_source_label: str | None = None
    situation_updated_by: str | None = None
    next_step: str | None
    decision_needed: str | None
    decision_maker: str | None
    decision_options: list[DecisionOption] = []
    objective: str | None
    deliverables: str | None
    progress: int | None
    risk_level: RiskLevel | None
    risk_note: str | None
    start_date: date | None
    end_date: date | None
    due_date: date | None
    date_certainty: DateCertainty | None
    window_start: date | None
    window_end: date | None
    country: str | None
    city: str | None
    external_url: str | None
    outcome: str | None
    cancel_reason: str | None
    open_tasks: int
    late_tasks: int
    created_at: datetime
    updated_at: datetime
    version: int
    # Lot C : projet privé, et rôle de la personne connectée sur ce projet
    # (owner, contributor ou reader) pour afficher ou non les boutons de modification.
    private: bool = False
    my_role: str | None = None


class _TaskFields(BaseModel):
    deliverable: Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)] | None = (
        None
    )
    assignee_member_id: uuid.UUID | None = None
    assignee_label: Label | None = None
    due_date: date | None = None
    due_certainty: DateCertainty | None = None
    # Répétition : chaque jour, semaine, mois ou année (exige une échéance).
    recurrence: TaskRecurrence | None = None
    # Étape F1 : section du projet, priorité et date de début (facultatives).
    section_id: uuid.UUID | None = None
    priority: TaskPriority | None = None
    start_date: date | None = None


class TaskCreate(_TaskFields):
    title: Title
    status: TaskStatus = TaskStatus.TODO


class SpaceTaskCreate(TaskCreate):
    """Tâche créée hors d'une fiche : le projet est obligatoire (décision du 9 nov. 2026)."""

    project_id: uuid.UUID


class TaskUpdate(_TaskFields):
    version: int
    title: Title | None = None
    status: TaskStatus | None = None
    # Motif d'un report (échéance repoussée) : gardé au journal avec l'échéance d'origine.
    postpone_reason: LongText | None = None


class TaskOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID | None
    title: str
    deliverable: str | None
    status: TaskStatus
    assignee: PersonRef
    due_date: date | None
    due_certainty: DateCertainty | None
    late: bool
    closed_at: datetime | None
    version: int
    # Sous-tâches, commentaires et dépendances (lot A) : valeurs par défaut pour rester
    # compatible avec les écrans qui ne les connaissent pas.
    parent_id: uuid.UUID | None = None
    subtasks_total: int = 0
    subtasks_done: int = 0
    comments_count: int = 0
    # Nombre de tâches encore ouvertes dont celle-ci attend la fin.
    waiting_on: int = 0
    # Tâche répétée, et la suivante une fois créée ; nombre de fichiers joints.
    recurrence: TaskRecurrence | None = None
    next_task_id: uuid.UUID | None = None
    documents_count: int = 0
    section_id: uuid.UUID | None = None
    priority: TaskPriority | None = None
    start_date: date | None = None
    # Première échéance, gardée dès le premier report ; nombre de reports.
    original_due_date: date | None = None
    postpone_count: int = 0


class TaskRef(BaseModel):
    id: uuid.UUID
    title: str
    status: TaskStatus
    project_id: uuid.UUID | None
    project_title: str | None


CommentBody = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)
]


class CommentCreate(BaseModel):
    body: CommentBody
    # Membres cités avec @nom (choisis dans la liste) : ils sont prévenus.
    mentions: list[uuid.UUID] = Field(default_factory=list, max_length=20)


class MentionRef(BaseModel):
    member_id: uuid.UUID
    name: str


class CommentOut(BaseModel):
    id: uuid.UUID
    author_name: str
    body: str
    mentions: list[MentionRef]
    created_at: datetime
    can_delete: bool


class FollowerOut(BaseModel):
    user_id: uuid.UUID
    name: str


class DependencyCreate(BaseModel):
    depends_on_id: uuid.UUID


class TaskDetail(BaseModel):
    task: TaskOut
    project_title: str | None
    parent: TaskRef | None
    subtasks: list[TaskOut]
    depends_on: list[TaskRef]
    blocking: list[TaskRef]
    comments: list[CommentOut]
    followers: list[FollowerOut]
    following: bool
    # Lot C : la personne connectée peut-elle modifier cette tâche (rôle sur son projet) ?
    can_write: bool = True
    # Projet terminé ou annulé : plus de sous-tâche ni de nouvelle tâche (audit M6).
    project_closed: bool = False
    # Fichiers joints à la tâche (versions actuelles, non retirés).
    documents: list["DocumentOut"] = Field(default_factory=list)


class ProjectLinkCreate(BaseModel):
    project_id: uuid.UUID
    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] | None = None


class LinkedProject(BaseModel):
    id: uuid.UUID
    title: str
    status: ProjectStatus
    portfolio: PortfolioRef


class ProjectLinkOut(BaseModel):
    id: uuid.UUID
    project: LinkedProject
    note: str | None
    created_at: datetime


class HistoryEntry(BaseModel):
    id: uuid.UUID
    action: str
    target_type: str
    actor_name: str | None
    created_at: datetime
    before: dict | None
    after: dict | None


# ---------- Documents ----------


class DocumentOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    project_title: str
    filename: str
    content_type: str
    size_bytes: int
    uploaded_by: str | None
    created_at: datetime
    archived: bool
    # Numéro de version (1 pour le premier envoi) ; une version remplacée garde sa date.
    revision: int = 1
    replaced_at: datetime | None = None
    # Fichier joint à une tâche du projet (facultatif).
    task_id: uuid.UUID | None = None
    task_title: str | None = None


# ---------- Modèles de projet ----------


class TemplateCreate(BaseModel):
    """Enregistre les tâches d'un projet comme modèle."""

    project_id: uuid.UUID
    name: Name
    description: LongText | None = None


class TemplateUpdate(BaseModel):
    version: int
    name: Name | None = None
    description: LongText | None = None


class TemplateTaskOut(BaseModel):
    title: str
    offset_days: int | None
    is_subtask: bool


class TemplateOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    tasks_count: int
    tasks: list[TemplateTaskOut]
    # Étape F1 : sections recréées dans le nouveau projet.
    sections: list[str] = []
    created_at: datetime
    version: int


# ---------- Alertes ----------


class AlertOut(BaseModel):
    id: uuid.UUID
    rule: str
    rule_label: str
    target_type: str
    target_id: uuid.UUID | None = None
    project_id: uuid.UUID | None
    alert_date: date
    title: str
    detail: str
    read: bool


class AlertList(BaseModel):
    unread: int
    items: list[AlertOut]


class AlertPreferenceOut(BaseModel):
    disabled_rules: list[str]
    email_digest: bool
    digest_hour: int
    email_available: bool
    rules: dict[str, str]


class AlertPreferenceIn(BaseModel):
    disabled_rules: list[str]
    email_digest: bool
    digest_hour: Annotated[int, Field(ge=0, le=23)]


class TestEmailResult(BaseModel):
    sent: bool
    message: str


# ---------- Mon compte ----------


class ProfileUpdate(BaseModel):
    display_name: Name


class PasswordChange(BaseModel):
    current_password: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    new_password: Password


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: Annotated[str, Field(min_length=20, max_length=128)]
    new_password: Password


class EmailChangeRequest(BaseModel):
    new_email: EmailStr
    password: Annotated[str, StringConstraints(min_length=1, max_length=128)]


class EmailChangeSent(BaseModel):
    sent_to: str
    expires_hours: int


# ---------- Boîte de mise à jour ----------


class UpdateSourceOut(BaseModel):
    id: uuid.UUID
    filename: str
    size_bytes: int
    extraction: str  # read | empty | unsupported | too_large | too_long | failed
    note: str | None
    chars: int


class ProposalProjectRef(BaseModel):
    id: uuid.UUID
    title: str
    detail: str | None  # portefeuille, filiale, ville : pour départager


class ProposalChangeOut(BaseModel):
    field: str
    label: str
    current: str | None
    proposed: str
    excerpt: str
    unchanged: bool  # la valeur proposée est déjà celle du projet


class ProposalOut(BaseModel):
    id: uuid.UUID
    # to_clarify | to_validate | conflict | applied | discarded
    state: str
    project: ProposalProjectRef | None
    candidates: list[ProposalProjectRef]
    source_label: str
    excerpt: str
    changes: list[ProposalChangeOut]
    issues: list[str]
    base_version: int | None
    applied_fields: list[str]
    decided_by: str | None
    decided_at: datetime | None
    discard_reason: str | None


class UpdateRequestOut(BaseModel):
    id: uuid.UUID
    created_at: datetime
    author_name: str | None
    mine: bool
    visibility: str  # private | shared
    message: str | None
    sources: list[UpdateSourceOut]
    proposals: list[ProposalOut]
    notes: list[str]


class UpdateRequestPatch(BaseModel):
    visibility: Literal["private", "shared"]


class ProposalTarget(BaseModel):
    project_id: uuid.UUID


class ProposalApply(BaseModel):
    fields: Annotated[list[str], Field(min_length=1, max_length=20)]
    base_version: int


class ProposalDiscard(BaseModel):
    reason: Annotated[str | None, StringConstraints(max_length=300)] = None


class SourceShare(BaseModel):
    project_id: uuid.UUID


# ---------- Export et import ----------


class ImportResult(BaseModel):
    space_id: uuid.UUID
    space_name: str
    already_imported: bool
    counts: dict[str, int]
    warnings: list[str]


# ---------- Accès à un projet (lot C) ----------


class ProjectAccessMemberIn(BaseModel):
    member_id: uuid.UUID
    role: ProjectRole


class ProjectAccessIn(BaseModel):
    private: bool
    members: list[ProjectAccessMemberIn] = Field(default_factory=list, max_length=200)


class ProjectAccessMember(BaseModel):
    member_id: uuid.UUID
    name: str
    email: str
    space_role: Role
    role: ProjectRole
    has_account: bool


class ProjectAccessOut(BaseModel):
    private: bool
    members: list[ProjectAccessMember]


TaskDetail.model_rebuild()  # DocumentOut est défini plus bas


# ---------- Assistant IA (lot E) ----------


class AiStatusOut(BaseModel):
    # Clé Anthropic configurée sur le serveur.
    available: bool
    # Allumé par un propriétaire pour cet espace.
    enabled: bool
    can_toggle: bool
    daily_limit: int
    used_today: int


class AiToggle(BaseModel):
    enabled: bool


class AiMessageIn(BaseModel):
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]


class AiChange(BaseModel):
    field: str
    before: str
    after: str


class AiActionOut(BaseModel):
    id: uuid.UUID
    kind: str
    summary: str
    changes: list[AiChange]
    state: Literal["pending", "applied", "rejected", "conflict", "failed"]
    result: str | None
    # Pour ouvrir la fiche concernée.
    project_id: uuid.UUID | None = None
    task_id: uuid.UUID | None = None


class AiTurnOut(BaseModel):
    role: Literal["user", "assistant"]
    text: str
    at: datetime | None = None
    error: bool = False
    actions: list[AiActionOut] = []


class AiConversationSummary(BaseModel):
    id: uuid.UUID
    title: str
    status: Literal["idle", "thinking"]
    updated_at: datetime


class AiConversationOut(AiConversationSummary):
    turns: list[AiTurnOut]


# ---------- Sections d'un projet (étape F1) ----------

SectionTitle = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)
]


class SectionCreate(BaseModel):
    title: SectionTitle
    description: LongText | None = None


class SectionUpdate(BaseModel):
    version: int
    title: SectionTitle | None = None
    description: LongText | None = None


class SectionOrder(BaseModel):
    # Identifiants des sections actives, dans le nouvel ordre.
    ids: Annotated[list[uuid.UUID], Field(max_length=100)]


class SectionArchive(BaseModel):
    # Où ranger les tâches ouvertes : une autre section, ou « sans section » (null).
    # `keep_tasks` les laisse dans la section archivée (elles restent visibles à part).
    move_open_tasks_to: uuid.UUID | None = None
    keep_tasks: bool = False


class SectionOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    title: str
    description: str | None
    position: int
    archived: bool
    version: int
