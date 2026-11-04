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
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pilot_api.db import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class Role(enum.StrEnum):
    OWNER = "owner"
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


# Une tâche annulée est clôturée, au même titre qu'une tâche terminée (CDC §8).
CLOSED_TASK_STATUSES = {TaskStatus.DONE, TaskStatus.CANCELLED}


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
        ForeignKey("memberships.id", ondelete="SET NULL")
    )
    owner_label: Mapped[str | None] = mapped_column(String(120))

    situation: Mapped[str | None] = mapped_column(Text)
    situation_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_step: Mapped[str | None] = mapped_column(Text)
    decision_needed: Mapped[str | None] = mapped_column(Text)
    decision_maker: Mapped[str | None] = mapped_column(String(120))
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
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    deliverable: Mapped[str | None] = mapped_column(String(300))
    status: Mapped[TaskStatus] = mapped_column(_enum(TaskStatus, "task_status"))
    assignee_member_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("memberships.id", ondelete="SET NULL")
    )
    assignee_label: Mapped[str | None] = mapped_column(String(120))
    due_date: Mapped[date | None] = mapped_column(Date)
    due_certainty: Mapped[DateCertainty | None] = mapped_column(
        _enum(DateCertainty, "task_due_certainty")
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    version: Mapped[int] = mapped_column(Integer, default=1)

    assignee_member: Mapped[Membership | None] = relationship()


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

    uploaded_by: Mapped[User | None] = relationship()


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
    target_type: Mapped[str] = mapped_column(String(16))  # project | task
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
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
