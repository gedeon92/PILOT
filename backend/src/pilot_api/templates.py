"""Modèles de projet : photographie des tâches d'un projet, recopiée dans un nouveau projet.

Les échéances sont gardées en écart de jours par rapport à la date de début du projet
(par exemple « 30 jours avant ») ; elles sont recalculées à partir de la date de début du
nouveau projet. Sans date de début, les tâches sont créées sans échéance.
"""

import uuid
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from pilot_api.models import (
    Membership,
    MembershipStatus,
    Milestone,
    MilestoneState,
    MilestoneTask,
    Project,
    ProjectSection,
    ProjectTemplate,
    Task,
    TaskDependency,
    TaskPriority,
    TaskRecurrence,
    TaskStatus,
)

MAX_TEMPLATE_TASKS = 500


def _template_tasks(db: Session, project: Project) -> list[Task]:
    return list(
        db.scalars(
            select(Task)
            .where(
                Task.project_id == project.id,
                Task.status != TaskStatus.CANCELLED,
                # Une occurrence passée d'une tâche répétée : seule la plus récente est reprise.
                Task.next_task_id.is_(None),
            )
            .order_by(Task.parent_id.is_not(None), Task.created_at)
            .limit(MAX_TEMPLATE_TASKS)
        ).all()
    )


def _template_milestones(db: Session, project: Project) -> list[Milestone]:
    return list(
        db.scalars(
            select(Milestone)
            .where(Milestone.project_id == project.id, Milestone.state != MilestoneState.CANCELLED)
            .order_by(Milestone.due_date)
            .limit(100)
        ).all()
    )


def _reference(project: Project, tasks: list[Task], milestones: list[Milestone]) -> date | None:
    dues = [t.due_date for t in tasks if t.due_date] + [m.due_date for m in milestones]
    return project.start_date or (min(dues) if dues else None)


def snapshot_milestones(db: Session, project: Project) -> list[dict[str, Any]]:
    """Jalons non annulés (étape F2), en jours depuis la même date de référence que les
    tâches ; `tasks` cite les tâches liées par leur numéro dans le modèle."""
    tasks = _template_tasks(db, project)
    milestones = _template_milestones(db, project)
    reference = _reference(project, tasks, milestones)
    refs = {t.id: str(index) for index, t in enumerate(tasks, start=1)}
    sections = {
        s.id: s.title
        for s in db.scalars(select(ProjectSection).where(ProjectSection.project_id == project.id))
    }
    links: dict[uuid.UUID, list[str]] = {}
    if milestones:
        for milestone_id, task_id in db.execute(
            select(MilestoneTask.milestone_id, MilestoneTask.task_id).where(
                MilestoneTask.milestone_id.in_([m.id for m in milestones])
            )
        ):
            if task_id in refs:
                links.setdefault(milestone_id, []).append(refs[task_id])
    return [
        {
            "title": m.title,
            "criterion": m.criterion,
            "offset_days": (m.due_date - reference).days if reference else None,
            "section": sections.get(m.section_id) if m.section_id else None,
            "critical": bool(m.critical),
            "tasks": links.get(m.id, []),
            "owner_member_id": str(m.owner_member_id) if m.owner_member_id else None,
            "owner_label": m.owner_label,
        }
        for m in milestones
    ]


def snapshot_tasks(db: Session, project: Project) -> list[dict[str, Any]]:
    """Tâches non annulées du projet (tâches puis sous-tâches), prêtes à être recopiées.
    Les occurrences déjà remplacées d'une tâche répétée ne sont pas reprises."""
    tasks = _template_tasks(db, project)
    reference: date | None = _reference(project, tasks, _template_milestones(db, project))
    refs = {t.id: str(index) for index, t in enumerate(tasks, start=1)}
    waits: dict[uuid.UUID, list[str]] = {}
    for task_id, other in db.execute(
        select(TaskDependency.task_id, TaskDependency.depends_on_id).where(
            TaskDependency.task_id.in_(refs)
        )
    ):
        if other in refs:
            waits.setdefault(task_id, []).append(refs[other])
    section_titles = {
        s.id: s.title
        for s in db.scalars(select(ProjectSection).where(ProjectSection.project_id == project.id))
    }
    return [
        {
            "ref": refs[t.id],
            "section": section_titles.get(t.section_id) if t.section_id else None,
            "priority": t.priority.value if t.priority else None,
            "title": t.title,
            "deliverable": t.deliverable,
            "offset_days": (t.due_date - reference).days if t.due_date and reference else None,
            "parent": refs.get(t.parent_id) if t.parent_id else None,
            "waits_for": waits.get(t.id, []),
            "recurrence": t.recurrence.value if t.recurrence else None,
            "assignee_member_id": str(t.assignee_member_id) if t.assignee_member_id else None,
            "assignee_label": t.assignee_label,
        }
        for t in tasks
        if not t.parent_id or t.parent_id in refs
    ]


def snapshot_sections(db: Session, project: Project) -> list[str]:
    """Titres des sections actives du projet, dans l'ordre (étape F1)."""
    return [
        s.title
        for s in db.scalars(
            select(ProjectSection)
            .where(ProjectSection.project_id == project.id, ProjectSection.archived_at.is_(None))
            .order_by(ProjectSection.position, ProjectSection.created_at)
        )
    ][:50]


def apply_template(db: Session, project: Project, template: ProjectTemplate) -> list[Task]:
    """Crée dans `project` les tâches du modèle. Renvoie les tâches créées."""
    anchor = project.start_date
    active = {
        str(m)
        for m in db.scalars(
            select(Membership.id).where(
                Membership.space_id == project.space_id,
                Membership.status == MembershipStatus.ACTIVE,
            )
        )
    }
    sections: dict[str, ProjectSection] = {}
    for position, title in enumerate(template.sections or [], start=1):
        name = str(title).strip()[:120]
        if name and name not in sections and len(sections) < 50:
            section = ProjectSection(
                space_id=project.space_id, project_id=project.id, title=name, position=position
            )
            db.add(section)
            sections[name] = section
    db.flush()
    created: dict[str, Task] = {}
    items = [i for i in template.tasks or [] if isinstance(i, dict) and i.get("title")]
    for item in items[:MAX_TEMPLATE_TASKS]:
        parent = created.get(str(item.get("parent"))) if item.get("parent") else None
        if item.get("parent") and parent is None:
            continue
        offset = item.get("offset_days")
        due = anchor + timedelta(days=int(offset)) if anchor and offset is not None else None
        member = item.get("assignee_member_id")
        recurrence = item.get("recurrence")
        task = Task(
            space_id=project.space_id,
            project_id=project.id,
            parent_id=parent.id if parent else None,
            title=str(item["title"])[:200],
            deliverable=(str(item["deliverable"])[:300] if item.get("deliverable") else None),
            status=TaskStatus.TODO,
            assignee_member_id=uuid.UUID(member) if member in active else None,
            assignee_label=(
                str(item["assignee_label"])[:120] if item.get("assignee_label") else None
            ),
            due_date=due,
            # Une répétition exige une échéance, et ne vaut pas pour une sous-tâche.
            recurrence=(
                TaskRecurrence(recurrence)
                if recurrence in TaskRecurrence._value2member_map_ and due and not parent
                else None
            ),
        )
        section = sections.get(str(item.get("section") or "")) if not parent else None
        task.section_id = section.id if section else None
        priority = item.get("priority")
        if priority in TaskPriority._value2member_map_:
            task.priority = TaskPriority(priority)
        db.add(task)
        db.flush()
        created[str(item.get("ref"))] = task
    waits: dict[uuid.UUID, set[uuid.UUID]] = {}

    def reaches(start: uuid.UUID, goal: uuid.UUID) -> bool:
        seen, todo = set(), [start]
        while todo:
            current = todo.pop()
            if current == goal:
                return True
            if current not in seen:
                seen.add(current)
                todo.extend(waits.get(current, ()))
        return False

    for item in items:
        task = created.get(str(item.get("ref")))
        for other_ref in (item.get("waits_for") or [])[:20]:
            other = created.get(str(other_ref))
            if task is None or other is None or other is task:
                continue
            if other.id in waits.get(task.id, ()) or reaches(other.id, task.id):
                continue  # doublon ou attente en boucle (modèle modifié) : écartée
            waits.setdefault(task.id, set()).add(other.id)
            db.add(
                TaskDependency(space_id=project.space_id, task_id=task.id, depends_on_id=other.id)
            )
    # Jalons (étape F2) : leur date engagée vient de la date de début ; sans elle, ils ne
    # peuvent pas être datés et ne sont pas recréés (le journal le signale).
    for item in (template.milestones or [])[:100]:
        offset = item.get("offset_days") if isinstance(item, dict) else None
        if not isinstance(item, dict) or not item.get("title") or anchor is None or offset is None:
            continue
        member = item.get("owner_member_id")
        section = sections.get(str(item.get("section") or ""))
        milestone = Milestone(
            space_id=project.space_id,
            project_id=project.id,
            section_id=section.id if section else None,
            title=str(item["title"])[:200],
            criterion=str(item["criterion"])[:5000] if item.get("criterion") else None,
            owner_member_id=uuid.UUID(member) if member in active else None,
            owner_label=str(item["owner_label"])[:120] if item.get("owner_label") else None,
            due_date=anchor + timedelta(days=int(offset)),
            postpone_count=0,
            critical=bool(item.get("critical")),
            state=MilestoneState.PLANNED,
        )
        db.add(milestone)
        db.flush()
        for ref in {str(r) for r in (item.get("tasks") or [])[:100]}:
            task = created.get(ref)
            if task is not None:
                db.add(MilestoneTask(milestone_id=milestone.id, task_id=task.id))
    return list(created.values())
