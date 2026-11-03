"""Routes communes aux éléments de structure d'un espace :
portefeuilles, filiales et types de projets.

Tous les membres consultent ; seul le rôle Propriétaire crée, modifie et archive (CDC §4, §5).
Il n'y a pas de suppression : un élément archivé disparaît des choix mais garde ses projets.
"""

import unicodedata
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from pilot_api.audit import record
from pilot_api.deps import CurrentMembership, DbSession, OwnerMembership
from pilot_api.models import Entity, Portfolio, Program, ProjectType, utcnow
from pilot_api.schemas import (
    EntityCreate,
    EntityOut,
    EntityUpdate,
    PortfolioCreate,
    PortfolioOut,
    PortfolioUpdate,
    ProgramCreate,
    ProgramOut,
    ProgramUpdate,
    ProjectTypeCreate,
    ProjectTypeOut,
    ProjectTypeUpdate,
)

# Champs toujours renseignés : jamais remplacés par une valeur vide.
REQUIRED_FIELDS = {"color", "kind"}


def sort_key(name: str) -> str:
    """Ordre alphabétique français : « Événement » se range avec les E, pas après le Z."""
    decomposed = unicodedata.normalize("NFKD", name.casefold())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def catalog_router(
    *,
    path: str,
    model: type[Portfolio | Entity | ProjectType | Program],
    create_schema: type[BaseModel],
    update_schema: type[BaseModel],
    out_schema: type[BaseModel],
    target_type: str,
    label: str,
) -> APIRouter:
    router = APIRouter(prefix=f"/api/spaces/{{space_id}}/{path}", tags=["structure"])
    fields = [name for name in create_schema.model_fields if name != "name"]

    def to_out(item: Any) -> Any:
        data = {name: getattr(item, name) for name in out_schema.model_fields if name != "archived"}
        return out_schema(**data, archived=item.archived_at is not None)

    def snapshot(item: Any) -> dict[str, Any]:
        data = {name: getattr(item, name) for name in ["name", *fields]}
        return {**data, "archived": item.archived_at is not None}

    def ensure_unique(db: Session, space_id: uuid.UUID, name: str, exclude: uuid.UUID | None):
        query = select(model.id).where(
            model.space_id == space_id, func.lower(model.name) == name.lower()
        )
        if exclude is not None:
            query = query.where(model.id != exclude)
        if db.scalar(query) is not None:
            raise HTTPException(409, f"{label} « {name} » existe déjà, éventuellement archivé.")

    def get_item(db: Session, space_id: uuid.UUID, item_id: uuid.UUID) -> Any:
        item = db.scalar(select(model).where(model.id == item_id, model.space_id == space_id))
        if item is None:
            raise HTTPException(404, f"{label} introuvable.")
        return item

    @router.get("", response_model=list[out_schema])
    def list_items(membership: CurrentMembership, db: DbSession, include_archived: bool = False):
        query = select(model).where(model.space_id == membership.space_id)
        if not include_archived:
            query = query.where(model.archived_at.is_(None))
        items = sorted(
            db.scalars(query), key=lambda i: (i.archived_at is not None, sort_key(i.name))
        )
        return [to_out(item) for item in items]

    @router.post("", status_code=201, response_model=out_schema)
    def create_item(body: create_schema, membership: OwnerMembership, db: DbSession):  # type: ignore[valid-type]
        ensure_unique(db, membership.space_id, body.name, exclude=None)
        values = {
            name: getattr(body, name) if name in REQUIRED_FIELDS else getattr(body, name) or None
            for name in fields
        }
        item = model(space_id=membership.space_id, name=body.name, **values)
        db.add(item)
        db.flush()
        record(
            db,
            action=f"{target_type}.created",
            actor_id=membership.user_id,
            space_id=membership.space_id,
            target_type=target_type,
            target_id=item.id,
            after=snapshot(item),
        )
        db.commit()
        return to_out(item)

    @router.patch("/{item_id}", response_model=out_schema)
    def update_item(
        item_id: uuid.UUID,
        body: update_schema,  # type: ignore[valid-type]
        membership: OwnerMembership,
        db: DbSession,
    ):
        item = get_item(db, membership.space_id, item_id)
        if item.version != body.version:
            raise HTTPException(
                409, "Cet élément a été modifié entre-temps. Rechargez la page avant de réessayer."
            )
        before = snapshot(item)
        sent = body.model_fields_set
        if "name" in sent and body.name is not None:
            ensure_unique(db, membership.space_id, body.name, exclude=item.id)
            item.name = body.name
        for name in fields:
            if name in sent:
                value = getattr(body, name)
                if name in REQUIRED_FIELDS and value is None:
                    continue  # champ obligatoire : « null » ne l'efface pas
                setattr(item, name, value or None)
        if "archived" in sent and body.archived is not None:
            if body.archived and item.archived_at is None:
                item.archived_at = utcnow()
            elif not body.archived:
                item.archived_at = None

        after = snapshot(item)
        if after != before:
            item.version += 1
            if before["archived"] != after["archived"]:
                action = "archived" if after["archived"] else "restored"
            else:
                action = "updated"
            record(
                db,
                action=f"{target_type}.{action}",
                actor_id=membership.user_id,
                space_id=membership.space_id,
                target_type=target_type,
                target_id=item.id,
                before=before,
                after=after,
            )
            db.commit()
        return to_out(item)

    return router


portfolios = catalog_router(
    path="portfolios",
    model=Portfolio,
    create_schema=PortfolioCreate,
    update_schema=PortfolioUpdate,
    out_schema=PortfolioOut,
    target_type="portfolio",
    label="Le portefeuille",
)
entities = catalog_router(
    path="entities",
    model=Entity,
    create_schema=EntityCreate,
    update_schema=EntityUpdate,
    out_schema=EntityOut,
    target_type="entity",
    label="La filiale",
)
project_types = catalog_router(
    path="project-types",
    model=ProjectType,
    create_schema=ProjectTypeCreate,
    update_schema=ProjectTypeUpdate,
    out_schema=ProjectTypeOut,
    target_type="project_type",
    label="Le type de projet",
)
programs = catalog_router(
    path="programs",
    model=Program,
    create_schema=ProgramCreate,
    update_schema=ProgramUpdate,
    out_schema=ProgramOut,
    target_type="program",
    label="Le programme",
)
