"""taches toujours dans un projet

Décision du 9 nov. 2026 : une tâche appartient toujours à un projet. Les tâches du « suivi
général » (sans projet) déjà saisies sont rangées, espace par espace, dans un projet
« Suivi général » créé pour l'occasion (rien n'est perdu ; l'opération est journalisée).

Revision ID: e56683f9014f
Revises: d3b7c5688a12
Create Date: 2026-11-09 14:09:11.577015

"""

import json
import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e56683f9014f"
down_revision: Union[str, Sequence[str], None] = "d3b7c5688a12"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TITLE = "Suivi général"


def upgrade() -> None:
    conn = op.get_bind()
    spaces = conn.execute(
        sa.text("SELECT DISTINCT space_id FROM tasks WHERE project_id IS NULL")
    ).fetchall()
    for (space_id,) in spaces:
        portfolio_id = conn.execute(
            sa.text(
                "SELECT id FROM portfolios WHERE space_id = :s AND archived_at IS NULL "
                "ORDER BY created_at LIMIT 1"
            ),
            {"s": space_id},
        ).scalar()
        if portfolio_id is None:
            portfolio_id = uuid.uuid4()
            conn.execute(
                sa.text(
                    "INSERT INTO portfolios (id, space_id, name, color, created_at, version) "
                    "VALUES (:id, :s, :name, 'gray', now(), 1)"
                ),
                {"id": portfolio_id, "s": space_id, "name": TITLE},
            )
        project_id = uuid.uuid4()
        conn.execute(
            sa.text(
                "INSERT INTO projects (id, space_id, portfolio_id, title, status, created_at, "
                "updated_at, version) VALUES (:id, :s, :p, :title, 'in_progress', now(), now(), 1)"
            ),
            {"id": project_id, "s": space_id, "p": portfolio_id, "title": TITLE},
        )
        moved = conn.execute(
            sa.text(
                "UPDATE tasks SET project_id = :p WHERE space_id = :s AND project_id IS NULL "
                "RETURNING id"
            ),
            {"p": project_id, "s": space_id},
        ).fetchall()
        conn.execute(
            sa.text(
                "UPDATE alerts SET project_id = :p WHERE space_id = :s AND target_type = 'task' "
                "AND project_id IS NULL"
            ),
            {"p": project_id, "s": space_id},
        )
        conn.execute(
            sa.text(
                "INSERT INTO audit_log (id, space_id, action, target_type, target_id, after, "
                "created_at) VALUES (:id, :s, 'project.created', 'project', :t, "
                "CAST(:after AS jsonb), now())"
            ),
            {
                "id": uuid.uuid4(),
                "s": space_id,
                "t": str(project_id),
                "after": json.dumps(
                    {
                        "title": TITLE,
                        "note": f"{len(moved)} tâche(s) sans projet regroupée(s) ici",
                    },
                    ensure_ascii=False,
                ),
            },
        )


def downgrade() -> None:
    # Rien à défaire : les tâches restent dans leur projet « Suivi général ».
    pass
