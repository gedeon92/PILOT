import enum
import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import false as sa_false
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pilot_api.db import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class Role(enum.StrEnum):
    OWNER = "owner"
    CONTRIBUTOR = "contributor"
    READER = "reader"
    # Invité extérieur (lot C) : ne voit que les projets auxquels on l'a ajouté.
    GUEST = "guest"


class ProjectRole(enum.StrEnum):
    """Rôle d'une personne sur un projet précis (lot C) ; précise le rôle de l'espace."""

    CONTRIBUTOR = "contributor"
    READER = "reader"


class MembershipStatus(enum.StrEnum):
    INVITED = "invited"
    ACTIVE = "active"


def _enum(cls: type[enum.StrEnum], name: str) -> Enum:
    # Texte contrôlé plutôt qu'un type PostgreSQL : ajouter une valeur ne demande pas de migration.
    return Enum(
        cls, name=name, native_enum=False, length=20, values_callable=lambda e: [m.value for m in e]
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Toujours enregistrée en minuscules (voir normalize_email).
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuthSession(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Seule l'empreinte du jeton est stockée : une fuite de la base ne donne pas accès aux comptes.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Space(Base):
    __tablename__ = "spaces"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120))
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    version: Mapped[int] = mapped_column(Integer, default=1)
    # Export dont l'espace est issu : réimporter le même fichier ne le duplique pas.
    imported_from: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    # Lot E : assistant IA, éteint par défaut ; seul un propriétaire l'allume.
    ai_enabled: Mapped[bool] = mapped_column(default=False, server_default=sa_false())


class Membership(Base):
    """Droit d'une personne sur un espace : une invitation en attente ou un membre actif."""

    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint("space_id", "user_id", name="uq_memberships_space_user"),
        UniqueConstraint("space_id", "email", name="uq_memberships_space_email"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    space_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("spaces.id", ondelete="CASCADE"), index=True
    )
    # Vide tant que l'invitation n'a pas été acceptée ; ensuite, le droit suit ce compte.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    email: Mapped[str] = mapped_column(String(320))
    role: Mapped[Role] = mapped_column(_enum(Role, "membership_role"))
    status: Mapped[MembershipStatus] = mapped_column(_enum(MembershipStatus, "membership_status"))
    invite_token_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    invite_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    invited_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    joined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, default=1)

    space: Mapped[Space] = relationship()
    user: Mapped[User | None] = relationship(foreign_keys=[user_id])


class LoginFailure(Base):
    """Échec de connexion, compté par adresse (empreinte) pour freiner les essais en rafale."""

    __tablename__ = "login_failures"
    __table_args__ = (Index("ix_login_failures_email_created", "email_hash", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_log_space_created", "space_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    space_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("spaces.id", ondelete="SET NULL"))
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(64))
    target_type: Mapped[str] = mapped_column(String(32))
    target_id: Mapped[str | None] = mapped_column(String(64))
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class _CatalogItem:
    """Élément de structure d'un espace : jamais supprimé, seulement archivé,
    pour que les projets qui y sont rattachés restent cohérents."""

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    space_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("spaces.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    version: Mapped[int] = mapped_column(Integer, default=1)


class Portfolio(_CatalogItem, Base):
    __tablename__ = "portfolios"
    __table_args__ = (UniqueConstraint("space_id", "name", name="uq_portfolios_space_name"),)

    description: Mapped[str | None] = mapped_column(String(500))
    color: Mapped[str] = mapped_column(String(20), default="orange")
    # Repère visuel facultatif (CDC §13) : complète le nom, ne le remplace jamais.
    emoji: Mapped[str | None] = mapped_column(String(16))


class Entity(_CatalogItem, Base):
    """Filiale ou entité responsable d'un projet (distincte du portefeuille, CDC §5)."""

    __tablename__ = "entities"
    __table_args__ = (UniqueConstraint("space_id", "name", name="uq_entities_space_name"),)

    country: Mapped[str | None] = mapped_column(String(80))


class Program(_CatalogItem, Base):
    """Événement récurrent (ex. salon annuel) ; chacune de ses éditions est un projet."""

    __tablename__ = "programs"
    __table_args__ = (UniqueConstraint("space_id", "name", name="uq_programs_space_name"),)

    description: Mapped[str | None] = mapped_column(String(500))


class ProjectKind(enum.StrEnum):
    STANDARD = "standard"
    # Un projet de cette nature recevra les détails d'événement (phase 3B).
    EVENT = "event"


class ProjectType(_CatalogItem, Base):
    __tablename__ = "project_types"
    __table_args__ = (UniqueConstraint("space_id", "name", name="uq_project_types_space_name"),)

    # Le comportement dépend de la nature, pas du nom : renommer « Événement » ne change rien.
    kind: Mapped[ProjectKind] = mapped_column(
        _enum(ProjectKind, "project_kind"), default=ProjectKind.STANDARD
    )


# Proposés à la création d'un espace ; le rôle Propriétaire peut les renommer ou les archiver.
DEFAULT_PROJECT_TYPES = (
    ("Événement", ProjectKind.EVENT),
    ("Produit", ProjectKind.STANDARD),
    ("Mission", ProjectKind.STANDARD),
    ("Autre", ProjectKind.STANDARD),
)


class ProjectStatus(enum.StrEnum):
    TO_FRAME = "to_frame"
    TO_LAUNCH = "to_launch"
    PREPARING = "preparing"
    IN_PROGRESS = "in_progress"
    AWAITING_VALIDATION = "awaiting_validation"
    BLOCKED = "blocked"
    SUSPENDED = "suspended"
    DONE = "done"
    CANCELLED = "cancelled"


CLOSED_PROJECT_STATUSES = {ProjectStatus.DONE, ProjectStatus.CANCELLED}


class TaskStatus(enum.StrEnum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    CANCELLED = "cancelled"
    # Étape F1 (cahier V2, TCH03) : sujet à préciser, tâche bloquée, tâche soumise à validation.
    TO_QUALIFY = "to_qualify"
    BLOCKED = "blocked"
    AWAITING_VALIDATION = "awaiting_validation"


class TaskPriority(enum.StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


# Une tâche annulée est clôturée, au même titre qu'une tâche terminée (CDC §8).
CLOSED_TASK_STATUSES = {TaskStatus.DONE, TaskStatus.CANCELLED}


class TaskRecurrence(enum.StrEnum):
    """Rythme d'une tâche répétée : quand elle est terminée, la suivante est créée."""

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"


class DateCertainty(enum.StrEnum):
    PROPOSED = "proposed"
    ANNOUNCED = "announced"
    CONFIRMED = "confirmed"


class RiskLevel(enum.StrEnum):
    WATCH = "watch"
    HIGH = "high"


class Project(Base):
    """Fiche projet (dictionnaire des champs, CDC §21). Une information inconnue reste vide."""

    __tablename__ = "projects"
    __table_args__ = (
        UniqueConstraint("space_id", "client_request_id", name="uq_projects_client_request"),
        CheckConstraint(
            "progress IS NULL OR progress BETWEEN 0 AND 100", name="ck_projects_progress"
        ),
        Index("ix_projects_space_status", "space_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    space_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("spaces.id", ondelete="CASCADE"), index=True
    )
    portfolio_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("portfolios.id"), index=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("entities.id"), index=True)
    project_type_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("project_types.id"))
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[ProjectStatus] = mapped_column(_enum(ProjectStatus, "project_status"))

    # Responsable du suivi : un membre de l'espace ou un simple nom (sans compte ni droit).
    owner_member_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("memberships.id", ondelete="SET NULL"), index=True
    )
    owner_label: Mapped[str | None] = mapped_column(String(120))

    # Origine du besoin (CDC §6, étape 1) : qui l'a exprimé, lors de quelle réunion…
    origin: Mapped[str | None] = mapped_column(Text)
    situation: Mapped[str | None] = mapped_column(Text)
    situation_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Source et fraîcheur (CDC §21) : d'où vient la dernière situation, et qui l'a enregistrée.
    situation_source: Mapped[str | None] = mapped_column(String(20))  # manual | update | import
    situation_source_label: Mapped[str | None] = mapped_column(String(255))
    situation_updated_by: Mapped[str | None] = mapped_column(String(120))
    next_step: Mapped[str | None] = mapped_column(Text)
    decision_needed: Mapped[str | None] = mapped_column(Text)
    decision_maker: Mapped[str | None] = mapped_column(String(120))
    # Options d'arbitrage (CDC §7) : [{"label": …, "consequence": …}], trois au plus.
    decision_options: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    objective: Mapped[str | None] = mapped_column(Text)
    deliverables: Mapped[str | None] = mapped_column(Text)
    # Mesure documentée et facultative : jamais déduite d'une date (CDC §2).
    progress: Mapped[int | None] = mapped_column(Integer)
    risk_level: Mapped[RiskLevel | None] = mapped_column(_enum(RiskLevel, "risk_level"))
    risk_note: Mapped[str | None] = mapped_column(Text)

    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    due_date: Mapped[date | None] = mapped_column(Date)
    date_certainty: Mapped[DateCertainty | None] = mapped_column(
        _enum(DateCertainty, "date_certainty")
    )
    # Période dans laquelle les jours restent à choisir (≠ durée du projet, CDC §12).
    window_start: Mapped[date | None] = mapped_column(Date)
    window_end: Mapped[date | None] = mapped_column(Date)

    country: Mapped[str | None] = mapped_column(String(80))
    city: Mapped[str | None] = mapped_column(String(80))
    external_url: Mapped[str | None] = mapped_column(String(500))

    outcome: Mapped[str | None] = mapped_column(Text)  # bilan, exigé pour « Terminé »
    cancel_reason: Mapped[str | None] = mapped_column(Text)  # motif, exigé pour « Annulé »

    # Identifiant envoyé par le navigateur : « Réessayer » ne crée pas un second projet.
    client_request_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    version: Mapped[int] = mapped_column(Integer, default=1)

    portfolio: Mapped[Portfolio] = relationship()
    entity: Mapped[Entity | None] = relationship()
    project_type: Mapped[ProjectType | None] = relationship()
    owner_member: Mapped[Membership | None] = relationship()
    event_details: Mapped["EventDetails | None"] = relationship(
        back_populates="project", uselist=False, cascade="all, delete-orphan"
    )
    # Projet privé (lot C) : visible seulement par ses membres et par les propriétaires.
    private: Mapped[bool] = mapped_column(default=False, server_default=sa_false())
    contributors: Mapped[list["ProjectContributor"]] = relationship(
        cascade="all, delete-orphan", order_by="ProjectContributor.position"
    )


class ProjectMember(Base):
    """Accès d'une personne à un projet précis (lot C) : rôle propre à ce projet, obligatoire
    pour voir un projet privé ou pour un invité extérieur."""

    __tablename__ = "project_members"
    __table_args__ = (UniqueConstraint("project_id", "member_id", name="uq_project_members"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    member_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("memberships.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[ProjectRole] = mapped_column(_enum(ProjectRole, "project_member_role"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProjectContributor(Base):
    """Personne qui participe au projet, distincte du responsable du suivi (CDC §21).
    Comme le responsable : un membre de l'espace ou un simple nom, sans droit supplémentaire."""

    __tablename__ = "project_contributors"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    member_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("memberships.id", ondelete="SET NULL"), index=True
    )
    label: Mapped[str | None] = mapped_column(String(120))
    position: Mapped[int] = mapped_column(Integer, default=0)

    member: Mapped[Membership | None] = relationship()


class ProjectLink(Base):
    """Lien entre deux projets (CDC §5), sans dupliquer l'un dans l'autre. Le lien est
    symétrique : il est stocké une seule fois, du plus petit identifiant vers le plus grand."""

    __tablename__ = "project_links"
    __table_args__ = (
        UniqueConstraint("project_a_id", "project_b_id", name="uq_project_links_pair"),
        CheckConstraint("project_a_id < project_b_id", name="ck_project_links_order"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    space_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("spaces.id", ondelete="CASCADE"), index=True
    )
    project_a_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    project_b_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    note: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EventDetails(Base):
    """Informations propres aux événements, stockées à part pour ne pas les imposer
    aux autres projets (CDC §21). Les dates restent celles du projet."""

    __tablename__ = "event_details"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    venue: Mapped[str | None] = mapped_column(String(200))
    audience: Mapped[str | None] = mapped_column(String(300))
    expected_attendance: Mapped[int | None] = mapped_column(Integer)
    program_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("programs.id"), index=True)
    edition_label: Mapped[str | None] = mapped_column(String(40))

    project: Mapped[Project] = relationship(back_populates="event_details")
    program: Mapped[Program | None] = relationship()


# Durée du suivi après un événement : relances, exploitation, bilan (CDC §6).
EVENT_FOLLOW_UP_DAYS = 15


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    space_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("spaces.id", ondelete="CASCADE"), index=True
    )
    # Obligatoire depuis le 9 nov. 2026 : les anciennes tâches sans projet ont été rangées dans un
    # projet « Suivi général » (de même pour un ancien export, à l'import).
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    deliverable: Mapped[str | None] = mapped_column(String(300))
    status: Mapped[TaskStatus] = mapped_column(_enum(TaskStatus, "task_status"))
    assignee_member_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("memberships.id", ondelete="SET NULL"), index=True
    )
    assignee_label: Mapped[str | None] = mapped_column(String(120))
    due_date: Mapped[date | None] = mapped_column(Date)
    due_certainty: Mapped[DateCertainty | None] = mapped_column(
        _enum(DateCertainty, "task_due_certainty")
    )
    # Sous-tâche : rattachée à une tâche du même projet (un seul niveau).
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE", name="fk_tasks_parent_id_tasks"), index=True
    )
    # Tâche répétée : à sa clôture (Terminée), la suivante est créée et notée dans `next_task_id`
    # (une seule fois, même si la tâche est rouverte puis terminée de nouveau).
    recurrence: Mapped[TaskRecurrence | None] = mapped_column(
        _enum(TaskRecurrence, "task_recurrence")
    )
    next_task_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL", name="fk_tasks_next_task_id_tasks")
    )
    # Étape F1 : section du projet (facultative), priorité, date de début, et reports :
    # la première échéance est gardée dans `original_due_date` dès le premier report.
    section_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("project_sections.id", ondelete="SET NULL", name="fk_tasks_section_id_sections"),
        index=True,
    )
    priority: Mapped[TaskPriority | None] = mapped_column(_enum(TaskPriority, "task_priority"))
    start_date: Mapped[date | None] = mapped_column(Date)
    original_due_date: Mapped[date | None] = mapped_column(Date)
    postpone_count: Mapped[int | None] = mapped_column(Integer)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    version: Mapped[int] = mapped_column(Integer, default=1)

    assignee_member: Mapped[Membership | None] = relationship(foreign_keys=[assignee_member_id])


class MilestoneState(enum.StrEnum):
    PLANNED = "planned"
    REACHED = "reached"
    MISSED = "missed"
    CANCELLED = "cancelled"


class Milestone(Base):
    """Jalon (cahier V2, TCH04) : un résultat de passage daté, pas une tâche longue. Il a un
    porteur, une date engagée, un critère, un état et des tâches dont il dépend. Un report garde
    la première date ; après deux reports, une revue de cadrage est exigée (CAP01)."""

    __tablename__ = "milestones"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    space_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("spaces.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    section_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("project_sections.id", ondelete="SET NULL", name="fk_milestones_section_id")
    )
    title: Mapped[str] = mapped_column(String(200))
    criterion: Mapped[str | None] = mapped_column(Text)
    owner_member_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("memberships.id", ondelete="SET NULL")
    )
    owner_label: Mapped[str | None] = mapped_column(String(120))
    due_date: Mapped[date] = mapped_column(Date)
    original_due_date: Mapped[date | None] = mapped_column(Date)
    postpone_count: Mapped[int] = mapped_column(Integer, default=0)
    # Jalon déclaré critique (pas de chemin critique calculé : CAP04).
    critical: Mapped[bool] = mapped_column(default=False, server_default=sa_false())
    state: Mapped[MilestoneState] = mapped_column(_enum(MilestoneState, "milestone_state"))
    # Preuve d'atteinte, ou motif d'un jalon manqué ou annulé.
    close_note: Mapped[str | None] = mapped_column(Text)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Revue de cadrage faite avant le troisième report.
    reframe_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    version: Mapped[int] = mapped_column(Integer, default=1)

    owner_member: Mapped[Membership | None] = relationship()


class MilestoneTask(Base):
    """Tâche dont dépend un jalon (même projet)."""

    __tablename__ = "milestone_tasks"
    __table_args__ = (UniqueConstraint("milestone_id", "task_id", name="uq_milestone_tasks"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    milestone_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("milestones.id", ondelete="CASCADE"), index=True
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), index=True
    )


class ProjectSection(Base):
    """Section d'un projet (cahier V2, STR02) : organise les tâches, n'est ni un statut ni une
    phase. Archiver une section la retire de la vue active sans rien supprimer (STR04)."""

    __tablename__ = "project_sections"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    space_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("spaces.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer, default=0)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    version: Mapped[int] = mapped_column(Integer, default=1)


class TaskComment(Base):
    """Commentaire sur une tâche. Le nom de l'auteur est gardé en copie (lisible après un
    départ) ; `mentions` liste les membres cités avec @nom, prévenus dans leurs alertes."""

    __tablename__ = "task_comments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    space_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("spaces.id", ondelete="CASCADE"), index=True
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), index=True
    )
    author_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    author_name: Mapped[str] = mapped_column(String(120))
    body: Mapped[str] = mapped_column(Text)
    mentions: Mapped[list[str]] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TaskFollower(Base):
    """Personne abonnée à une tâche : prévenue des commentaires et des changements."""

    __tablename__ = "task_followers"
    __table_args__ = (UniqueConstraint("task_id", "user_id", name="uq_task_followers"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TaskDependency(Base):
    """`task_id` attend la fin de `depends_on_id` (terminée ou annulée)."""

    __tablename__ = "task_dependencies"
    __table_args__ = (
        UniqueConstraint("task_id", "depends_on_id", name="uq_task_dependencies"),
        CheckConstraint("task_id <> depends_on_id", name="ck_task_dependencies_self"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    space_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("spaces.id", ondelete="CASCADE"), index=True
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), index=True
    )
    depends_on_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Document(Base):
    """Pièce du dossier d'un projet. Le contenu est stocké à part (voir `storage`),
    sous une clé technique indépendante du nom du fichier (CDC §11)."""

    __tablename__ = "documents"
    __table_args__ = (Index("ix_documents_project", "project_id", "archived_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    space_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("spaces.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    # Fichier joint à une tâche (facultatif) : il reste aussi dans le dossier du projet.
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL", name="fk_documents_task_id_tasks"), index=True
    )
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(120))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), unique=True)
    uploaded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # Pas de suppression définitive : un document retiré reste dans la base et au journal.
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Versions : un remplacement crée une nouvelle fiche qui pointe vers la précédente ;
    # l'ancienne est gardée (téléchargeable) avec sa date de remplacement.
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    previous_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), index=True
    )
    replaced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    uploaded_by: Mapped[User | None] = relationship()


class ProjectTemplate(Base):
    """Modèle de projet : une liste de tâches prêtes à l'emploi, copiée à la création d'un
    projet. `tasks` : [{"ref", "title", "deliverable", "offset_days", "parent", "waits_for",
    "recurrence", "assignee_member_id", "assignee_label"}]. `offset_days` compte les jours
    depuis la date de début du projet (négatif = avant)."""

    __tablename__ = "project_templates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    space_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("spaces.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    tasks: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    # Étape F1 : titres des sections, dans l'ordre (les tâches citent leur section par son titre).
    sections: Mapped[list[str] | None] = mapped_column(JSONB)
    # Étape F2 : jalons [{"title", "criterion", "offset_days", "section", "critical", "tasks"}].
    milestones: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    version: Mapped[int] = mapped_column(Integer, default=1)


class AiConversation(Base):
    """Conversation privée d'une personne avec l'assistant IA (lot E).

    `history` : messages échangés avec l'API d'Anthropic, conservés tels quels (on y ajoute
    seulement). `turns` : ce qui s'affiche à l'écran, [{"role", "text", "action_ids", "at"}].
    `status` : « idle », ou « thinking » pendant que l'assistant prépare sa réponse."""

    __tablename__ = "ai_conversations"
    __table_args__ = (Index("ix_ai_conversations_space_user", "space_id", "user_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    space_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("spaces.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(120))
    history: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    turns: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    status: Mapped[str] = mapped_column(String(16), default="idle")
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AiActionState(enum.StrEnum):
    PENDING = "pending"
    APPLIED = "applied"
    REJECTED = "rejected"
    # La fiche a changé depuis la proposition : rien n'est appliqué.
    CONFLICT = "conflict"
    FAILED = "failed"


class AiAction(Base):
    """Changement proposé par l'assistant. Rien n'est appliqué sans le clic de la personne,
    et l'application passe par les mêmes contrôles de droits que l'écran."""

    __tablename__ = "ai_actions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ai_conversations.id", ondelete="CASCADE"), index=True
    )
    space_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("spaces.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(40))
    target_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    # Version de la fiche vue au moment de la proposition (conflit si elle a changé).
    base_version: Mapped[int | None] = mapped_column(Integer)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    summary: Mapped[str] = mapped_column(Text)
    # Lignes « champ : actuel → proposé » affichées avant validation.
    changes: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    state: Mapped[AiActionState] = mapped_column(_enum(AiActionState, "ai_action_state"))
    result: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AiUsage(Base):
    """Une question posée à l'assistant, pour la limite par jour et le suivi des coûts."""

    __tablename__ = "ai_usage"
    __table_args__ = (Index("ix_ai_usage_space_at", "space_id", "at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    space_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("spaces.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)


class StoredFile(Base):
    """Contenu des fichiers pendant la phase de test (stockage dans PostgreSQL)."""

    __tablename__ = "stored_files"

    key: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    data: Mapped[bytes] = mapped_column(LargeBinary)


class AlertRule(enum.StrEnum):
    DUE_SOON = "due_soon"
    OVERDUE = "overdue"
    BLOCKED = "blocked"
    DECISION_PENDING = "decision_pending"
    STALE = "stale"
    MISSING_INFO = "missing_info"
    PROPOSAL_PENDING = "proposal_pending"
    # Notifications déclenchées par un événement (CDC §16), distinctes des rappels calculés.
    MENTION = "mention"
    TASK_ACTIVITY = "task_activity"
    # Étape F2 (cahier V2, CAP) : jalon à risque dans les trois semaines ; jalon reporté deux
    # fois, qui demande une revue de cadrage avant toute nouvelle date.
    MILESTONE_AT_RISK = "milestone_at_risk"
    MILESTONE_REFRAME = "milestone_reframe"


class Alert(Base):
    """Rappel adressé à une personne. Unique par personne, règle, objet et jour (pas de doublon)."""

    __tablename__ = "alerts"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "rule", "target_id", "alert_date", name="uq_alerts_user_rule_target_day"
        ),
        Index("ix_alerts_user_space_date", "user_id", "space_id", "alert_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    space_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("spaces.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    rule: Mapped[AlertRule] = mapped_column(_enum(AlertRule, "alert_rule"))
    target_type: Mapped[str] = mapped_column(String(16))  # project | task | proposal | milestone
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    # Vide pour une proposition dont le projet reste à préciser.
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    # Jour de l'alerte dans le fuseau de l'espace.
    alert_date: Mapped[date] = mapped_column(Date)
    title: Mapped[str] = mapped_column(String(200))
    detail: Mapped[str] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AlertPreference(Base):
    __tablename__ = "alert_preferences"
    __table_args__ = (UniqueConstraint("user_id", "space_id", name="uq_alert_preferences"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    space_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("spaces.id", ondelete="CASCADE"))
    disabled_rules: Mapped[list[str]] = mapped_column(JSONB, default=list)
    email_digest: Mapped[bool] = mapped_column(default=True)
    digest_hour: Mapped[int] = mapped_column(Integer, default=7)
    # Dernier récapitulatif envoyé (jour de l'espace) : un seul envoi par jour.
    last_digest_date: Mapped[date | None] = mapped_column(Date)


class EmailChange(Base):
    """Demande de changement d'adresse : appliquée seulement quand le lien envoyé
    à la nouvelle adresse est ouvert (preuve que la boîte appartient à la personne)."""

    __tablename__ = "email_changes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    new_email: Mapped[str] = mapped_column(String(320))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PasswordReset(Base):
    """Lien « mot de passe oublié » : à usage unique, valable peu de temps. Seule l'empreinte
    du jeton est gardée ; le jeton lui-même n'existe que dans l'e-mail."""

    __tablename__ = "password_resets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


# ---------- Boîte de mise à jour (CDC §9, §10, §11) ----------


class UpdateVisibility(enum.StrEnum):
    PRIVATE = "private"  # visible de son auteur seulement
    SHARED = "shared"  # visible des contributeurs et propriétaires de l'espace


class ExtractionStatus(enum.StrEnum):
    READ = "read"
    EMPTY = "empty"  # aucun texte lisible (PDF scanné, image dans un PDF…)
    UNSUPPORTED = "unsupported"  # format non lu (image, archive…)
    TOO_LARGE = "too_large"  # au-delà de la taille lue
    TOO_LONG = "too_long"  # trop de pages ou de caractères
    FAILED = "failed"  # fichier illisible ou abîmé


class ProposalState(enum.StrEnum):
    TO_CLARIFY = "to_clarify"  # À préciser : projet ou valeur incertains
    TO_VALIDATE = "to_validate"  # À valider
    APPLIED = "applied"  # Appliquée
    DISCARDED = "discarded"  # Écartée


OPEN_PROPOSAL_STATES = {ProposalState.TO_CLARIFY, ProposalState.TO_VALIDATE}


class UpdateRequest(Base):
    """Une demande de mise à jour : un message et/ou des fichiers déposés dans la boîte.
    La déposer ne modifie aucun projet : elle produit des propositions à valider."""

    __tablename__ = "update_requests"
    __table_args__ = (
        UniqueConstraint("space_id", "client_request_id", name="uq_update_requests_client"),
        Index("ix_update_requests_space_created", "space_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    space_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("spaces.id", ondelete="CASCADE"))
    author_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    message: Mapped[str | None] = mapped_column(Text)
    visibility: Mapped[UpdateVisibility] = mapped_column(
        _enum(UpdateVisibility, "update_visibility")
    )
    # Ce qui n'a pas pu être rattaché à un projet ou lu (messages de fin de parcours).
    notes: Mapped[list[str]] = mapped_column(JSONB, default=list)
    client_request_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    author: Mapped[User | None] = relationship()
    sources: Mapped[list["UpdateSource"]] = relationship(
        back_populates="request", order_by="UpdateSource.position"
    )
    proposals: Mapped[list["Proposal"]] = relationship(
        back_populates="request", order_by="Proposal.position"
    )


class UpdateSource(Base):
    """Fichier déposé dans une demande : source d'analyse, distincte du dossier partagé
    du projet. Il est conservé même si son texte ne peut pas être lu."""

    __tablename__ = "update_sources"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("update_requests.id", ondelete="CASCADE"), index=True
    )
    space_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("spaces.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer, default=0)
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(120))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), unique=True)
    extraction: Mapped[ExtractionStatus] = mapped_column(
        _enum(ExtractionStatus, "extraction_status")
    )
    extraction_note: Mapped[str | None] = mapped_column(String(300))
    extracted_chars: Mapped[int] = mapped_column(Integer, default=0)

    request: Mapped[UpdateRequest] = relationship(back_populates="sources")


class Proposal(Base):
    """Proposition de modification d'un projet, issue d'un passage de la demande.
    `changes` : [{field, value, display, excerpt}] ; `before` : valeurs lues à la préparation ;
    `base_version` : version du projet à la préparation (une autre version bloque l'application)."""

    __tablename__ = "proposals"
    __table_args__ = (Index("ix_proposals_space_state", "space_id", "state"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("update_requests.id", ondelete="CASCADE"), index=True
    )
    space_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("spaces.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer, default=0)
    state: Mapped[ProposalState] = mapped_column(_enum(ProposalState, "proposal_state"))
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    # Projets possibles quand le passage ne permet pas de conclure.
    candidate_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)
    source_label: Mapped[str] = mapped_column(String(255))  # « Message » ou nom du fichier
    excerpt: Mapped[str] = mapped_column(Text)
    changes: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    issues: Mapped[list[str]] = mapped_column(JSONB, default=list)
    before: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    base_version: Mapped[int | None] = mapped_column(Integer)
    applied_fields: Mapped[list[str]] = mapped_column(JSONB, default=list)
    decided_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    discard_reason: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    request: Mapped[UpdateRequest] = relationship(back_populates="proposals")
    project: Mapped[Project | None] = relationship()
    decided_by: Mapped[User | None] = relationship()
