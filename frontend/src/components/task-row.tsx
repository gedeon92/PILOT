import { Link } from 'react-router'
import { errorMessage, type Task } from '../api/client'
import { useUpdateTask } from '../api/queries'
import { CERTAINTY, formatDay, TASK_STATUS, type TaskStatus } from '../labels'
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
  project?: { id: string; title: string }
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
        {project && (
          <Link className="task-row__project" to={`/espaces/${spaceId}/projets/${project.id}`}>
            {project.title}
          </Link>
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
