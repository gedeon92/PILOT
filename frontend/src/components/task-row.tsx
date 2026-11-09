import { useState, type FormEvent } from 'react'
import { errorMessage, type Task } from '../api/client'
import { useCreateTask, useMembers, useUpdateTask } from '../api/queries'
import { CERTAINTY, formatDay, TASK_STATUS, type TaskStatus } from '../labels'
import { personPayload } from '../person'
import { PersonField, type PersonValue } from './person-field'
import { Avatar } from './avatar'
import { Alert, StatusPill } from './ui'
import { useOpenTask } from './task-dialog'

/** Une tâche : case « terminée », responsable, échéance et statut. */
export function TaskRow({
  task,
  spaceId,
  canWrite,
  projectClosed = false,
}: {
  task: Task
  spaceId: string
  canWrite: boolean
  /** Projet terminé ou annulé : plus de sous-tâche possible. */
  projectClosed?: boolean
}) {
  const update = useUpdateTask(spaceId)
  const openTask = useOpenTask()
  const subtasks = task.subtasks_total ?? 0
  const comments = task.comments_count ?? 0
  const waiting = (task.waiting_on ?? 0) > 0
  const closed = task.status === 'done' || task.status === 'cancelled'
  const status = TASK_STATUS[task.status]

  return (
    <li className={closed ? 'task-row task-row--closed' : 'task-row'}>
      <input
        type="checkbox"
        className="task-row__check"
        aria-label={
          task.status === 'done'
            ? `Rouvrir « ${task.title} »`
            : `Marquer « ${task.title} » comme terminée`
        }
        checked={task.status === 'done'}
        disabled={!canWrite || task.status === 'cancelled' || update.isPending}
        onChange={(e) =>
          update.mutate({ task, changes: { status: e.target.checked ? 'done' : 'todo' } })
        }
      />
      <span className="task-row__text">
        <button
          type="button"
          className="task-row__title task-row__open"
          onClick={() => openTask(task.id)}
          title="Ouvrir la tâche : sous-tâches, commentaires, dépendances"
        >
          {task.title}
        </button>
        {(subtasks > 0 || comments > 0 || (waiting && !closed)) && (
          <span className="task-row__badges">
            {waiting && !closed && (
              <span className="task-badge task-badge--waiting">En attente</span>
            )}
            {subtasks > 0 && (
              <span
                className="task-badge"
                aria-label={`${task.subtasks_done ?? 0} sous-tâche(s) terminée(s) sur ${subtasks}`}
              >
                ☑ {task.subtasks_done ?? 0}/{subtasks}
              </span>
            )}
            {comments > 0 && (
              <span className="task-badge" aria-label={`${comments} commentaire(s)`}>
                💬 {comments}
              </span>
            )}
          </span>
        )}
        {task.deliverable && <span className="task-row__meta">Livrable : {task.deliverable}</span>}
      </span>
      <span className="task-row__person">
        {task.assignee.name ? (
          <>
            <Avatar name={task.assignee.name} size="tiny" />
            <span>
              {task.assignee.name}
              {!task.assignee.has_account && <span className="owner__note">Sans compte</span>}
            </span>
          </>
        ) : (
          <span className="muted">Non attribuée</span>
        )}
      </span>
      <span className="task-row__due">
        {task.due_date ? (
          <>
            <span className={task.late ? 'due__date due__date--late' : 'due__date'}>
              {formatDay(task.due_date)}
            </span>
            <span className="due__note">
              {task.late ? 'En retard' : task.due_certainty ? CERTAINTY[task.due_certainty] : ''}
            </span>
          </>
        ) : (
          <span className="muted">Sans date</span>
        )}
      </span>
      {canWrite && !closed ? (
        <select
          aria-label={`Statut de « ${task.title} »`}
          className="task-row__status"
          value={task.status}
          disabled={update.isPending}
          onChange={(e) =>
            update.mutate({ task, changes: { status: e.target.value as TaskStatus } })
          }
        >
          {(Object.keys(TASK_STATUS) as TaskStatus[]).map((s) => (
            <option key={s} value={s}>
              {TASK_STATUS[s].label}
            </option>
          ))}
        </select>
      ) : (
        <StatusPill tone={status.tone}>{status.label}</StatusPill>
      )}
      {canWrite && !closed && !projectClosed && !task.parent_id ? (
        <button
          type="button"
          className="button button--small task-row__details"
          aria-label={`Ajouter une sous-tâche à « ${task.title} »`}
          onClick={() => openTask(task.id, 'sous-taches')}
        >
          + Sous-tâche
        </button>
      ) : (
        <button
          type="button"
          className="button button--small task-row__details"
          aria-label={`Ouvrir « ${task.title} » : sous-tâches, commentaires, dépendances`}
          onClick={() => openTask(task.id)}
        >
          Ouvrir ›
        </button>
      )}
      {update.isError && <Alert>{errorMessage(update.error)}</Alert>}
    </li>
  )
}

/** Nouvelle tâche, dans le projet de la fiche (une tâche appartient toujours à un projet). */
export function TaskAddForm({
  spaceId,
  projectId,
  onDone,
}: {
  spaceId: string
  projectId: string
  onDone: () => void
}) {
  const create = useCreateTask(spaceId, projectId)
  const members = useMembers(spaceId)
  const [title, setTitle] = useState('')
  const [deliverable, setDeliverable] = useState('')
  const [due, setDue] = useState('')
  const [certainty, setCertainty] = useState('')
  const [assignee, setAssignee] = useState<PersonValue>({ memberId: null, label: '' })

  function submit(event: FormEvent) {
    event.preventDefault()
    create.mutate(
      {
        title,
        deliverable: deliverable || null,
        due_date: due || null,
        due_certainty: due && certainty ? certainty : null,
        ...personPayload(assignee, 'assignee'),
      },
      { onSuccess: onDone },
    )
  }

  return (
    <form className="form-grid task-form" onSubmit={submit} aria-label="Nouvelle tâche">
      <div className="field form-grid__full">
        <label htmlFor="task-title">Tâche *</label>
        <input
          id="task-title"
          required
          maxLength={200}
          value={title}
          onChange={(e) => setTitle(e.target.value)}
        />
      </div>
      <div className="field">
        <label htmlFor="task-deliverable">Livrable</label>
        <input
          id="task-deliverable"
          maxLength={300}
          value={deliverable}
          onChange={(e) => setDeliverable(e.target.value)}
        />
      </div>
      <PersonField
        id="task-assignee"
        label="Responsable"
        members={members.data ?? []}
        value={assignee}
        onChange={setAssignee}
      />
      <div className="field">
        <label htmlFor="task-due">Échéance</label>
        <input id="task-due" type="date" value={due} onChange={(e) => setDue(e.target.value)} />
      </div>
      <div className="field">
        <label htmlFor="task-certainty">Certitude</label>
        <select
          id="task-certainty"
          disabled={!due}
          value={certainty}
          onChange={(e) => setCertainty(e.target.value)}
        >
          <option value="">Non précisée</option>
          <option value="proposed">Proposée</option>
          <option value="confirmed">Confirmée</option>
        </select>
      </div>
      {create.isError && (
        <div className="form-grid__full">
          <Alert>{errorMessage(create.error)}</Alert>
        </div>
      )}
      <div className="form-grid__full form-actions">
        <button className="button button--primary" type="submit" disabled={create.isPending}>
          Ajouter la tâche
        </button>
        <button className="button button--ghost" type="button" onClick={onDone}>
          Annuler
        </button>
      </div>
    </form>
  )
}
