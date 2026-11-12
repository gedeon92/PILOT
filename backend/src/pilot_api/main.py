from typing import Literal

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError

from pilot_api import __version__
from pilot_api.config import get_settings
from pilot_api.db import check_database
from pilot_api.deps import require_csrf_header
from pilot_api.routers import (
    ai,
    alerts,
    auth,
    catalog,
    custom_fields,
    decisions,
    documents,
    invitations,
    milestones,
    portability,
    project_access,
    projects,
    purge,
    routines,
    sections,
    spaces,
    task_collab,
    templates,
    updates,
)

# La documentation interactive de l'API reste ouverte en test, fermée en production.
_PUBLIC_DOCS = get_settings().environment != "production"

app = FastAPI(
    title="PILOT API",
    version=__version__,
    openapi_url="/api/openapi.json" if _PUBLIC_DOCS else None,
    docs_url="/api/docs" if _PUBLIC_DOCS else None,
    redoc_url=None,
    dependencies=[Depends(require_csrf_header)],
)
app.include_router(auth.router)
app.include_router(spaces.router)
app.include_router(invitations.router)
app.include_router(catalog.portfolios)
app.include_router(catalog.entities)
app.include_router(catalog.project_types)
app.include_router(catalog.programs)
app.include_router(projects.router)
app.include_router(task_collab.router)
app.include_router(templates.router)
app.include_router(sections.router)
app.include_router(custom_fields.router)
app.include_router(routines.router)
app.include_router(milestones.router)
app.include_router(decisions.router)
app.include_router(purge.router)
app.include_router(project_access.router)
app.include_router(documents.router)
app.include_router(updates.router)
app.include_router(portability.router)
app.include_router(alerts.router)
app.include_router(alerts.cron_router)
app.include_router(ai.router)


@app.exception_handler(IntegrityError)
def integrity_conflict(_: Request, __: IntegrityError) -> JSONResponse:
    """Deux actions simultanées sur le même élément (doublon refusé par la base) : un message
    clair plutôt qu'une erreur serveur. La transaction est annulée à la fermeture de la session."""
    return JSONResponse(
        status_code=409,
        content={"detail": "Cet élément vient d'être modifié ou existe déjà. Rechargez la page."},
    )


class Health(BaseModel):
    status: Literal["ok"]
    version: str
    environment: str
    database: Literal["ok", "unavailable", "not_configured"]


@app.get("/api/health", response_model=Health, tags=["système"])
def health() -> Health:
    return Health(
        status="ok",
        version=__version__,
        environment=get_settings().environment,
        database=check_database(),
    )
