import { useState, type DragEvent } from 'react'
import { errorMessage, type Task } from '../api/client'
import { useAdvanced, useUpdateTask } from '../api/queries'
import { formatDay, TASK_STATUS, taskStatusChoices, type TaskStatus } from '../labels'
import { Avatar } from './avatar'
import { useOpenTask } from './task-dialog'
import { Alert } from './ui'

/** Vue « Tableau » des tâches (lot B) : une colonne par statut, des cartes qu'on fait glisser.
 * C'est une autre façon d'afficher les mêmes tâches : déplacer une carte change son statut,
 * exactement comme le menu de statut de la liste. Le menu « Colonne » de chaque carte permet
 * la même chose au clavier et sur téléphone. Les lecteurs voient le tableau sans rien déplacer. */

type Column = { key: TaskStatus; label: string; statuses: TaskStatus[]; tone: string }

// Étape F1 : « À qualifier » rejoint la colonne À faire ; Bloquée et En validation ont la leur.
const COLUMNS: Column[] = [
  { key: 'todo', label: 'À faire', statuses: ['to_qualify', 'todo'], tone: 'neutral' },
  { key: 'in_progress', label: 'En cours', statuses: ['in_progress'], tone: 'info' },
  { key: 'blocked', label: 'Bloquée', statuses: ['blocked'], tone: 'danger' },
  {
    key: 'awaiting_validation',
    label: 'En validation',
    statuses: ['awaiting_validation'],
    tone: 'warn',
  },
  { key: 'done', label: 'Terminé', statuses: ['done', 'cancelled'], tone: 'ok' },
]
// Au-delà, la colonne Terminé ne montre que les plus récentes (la liste les garde toutes).
const DONE_LIMIT = 30

export function TaskBoard({
  tasks,
  spaceId,
  canWrite,
}: {
  tasks: Task[]
  spaceId: string
  canWrite: boolean
}) {
  const update = useUpdateTask(spaceId)
  const advanced = useAdvanced(spaceId)
  // Déplacements affichés tout de suite, en attendant que la liste rechargée les confirme
  // (la version renvoyée par le serveur dit quand la liste est à jour). Une carte en cours
  // d'enregistrement n'a pas encore de version : elle ne peut pas être redéplacée.
  const [moves, setMoves] = useState<Record<string, { status: TaskStatus; version?: number }>>({})
  const [error, setError] = useState<unknown>(null)
  const [dragging, setDragging] = useState<string | null>(null)
  const [over, setOver] = useState<TaskStatus | null>(null)

  const statusOf = (t: Task) => {
    const m = moves[t.id]
    return m && (m.version === undefined || t.version < m.version) ? m.status : t.status
  }
  const byId = new Map(tasks.map((t) => [t.id, t]))

  function forget(id: string) {
    setMoves((m) => {
      const rest = { ...m }
      delete rest[id]
      return rest
    })
  }

  const pending = (t: Task) => moves[t.id] !== undefined && moves[t.id].version === undefined

  function move(task: Task, status: TaskStatus) {
    if (statusOf(task) === status || pending(task)) return
    setError(null)
    setMoves((m) => ({ ...m, [task.id]: { status } }))
    // La promesse de chaque appel aboutit toujours, même si d'autres cartes sont déplacées
    // entre-temps (contrairement aux rappels de `mutate`, qui ne suivent que le dernier appel).
    update.mutateAsync({ task, changes: { status } }).then(
      (saved) => setMoves((m) => ({ ...m, [task.id]: { status, version: saved.version } })),
      (err: unknown) => {
        forget(task.id)
        setError(err)
      },
    )
  }

  function onDrop(e: DragEvent, column: Column) {
    e.preventDefault()
    setOver(null)
    const task = byId.get(e.dataTransfer.getData('text/plain'))
    if (task && !column.statuses.includes(statusOf(task))) move(task, column.key)
  }

  // Mode simple : pas de colonnes Bloquée ni En validation, sauf si des tâches y sont déjà.
  const columns = COLUMNS.filter(
    (c) =>
      advanced ||
      (c.key !== 'blocked' && c.key !== 'awaiting_validation') ||
      tasks.some((t) => c.statuses.includes(statusOf(t))),
  )

  return (
    <>
      {error !== null && <Alert>{errorMessage(error)}</Alert>}
      <div
        className="board"
        aria-label="Tableau des tâches"
        style={{ gridTemplateColumns: `repeat(${columns.length}, minmax(165px, 1fr))` }}
      >
        {columns.map((column) => {
          let cards = tasks.filter((t) => column.statuses.includes(statusOf(t)))
          let hidden = 0
          if (column.key === 'done') {
            cards = [...cards].sort((a, b) => (b.closed_at ?? '').localeCompare(a.closed_at ?? ''))
            hidden = Math.max(0, cards.length - DONE_LIMIT)
            cards = cards.slice(0, DONE_LIMIT)
          }
          const droppable = canWrite && dragging !== null
          return (
            <section
              key={column.key}
              className={
                over === column.key && droppable
                  ? `board__col board__col--${column.tone} board__col--over`
                  : `board__col board__col--${column.tone}`
              }
              aria-label={`${column.label} : ${cards.length + hidden} tâche(s)`}
              onDragOver={(e) => {
                if (!droppable) return
                e.preventDefault()
                e.dataTransfer.dropEffect = 'move'
                if (over !== column.key) setOver(column.key)
              }}
              onDragLeave={(e) => {
                if (!e.currentTarget.contains(e.relatedTarget as Node)) setOver(null)
              }}
              onDrop={(e) => onDrop(e, column)}
            >
              <header className="board__head">
                <span className={`board__dot board__dot--${column.tone}`} aria-hidden="true" />
                <h2 className="board__title">{column.label}</h2>
                <span className="count">{cards.length + hidden}</span>
              </header>
              <ul className="board__cards">
                {cards.map((task) => (
                  <BoardCard
                    key={task.id}
                    task={task}
                    status={statusOf(task)}
                    canWrite={canWrite}
                    saving={pending(task)}
                    dragging={dragging === task.id}
                    onDragStart={() => setDragging(task.id)}
                    onDragEnd={() => {
                      setDragging(null)
                      setOver(null)
                    }}
                    onMove={(status) => move(task, status)}
                    choices={taskStatusChoices(advanced, statusOf(task))}
                  />
                ))}
              </ul>
              {cards.length === 0 && (
                <p className="board__empty">
                  {canWrite && dragging ? 'Déposez la carte ici' : 'Aucune tâche'}
                </p>
              )}
              {hidden > 0 && (
                <p className="board__more">
                  + {hidden} plus ancienne(s) : passez en vue Liste pour tout voir.
                </p>
              )}
            </section>
          )
        })}
      </div>
    </>
  )
}

function BoardCard({
  task,
  status,
  canWrite,
  saving,
  dragging,
  onDragStart,
  onDragEnd,
  onMove,
  choices,
}: {
  task: Task
  status: TaskStatus
  canWrite: boolean
  saving: boolean
  dragging: boolean
  onDragStart: () => void
  onDragEnd: () => void
  onMove: (status: TaskStatus) => void
  choices: TaskStatus[]
}) {
  const openTask = useOpenTask()
  const closed = status === 'done' || status === 'cancelled'
  const subtasks = task.subtasks_total ?? 0
  const comments = task.comments_count ?? 0
  const waiting = (task.waiting_on ?? 0) > 0 && !closed
  const files = task.documents_count ?? 0
  const repeats = Boolean(task.recurrence) && !closed

  return (
    <li
      className={[
        'board-card',
        closed && 'board-card--closed',
        dragging && 'board-card--dragging',
        canWrite && 'board-card--movable',
      ]
        .filter(Boolean)
        .join(' ')}
      draggable={canWrite && !saving}
      aria-busy={saving || undefined}
      onDragStart={(e) => {
        e.dataTransfer.setData('text/plain', task.id)
        e.dataTransfer.effectAllowed = 'move'
        onDragStart()
      }}
      onDragEnd={onDragEnd}
    >
      <button type="button" className="board-card__title" onClick={() => openTask(task.id)}>
        {task.title}
      </button>
      {(waiting ||
        subtasks > 0 ||
        comments > 0 ||
        files > 0 ||
        repeats ||
        status === 'cancelled') && (
        <span className="task-row__badges">
          {status === 'cancelled' && <span className="task-badge">Annulée</span>}
          {waiting && <span className="task-badge task-badge--waiting">En attente</span>}
          {subtasks > 0 && (
            <span className="task-badge">
              ☑ {task.subtasks_done ?? 0}/{subtasks}
            </span>
          )}
          {comments > 0 && <span className="task-badge">💬 {comments}</span>}
          {files > 0 && (
            <span className="task-badge" aria-label={`${files} fichier(s) joint(s)`}>
              📎 {files}
            </span>
          )}
          {repeats && (
            <span className="task-badge" aria-label="Tâche répétée">
              🔁
            </span>
          )}
        </span>
      )}
      <span className="board-card__foot">
        {task.assignee.name ? (
          <span className="board-card__person">
            <Avatar name={task.assignee.name} size="tiny" />
            {task.assignee.name}
          </span>
        ) : (
          <span className="muted">Non attribuée</span>
        )}
        {task.due_date && (
          <span className={task.late ? 'board-card__due board-card__due--late' : 'board-card__due'}>
            {task.late ? 'En retard · ' : ''}
            {formatDay(task.due_date)}
          </span>
        )}
      </span>
      {canWrite && (
        <label className="board-card__move">
          <span>Colonne</span>
          <select
            aria-label={`Colonne de « ${task.title} »`}
            value={status}
            disabled={saving}
            onChange={(e) => onMove(e.target.value as TaskStatus)}
          >
            {choices.map((s) => (
              <option key={s} value={s}>
                {TASK_STATUS[s].label}
              </option>
            ))}
          </select>
        </label>
      )}
    </li>
  )
}
