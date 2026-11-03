# PILOT

Plateforme de pilotage de projets. Le plan de travail est dans [WORKFLOW.md](WORKFLOW.md).

| Dossier | Contenu | Hébergement |
|---|---|---|
| `backend/` | API Python (FastAPI) | Render |
| `frontend/` | Interface TypeScript (React + Vite) | Vercel |
| — | Base PostgreSQL | Neon |

## Lancer en local

Prérequis : [uv](https://docs.astral.sh/uv/) et Node.js 22.

```bash
# API : http://localhost:8000/api/health (documentation : /api/docs)
cd backend
cp .env.example .env   # puis renseigner DATABASE_URL (branche Neon « dev »)
uv sync
uv run uvicorn pilot_api.main:app --reload

# Interface : http://localhost:5173 (relaie /api vers le port 8000)
cd frontend
npm install
npm run dev
```

## Vérifications

```bash
cd backend && uv run ruff check . && uv run ruff format --check . && uv run pytest
cd frontend && npm run lint && npm run format:check && npm run typecheck && npm test && npm run build
```

Après chaque changement de l'API, régénérer les types du frontend :

```bash
cd frontend && npm run gen:api
```
