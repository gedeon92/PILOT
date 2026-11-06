import { useState, type FormEvent } from 'react'
import { Link } from 'react-router'
import { errorMessage, type Task } from '../api/client'
import { useCreateSpaceTask, useCreateTask, useMembers, useUpdateTask } from '../api/queries'
import { CERTAINTY, formatDay, TASK_STATUS, type TaskStatus } from '../labels'
import { personPayload } from '../person'
import { PersonField, type PersonValue } from './person-field'
import { Alert, StatusPill } from './ui'

/** Une tâche : case « terminée », responsable, échéance et statut. `project` ajoute le lien
 * vers la fiche (page Tâches, où les tâches de tous les projets sont mélangées). */
export function TaskRow({
  task,
  spaceId,
  canWrite,
  project,
}: {
  task: Task
  spaceId: string
  canWrite: boolean
  project?: { id: string; title: string } | 'general'
}) {
  const update = useUpdateTask(spaceId)
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
        <span className="task-row__title">{task.title}</span>
        {project === 'general' ? (
          <span className="task-row__general">Suivi général</span>
        ) : (
          project && (
            <Link className="task-row__project" to={`/espaces/${spaceId}/projets/${project.id}`}>
              {project.title}
            </Link>
          )
        )}
        {task.deliverable && <span className="task-row__meta">Livrable : {task.deliverable}</span>}
      </span>
      <span className="task-row__person">
        {task.assignee.name ?? <span className="muted">Non attribuée</span>}
        {task.assignee.name && !task.assignee.has_account && (
          <span className="owner__note">Sans compte</span>
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
      {update.isError && <Alert>{errorMessage(update.error)}</Alert>}
    </li>
  )
}

/** Nouvelle tâche. Dans une fiche, le projet est fixé ; sur la page Tâches (`projects`
 * fourni), on choisit un projet ou « Suivi général » (aucun projet). */
export function TaskAddForm({
  spaceId,
  projectId,
  projects,
  onDone,
}: {
  spaceId: string
  projectId?: string
  projects?: { id: string; title: string }[]
  onDone: () => void
}) {
  const inProject = useCreateTask(spaceId, projectId ?? '')
  const inSpace = useCreateSpaceTask(spaceId)
  const create = projectId ? inProject : inSpace
  const members = useMembers(spaceId)
  const [target, setTarget] = useState('')
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
        ...(projectId ? {} : { project_id: target || null }),
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
      {projects && (
        <div className="field">
          <label htmlFor="task-project">Projet</label>
          <select id="task-project" value={target} onChange={(e) => setTarget(e.target.value)}>
            <option value="">Suivi général (aucun projet)</option>
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.title}
              </option>
            ))}
          </select>
        </div>
      )}
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
