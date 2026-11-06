import { useState } from 'react'
import { useOutletContext } from 'react-router'
import { errorMessage, type Task } from '../api/client'
import { useMembers, useProjects, useSpaceTasks } from '../api/queries'
import { TasksIcon } from '../components/icons'
import { TaskRow } from '../components/task-row'
import { Alert, PageHeader } from '../components/ui'
import { addDays, todayIso } from '../labels'
import type { SpaceContext } from './space-layout'

type View = 'all' | 'late' | 'week' | 'undated'

const VIEWS: Record<View, string> = {
  all: 'Toutes',
  late: 'En retard',
  week: '7 prochains jours',
  undated: 'Sans date',
}

const closed = (t: Task) => t.status === 'done' || t.status === 'cancelled'

export function TasksPage() {
  const { space } = useOutletContext<SpaceContext>()
  const canWrite = space.role !== 'reader'
  const today = todayIso(space.timezone)
  const [view, setView] = useState<View>('all')
  const [mine, setMine] = useState(false)
  const [projectId, setProjectId] = useState('')
  const [q, setQ] = useState('')
  const [withClosed, setWithClosed] = useState(false)
  const tasks = useSpaceTasks(space.id, withClosed)
  const projects = useProjects(space.id)
  const members = useMembers(space.id)
  const myMemberId = members.data?.find((m) => m.is_me)?.id

  const projectById = new Map((projects.data ?? []).map((p) => [p.id, p]))
  const all = tasks.data ?? []
  const inWeek = (t: Task) =>
    t.due_date !== null && t.due_date >= today && t.due_date <= addDays(today, 7)
  const matches: Record<View, (t: Task) => boolean> = {
    all: () => true,
    late: (t) => t.late,
    week: (t) => !closed(t) && inWeek(t),
    undated: (t) => !closed(t) && t.due_date === null,
  }
  const needle = q.trim().toLocaleLowerCase('fr')
  const shown = all
    .filter(matches[view])
    .filter((t) => !mine || t.assignee.member_id === myMemberId)
    .filter((t) => !projectId || t.project_id === projectId)
    .filter((t) => !needle || t.title.toLocaleLowerCase('fr').includes(needle))
    .sort(
      (a, b) =>
        Number(closed(a)) - Number(closed(b)) ||
        (a.due_date ?? '9999').localeCompare(b.due_date ?? '9999'),
    )
  const counts = {
    late: all.filter(matches.late).length,
    week: all.filter(matches.week).length,
  }

  return (
    <div className="page-content">
      <PageHeader
        title="Tâches"
        subtitle="Les tâches de tous les projets. Cochez une tâche quand elle est faite ; pour en ajouter, ouvrez la fiche du projet."
      />
      <div className="filters tasks-filters">
        <div className="segmented" role="group" aria-label="Afficher">
          {(Object.keys(VIEWS) as View[]).map((v) => (
            <button
              key={v}
              type="button"
              aria-pressed={view === v}
              className={view === v ? 'segmented__item segmented__item--on' : 'segmented__item'}
              onClick={() => setView(v)}
            >
              {VIEWS[v]}
              {v === 'late' && counts.late > 0 && (
                <span className="count count--danger">{counts.late}</span>
              )}
              {v === 'week' && counts.week > 0 && <span className="count">{counts.week}</span>}
            </button>
          ))}
        </div>
        <label className="filters__search">
          <span className="visually-hidden">Rechercher une tâche</span>
          <input
            type="search"
            placeholder="Rechercher une tâche…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </label>
        <select
          aria-label="Projet"
          value={projectId}
          onChange={(e) => setProjectId(e.target.value)}
        >
          <option value="">Tous les projets</option>
          {(projects.data ?? []).map((p) => (
            <option key={p.id} value={p.id}>
              {p.title}
            </option>
          ))}
        </select>
        <label className="checkbox">
          <input type="checkbox" checked={mine} onChange={(e) => setMine(e.target.checked)} />
          Mes tâches
        </label>
        <label className="checkbox">
          <input
            type="checkbox"
            checked={withClosed}
            onChange={(e) => setWithClosed(e.target.checked)}
          />
          Afficher les tâches terminées
        </label>
      </div>
      {tasks.isError && <Alert>{errorMessage(tasks.error)}</Alert>}
      <section className="card-panel card-panel--flush" aria-label="Liste des tâches">
        {tasks.isPending ? (
          <p className="table-loading muted">Chargement…</p>
        ) : shown.length === 0 ? (
          <div className="table-empty">
            <span className="icon-tile icon-tile--info">
              <TasksIcon />
            </span>
            <span>
              {all.length === 0
                ? 'Aucune tâche pour l’instant. Ajoutez-en depuis la fiche d’un projet.'
                : 'Aucune tâche ne correspond à ces filtres.'}
            </span>
          </div>
        ) : (
          <ul className="task-list">
            {shown.map((t) => {
              const project = projectById.get(t.project_id)
              return (
                <TaskRow
                  key={t.id}
                  task={t}
                  spaceId={space.id}
                  canWrite={canWrite}
                  project={project && { id: project.id, title: project.title }}
                />
              )
            })}
          </ul>
        )}
      </section>
    </div>
  )
}
