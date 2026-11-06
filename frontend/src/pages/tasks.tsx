import { useState } from 'react'
import { useOutletContext } from 'react-router'
import { errorMessage, type Task } from '../api/client'
import { useMembers, useProjects, useSpaceTasks } from '../api/queries'
import { PlusIcon, TasksIcon } from '../components/icons'
import { TaskAddForm, TaskRow } from '../components/task-row'
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

const GENERAL = '__general'

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
  const [adding, setAdding] = useState(false)
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
    .filter(
      (t) =>
        !projectId || (projectId === GENERAL ? t.project_id === null : t.project_id === projectId),
    )
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
        subtitle="Les tâches de tous les projets et du suivi général. Cochez une tâche quand elle est faite."
        actions={
          canWrite && !adding ? (
            <button
              type="button"
              className="button button--primary"
              onClick={() => setAdding(true)}
            >
              <PlusIcon /> Nouvelle tâche
            </button>
          ) : undefined
        }
      />
      {adding && (
        <section className="card-panel" aria-label="Ajouter une tâche">
          <TaskAddForm
            spaceId={space.id}
            projects={(projects.data ?? [])
              .filter((p) => p.status !== 'done' && p.status !== 'cancelled')
              .map((p) => ({ id: p.id, title: p.title }))}
            onDone={() => setAdding(false)}
          />
        </section>
      )}
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
          <option value={GENERAL}>Suivi général (sans projet)</option>
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
                ? 'Aucune tâche pour l’instant. Ajoutez-en avec « Nouvelle tâche ».'
                : 'Aucune tâche ne correspond à ces filtres.'}
            </span>
          </div>
        ) : (
          <ul className="task-list">
            {shown.map((t) => {
              const project = t.project_id ? projectById.get(t.project_id) : undefined
              return (
                <TaskRow
                  key={t.id}
                  task={t}
                  spaceId={space.id}
                  canWrite={canWrite}
                  project={
                    t.project_id === null
                      ? 'general'
                      : project && { id: project.id, title: project.title }
                  }
                />
              )
            })}
          </ul>
        )}
      </section>
    </div>
  )
}
