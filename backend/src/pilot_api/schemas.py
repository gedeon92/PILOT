import uuid
from datetime import datetime
from typing import Annotated, Literal
from zoneinfo import available_timezones

from pydantic import BaseModel, EmailStr, Field, StringConstraints, field_validator

from pilot_api.models import MembershipStatus, Role

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Password = Annotated[str, StringConstraints(min_length=10, max_length=128)]
InvitableRole = Literal[Role.READER, Role.CONTRIBUTOR]


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
