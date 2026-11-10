import { useState, type FormEvent } from 'react'
import { errorMessage, type Section, type Task } from '../api/client'
import {
  useArchiveSection,
  useCreateSection,
  useDefaultSections,
  useRenameSection,
  useReorderSections,
  useRestoreSection,
} from '../api/queries'
import { TaskAddForm, TaskRow } from './task-row'
import { Alert } from './ui'

/** Étape F1 (cahier V2, STR02) : les tâches d'un projet rangées par sections.
 * Une section organise ; ce n'est ni un statut ni une phase. Replier une section ne cache
 * jamais ses tâches en retard ou bloquées : leur nombre reste affiché dans l'en-tête. */

const isClosed = (t: Task) => t.status === 'done' || t.status === 'cancelled'

/** Barre d'outils : « + Section » et, pour un projet sans section, les sections types. */
export function SectionTools({
  spaceId,
  projectId,
  hasSections,
}: {
  spaceId: string
  projectId: string
  hasSections: boolean
}) {
  const create = useCreateSection(spaceId, projectId)
  const defaults = useDefaultSections(spaceId, projectId)
  const [adding, setAdding] = useState(false)
  const [title, setTitle] = useState('')

  function submit(event: FormEvent) {
    event.preventDefault()
    if (!title.trim()) return
    create.mutate(title.trim(), {
      onSuccess: () => {
        setTitle('')
        setAdding(false)
      },
    })
  }

  return (
    <div className="section-tools">
      {adding ? (
        <form className="inline-form" onSubmit={submit}>
          <label htmlFor="new-section" className="visually-hidden">
            Nom de la section
          </label>
          <input
            id="new-section"
            autoFocus
            required
            maxLength={120}
            placeholder="Nom de la section (ex. Préparation)"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
          <button className="button button--small button--primary" disabled={create.isPending}>
            Ajouter
          </button>
          <button type="button" className="button button--small" onClick={() => setAdding(false)}>
            Annuler
          </button>
        </form>
      ) : (
        <>
          <button type="button" className="button button--small" onClick={() => setAdding(true)}>
            + Section
          </button>
          {!hasSections && (
            <button
              type="button"
              className="button button--small button--ghost"
              disabled={defaults.isPending}
              title="Cadrage, Préparation, Exécution, Décisions et blocages, Contrôle et validation, Bilan et suites"
              onClick={() => defaults.mutate(undefined)}
            >
              Sections types
            </button>
          )}
        </>
      )}
      {(create.isError || defaults.isError) && (
        <Alert>{errorMessage(create.error ?? defaults.error)}</Alert>
      )}
    </div>
  )
}

function SectionHeader({
  section,
  tasks,
  index,
  sections,
  spaceId,
  projectId,
  canWrite,
  collapsed,
  onToggle,
  onAddTask,
}: {
  section: Section
  tasks: Task[]
  index: number
  sections: Section[]
  spaceId: string
  projectId: string
  canWrite: boolean
  collapsed: boolean
  onToggle: () => void
  onAddTask: () => void
}) {
  const rename = useRenameSection(spaceId, projectId)
  const reorder = useReorderSections(spaceId, projectId)
  const archive = useArchiveSection(spaceId, projectId)
  const [editing, setEditing] = useState(false)
  const [title, setTitle] = useState(section.title)
  const [archiving, setArchiving] = useState(false)
  const [target, setTarget] = useState<string>('')
  const late = tasks.filter((t) => t.late).length
  const blocked = tasks.filter((t) => t.status === 'blocked').length
  const others = sections.filter((s) => s.id !== section.id)
  const error = rename.error ?? reorder.error ?? archive.error

  function move(delta: number) {
    const ids = sections.map((s) => s.id)
    const to = index + delta
    if (to < 0 || to >= ids.length) return
    ;[ids[index], ids[to]] = [ids[to], ids[index]]
    reorder.mutate(ids)
  }

  if (editing) {
    return (
      <form
        className="inline-form task-section__head"
        onSubmit={(e) => {
          e.preventDefault()
          rename.mutate({ section, title: title.trim() }, { onSuccess: () => setEditing(false) })
        }}
      >
        <label htmlFor={`section-${section.id}`} className="visually-hidden">
          Nom de la section
        </label>
        <input
          id={`section-${section.id}`}
          autoFocus
          required
          maxLength={120}
          value={title}
          onChange={(e) => setTitle(e.target.value)}
        />
        <button className="button button--small button--primary" disabled={rename.isPending}>
          Enregistrer
        </button>
        <button type="button" className="button button--small" onClick={() => setEditing(false)}>
          Annuler
        </button>
      </form>
    )
  }

  return (
    <div className="task-section__head">
      <button
        type="button"
        className="task-section__toggle"
        aria-expanded={!collapsed}
        onClick={onToggle}
      >
        <span className="task-section__chevron" aria-hidden="true">
          {collapsed ? '▸' : '▾'}
        </span>
        <span className="task-section__title">{section.title}</span>
        <span className="count">{tasks.length}</span>
        {collapsed && late > 0 && (
          <span className="task-badge task-badge--late">{late} en retard</span>
        )}
        {collapsed && blocked > 0 && (
          <span className="task-badge task-badge--blocked">{blocked} bloquée(s)</span>
        )}
      </button>
      {canWrite && (
        <span className="task-section__actions">
          <button type="button" className="button button--small" onClick={onAddTask}>
            + Tâche
          </button>
          <button
            type="button"
            className="icon-button"
            aria-label={`Monter la section « ${section.title} »`}
            disabled={index === 0 || reorder.isPending}
            onClick={() => move(-1)}
          >
            ↑
          </button>
          <button
            type="button"
            className="icon-button"
            aria-label={`Descendre la section « ${section.title} »`}
            disabled={index === sections.length - 1 || reorder.isPending}
            onClick={() => move(1)}
          >
            ↓
          </button>
          <button
            type="button"
            className="button button--small button--ghost"
            onClick={() => {
              setTitle(section.title)
              setEditing(true)
            }}
          >
            Renommer
          </button>
          <button
            type="button"
            className="button button--small button--ghost"
            onClick={() => setArchiving((v) => !v)}
          >
            Archiver
          </button>
        </span>
      )}
      {archiving && (
        <div className="task-section__archive">
          {tasks.length > 0 ? (
            <label>
              Ranger ses {tasks.length} tâche(s) ouverte(s) dans :{' '}
              <select value={target} onChange={(e) => setTarget(e.target.value)}>
                <option value="">Sans section</option>
                {others.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.title}
                  </option>
                ))}
                <option value="__keep">Les laisser dans la section archivée</option>
              </select>
            </label>
          ) : (
            <span>Aucune tâche ouverte dans cette section.</span>
          )}
          <span className="muted">Rien n’est supprimé : la section peut être restaurée.</span>
          <button
            type="button"
            className="button button--small button--danger"
            disabled={archive.isPending}
            onClick={() =>
              archive.mutate({
                id: section.id,
                target: target && target !== '__keep' ? target : null,
                keep: target === '__keep',
              })
            }
          >
            Confirmer l’archivage
          </button>
          <button
            type="button"
            className="button button--small"
            onClick={() => setArchiving(false)}
          >
            Annuler
          </button>
        </div>
      )}
      {error && <Alert>{errorMessage(error)}</Alert>}
    </div>
  )
}

function TaskList({
  tasks,
  spaceId,
  canWrite,
  projectClosed,
}: {
  tasks: Task[]
  spaceId: string
  canWrite: boolean
  projectClosed: boolean
}) {
  return (
    <ul className="task-list">
      {tasks.map((task) => (
        <TaskRow
          key={task.id}
          task={task}
          spaceId={spaceId}
          canWrite={canWrite}
          projectClosed={projectClosed}
        />
      ))}
    </ul>
  )
}

/** Liste des tâches ouvertes, rangées par section (les clôturées restent à part). */
export function SectionedTasks({
  sections,
  tasks,
  spaceId,
  projectId,
  canWrite,
  projectClosed,
}: {
  sections: Section[]
  tasks: Task[]
  spaceId: string
  projectId: string
  canWrite: boolean
  projectClosed: boolean
}) {
  const restore = useRestoreSection(spaceId, projectId)
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({})
  const [addingIn, setAddingIn] = useState<string | null>(null)
  const active = sections.filter((s) => !s.archived)
  const archived = sections.filter((s) => s.archived)
  const activeIds = new Set(active.map((s) => s.id))
  const open = tasks.filter((t) => !isClosed(t))
  const loose = open.filter((t) => !t.section_id || !sections.some((s) => s.id === t.section_id))
  const writable = canWrite && !projectClosed

  return (
    <div className="task-sections">
      {loose.length > 0 && (
        <section className="task-section" aria-label="Tâches sans section">
          <div className="task-section__head">
            <span className="task-section__title task-section__title--muted">Sans section</span>
            <span className="count">{loose.length}</span>
          </div>
          <TaskList
            tasks={loose}
            spaceId={spaceId}
            canWrite={canWrite}
            projectClosed={projectClosed}
          />
        </section>
      )}
      {active.map((section, index) => {
        const inside = open.filter((t) => t.section_id === section.id)
        const isCollapsed = Boolean(collapsed[section.id])
        return (
          <section key={section.id} className="task-section" aria-label={section.title}>
            <SectionHeader
              section={section}
              tasks={inside}
              index={index}
              sections={active}
              spaceId={spaceId}
              projectId={projectId}
              canWrite={writable}
              collapsed={isCollapsed}
              onToggle={() => setCollapsed((c) => ({ ...c, [section.id]: !c[section.id] }))}
              onAddTask={() => setAddingIn(section.id)}
            />
            {!isCollapsed && (
              <>
                {section.description && inside.length === 0 && (
                  <p className="task-section__desc muted">{section.description}</p>
                )}
                {addingIn === section.id && (
                  <TaskAddForm
                    spaceId={spaceId}
                    projectId={projectId}
                    sectionId={section.id}
                    onDone={() => setAddingIn(null)}
                  />
                )}
                {inside.length > 0 && (
                  <TaskList
                    tasks={inside}
                    spaceId={spaceId}
                    canWrite={canWrite}
                    projectClosed={projectClosed}
                  />
                )}
              </>
            )}
          </section>
        )
      })}
      {archived.length > 0 && (
        <details className="task-closed">
          <summary>{archived.length} section(s) archivée(s)</summary>
          {archived.map((section) => {
            const inside = open.filter((t) => t.section_id === section.id)
            return (
              <section key={section.id} className="task-section task-section--archived">
                <div className="task-section__head">
                  <span className="task-section__title">{section.title}</span>
                  <span className="count">{inside.length}</span>
                  {writable && (
                    <button
                      type="button"
                      className="button button--small"
                      disabled={restore.isPending || activeIds.size >= 50}
                      onClick={() => restore.mutate(section.id)}
                    >
                      Restaurer
                    </button>
                  )}
                </div>
                {inside.length > 0 && (
                  <TaskList
                    tasks={inside}
                    spaceId={spaceId}
                    canWrite={canWrite}
                    projectClosed={projectClosed}
                  />
                )}
              </section>
            )
          })}
          {restore.isError && <Alert>{errorMessage(restore.error)}</Alert>}
        </details>
      )}
    </div>
  )
}
