from typing import Literal

from fastapi import Depends, FastAPI
from pydantic import BaseModel

from pilot_api import __version__
from pilot_api.config import get_settings
from pilot_api.db import check_database
from pilot_api.deps import require_csrf_header
from pilot_api.routers import auth, invitations, spaces

app = FastAPI(
    title="PILOT API",
    version=__version__,
    openapi_url="/api/openapi.json",
    docs_url="/api/docs",
    redoc_url=None,
    dependencies=[Depends(require_csrf_header)],
)
app.include_router(auth.router)
app.include_router(spaces.router)
app.include_router(invitations.router)


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
