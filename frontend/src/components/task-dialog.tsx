import {
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
  type ReactNode,
} from 'react'
import { Link, useSearchParams } from 'react-router'
import { errorMessage, type Member, type Task, type TaskDetail, type TaskRef } from '../api/client'
import {
  useAddComment,
  useAddDependency,
  useAddSubtask,
  useDeleteComment,
  useFollowTask,
  useMembers,
  useProjects,
  useRemoveDependency,
  useSpaceTasks,
  useTaskDetail,
  useUpdateTask,
} from '../api/queries'
import { CERTAINTY, formatDay, formatMoment, TASK_STATUS, type TaskStatus } from '../labels'
import { personPayload, personValue } from '../person'
import { Avatar } from './avatar'
import { PersonField, type PersonValue } from './person-field'
import { Alert, StatusPill } from './ui'

const PARAM = 'tache'
// Partie de la fenêtre à mettre en avant à l'ouverture (ex. « + Sous-tâche » dans la liste).
const ZONE = 'zone'
const SUBTASKS_ZONE = 'sous-taches'

/** Ouvre la fenêtre d'une tâche en ajoutant `?tache=<id>` à l'adresse de la page :
 * le lien peut être partagé, et « Retour » du navigateur la referme. */
export function useOpenTask() {
  const [params, setParams] = useSearchParams()
  return (taskId: string, zone?: 'sous-taches') => {
    const next = new URLSearchParams(params)
    next.set(PARAM, taskId)
    if (zone) next.set(ZONE, zone)
    else next.delete(ZONE)
    setParams(next)
  }
}

/** Placée une fois dans la mise en page de l'espace : affiche la tâche demandée dans l'adresse. */
export function TaskDialogHost({ spaceId, canWrite }: { spaceId: string; canWrite: boolean }) {
  const [params, setParams] = useSearchParams()
  const taskId = params.get(PARAM)
  if (!taskId) return null
  const close = () => {
    const next = new URLSearchParams(params)
    next.delete(PARAM)
    next.delete(ZONE)
    setParams(next)
  }
  return (
    <TaskDialog
      key={taskId}
      spaceId={spaceId}
      taskId={taskId}
      canWrite={canWrite}
      onClose={close}
    />
  )
}

function isClosed(status: TaskStatus) {
  return status === 'done' || status === 'cancelled'
}

export function TaskDialog({
  spaceId,
  taskId,
  canWrite,
  onClose,
}: {
  spaceId: string
  taskId: string
  canWrite: boolean
  onClose: () => void
}) {
  const detail = useTaskDetail(spaceId, taskId)
  const panel = useRef<HTMLElement>(null)

  useEffect(() => {
    panel.current?.focus()
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = previous
    }
  }, [])

  function onKeyDown(e: KeyboardEvent) {
    if (e.key === 'Escape' && !e.defaultPrevented) onClose()
  }

  return (
    <div
      className="task-drawer-backdrop"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <aside
        ref={panel}
        className="task-drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="task-drawer-title"
        tabIndex={-1}
        onKeyDown={onKeyDown}
      >
        <button
          type="button"
          className="icon-button task-drawer__close"
          aria-label="Fermer la tâche"
          onClick={onClose}
        >
          ×
        </button>
        {detail.isPending && <p className="muted">Chargement de la tâche…</p>}
        {detail.isError && (
          <>
            <h2 id="task-drawer-title">Tâche indisponible</h2>
            <Alert>{errorMessage(detail.error)}</Alert>
          </>
        )}
        {detail.data && <TaskContent spaceId={spaceId} detail={detail.data} canWrite={canWrite} />}
      </aside>
    </div>
  )
}

function TaskContent({
  spaceId,
  detail,
  canWrite,
}: {
  spaceId: string
  detail: TaskDetail
  canWrite: boolean
}) {
  const { task } = detail
  const openTask = useOpenTask()
  const waiting = detail.depends_on.filter((t) => !isClosed(t.status))

  return (
    <div className="task-drawer__body">
      <header className="task-drawer__head">
        <p className="eyebrow">
          {detail.parent ? (
            <>
              Sous-tâche de{' '}
              <button
                type="button"
                className="link-button"
                onClick={() => openTask(detail.parent!.id)}
              >
                {detail.parent.title}
              </button>
            </>
          ) : task.project_id ? (
            <Link to={`/espaces/${spaceId}/projets/${task.project_id}`}>
              {detail.project_title}
            </Link>
          ) : (
            'Suivi général'
          )}
        </p>
        <h2 id="task-drawer-title" className="task-drawer__title">
          {task.title}
        </h2>
        <FollowButton spaceId={spaceId} detail={detail} />
      </header>

      {waiting.length > 0 && !isClosed(task.status) && (
        <div className="alert alert--warn task-drawer__waiting" role="status">
          En attente de {waiting.length > 1 ? 'la fin de :' : 'la fin de'}{' '}
          {waiting.map((t, i) => (
            <span key={t.id}>
              {i > 0 && ', '}« {t.title} »
            </span>
          ))}
        </div>
      )}

      <TaskFields spaceId={spaceId} task={task} canWrite={canWrite} />

      {!detail.parent && <Subtasks spaceId={spaceId} detail={detail} canWrite={canWrite} />}
      <Dependencies spaceId={spaceId} detail={detail} canWrite={canWrite} />
      <Comments spaceId={spaceId} detail={detail} canWrite={canWrite} />
      <Followers detail={detail} />
    </div>
  )
}

function Section({
  title,
  count,
  children,
}: {
  title: string
  count?: ReactNode
  children: ReactNode
}) {
  return (
    <section className="task-drawer__section">
      <h3>
        {title} {count !== undefined && <span className="count">{count}</span>}
      </h3>
      {children}
    </section>
  )
}

// ---------- Champs de la tâche ----------

function TaskFields({
  spaceId,
  task,
  canWrite,
}: {
  spaceId: string
  task: Task
  canWrite: boolean
}) {
  const update = useUpdateTask(spaceId)
  const [editing, setEditing] = useState(false)
  const status = TASK_STATUS[task.status]

  if (editing) {
    return <TaskEditForm spaceId={spaceId} task={task} onDone={() => setEditing(false)} />
  }
  return (
    <dl className="task-drawer__facts">
      <div>
        <dt>Statut</dt>
        <dd>
          {canWrite ? (
            <select
              aria-label="Statut de la tâche"
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
        </dd>
      </div>
      <div>
        <dt>Responsable</dt>
        <dd className="task-drawer__person">
          {task.assignee.name ? (
            <>
              <Avatar name={task.assignee.name} size="tiny" />
              {task.assignee.name}
              {!task.assignee.has_account && <span className="owner__note">Sans compte</span>}
            </>
          ) : (
            <span className="muted">Non attribuée</span>
          )}
        </dd>
      </div>
      <div>
        <dt>Échéance</dt>
        <dd>
          {task.due_date ? (
            <span className={task.late ? 'due__date--late' : undefined}>
              {formatDay(task.due_date)}
              {task.late
                ? ' · en retard'
                : task.due_certainty
                  ? ` · ${CERTAINTY[task.due_certainty].toLowerCase()}`
                  : ''}
            </span>
          ) : (
            <span className="muted">Sans date</span>
          )}
        </dd>
      </div>
      <div>
        <dt>Livrable</dt>
        <dd>{task.deliverable ?? <span className="muted">Non précisé</span>}</dd>
      </div>
      {canWrite && (
        <div className="task-drawer__edit">
          <button type="button" className="button button--small" onClick={() => setEditing(true)}>
            Modifier la tâche
          </button>
        </div>
      )}
      {update.isError && <Alert>{errorMessage(update.error)}</Alert>}
    </dl>
  )
}

function TaskEditForm({
  spaceId,
  task,
  onDone,
}: {
  spaceId: string
  task: Task
  onDone: () => void
}) {
  const update = useUpdateTask(spaceId)
  const members = useMembers(spaceId)
  const [title, setTitle] = useState(task.title)
  const [deliverable, setDeliverable] = useState(task.deliverable ?? '')
  const [due, setDue] = useState(task.due_date ?? '')
  const [certainty, setCertainty] = useState<string>(task.due_certainty ?? '')
  const [assignee, setAssignee] = useState<PersonValue>(personValue(task.assignee))

  function submit(event: FormEvent) {
    event.preventDefault()
    update.mutate(
      {
        task,
        changes: {
          title,
          deliverable: deliverable || null,
          due_date: due || null,
          due_certainty: due && certainty ? certainty : null,
          ...personPayload(assignee, 'assignee'),
        },
      },
      { onSuccess: onDone },
    )
  }

  return (
    <form className="form-grid task-drawer__form" onSubmit={submit} aria-label="Modifier la tâche">
      <div className="field form-grid__full">
        <label htmlFor="edit-task-title">Tâche *</label>
        <input
          id="edit-task-title"
          required
          maxLength={200}
          value={title}
          onChange={(e) => setTitle(e.target.value)}
        />
      </div>
      <div className="field form-grid__full">
        <label htmlFor="edit-task-deliverable">Livrable</label>
        <input
          id="edit-task-deliverable"
          maxLength={300}
          value={deliverable}
          onChange={(e) => setDeliverable(e.target.value)}
        />
      </div>
      <PersonField
        id="edit-task-assignee"
        label="Responsable"
        members={members.data ?? []}
        value={assignee}
        onChange={setAssignee}
      />
      <div className="field">
        <label htmlFor="edit-task-due">Échéance</label>
        <input
          id="edit-task-due"
          type="date"
          value={due}
          onChange={(e) => setDue(e.target.value)}
        />
      </div>
      <div className="field">
        <label htmlFor="edit-task-certainty">Certitude</label>
        <select
          id="edit-task-certainty"
          disabled={!due}
          value={certainty}
          onChange={(e) => setCertainty(e.target.value)}
        >
          <option value="">Non précisée</option>
          <option value="proposed">Proposée</option>
          <option value="confirmed">Confirmée</option>
        </select>
      </div>
      {update.isError && (
        <div className="form-grid__full">
          <Alert>{errorMessage(update.error)}</Alert>
        </div>
      )}
      <div className="form-grid__full form-actions">
        <button className="button button--primary" type="submit" disabled={update.isPending}>
          Enregistrer
        </button>
        <button className="button button--ghost" type="button" onClick={onDone}>
          Annuler
        </button>
      </div>
    </form>
  )
}

// ---------- Sous-tâches ----------

function Subtasks({
  spaceId,
  detail,
  canWrite,
}: {
  spaceId: string
  detail: TaskDetail
  canWrite: boolean
}) {
  const add = useAddSubtask(spaceId, detail.task.id)
  const update = useUpdateTask(spaceId)
  const openTask = useOpenTask()
  const [title, setTitle] = useState('')
  const [params] = useSearchParams()
  const focusHere = params.get(ZONE) === SUBTASKS_ZONE
  const input = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (!focusHere) return
    input.current?.scrollIntoView?.({ block: 'center' })
    input.current?.focus()
  }, [focusHere])
  const subtasks = detail.subtasks
  const counted = subtasks.filter((t) => t.status !== 'cancelled')
  const done = counted.filter((t) => t.status === 'done').length
  const canAdd = canWrite && !isClosed(detail.task.status)

  function submit(event: FormEvent) {
    event.preventDefault()
    if (!title.trim()) return
    add.mutate({ title: title.trim() }, { onSuccess: () => setTitle('') })
  }

  return (
    <Section
      title="Sous-tâches"
      count={counted.length ? `${done} sur ${counted.length}` : undefined}
    >
      {counted.length > 0 && (
        <div className="task-drawer__progress" aria-hidden="true">
          <span style={{ width: `${(done / counted.length) * 100}%` }} />
        </div>
      )}
      {subtasks.length === 0 && !canAdd && <p className="muted">Aucune sous-tâche.</p>}
      <ul className="subtask-list">
        {subtasks.map((sub) => (
          <li key={sub.id} className={isClosed(sub.status) ? 'subtask subtask--closed' : 'subtask'}>
            <input
              type="checkbox"
              aria-label={
                sub.status === 'done'
                  ? `Rouvrir « ${sub.title} »`
                  : `Marquer « ${sub.title} » comme terminée`
              }
              checked={sub.status === 'done'}
              disabled={!canWrite || sub.status === 'cancelled' || update.isPending}
              onChange={(e) =>
                update.mutate({
                  task: sub,
                  changes: { status: e.target.checked ? 'done' : 'todo' },
                })
              }
            />
            <button
              type="button"
              className="link-button subtask__title"
              onClick={() => openTask(sub.id)}
            >
              {sub.title}
            </button>
            {sub.assignee.name && (
              <Avatar name={sub.assignee.name} size="tiny" title={sub.assignee.name} />
            )}
            {sub.due_date && (
              <span className={sub.late ? 'subtask__due due__date--late' : 'subtask__due'}>
                {formatDay(sub.due_date)}
              </span>
            )}
          </li>
        ))}
      </ul>
      {canAdd && (
        <form className="inline-form" onSubmit={submit}>
          <label htmlFor="new-subtask" className="visually-hidden">
            Nouvelle sous-tâche
          </label>
          <input
            id="new-subtask"
            ref={input}
            placeholder="Ajouter une sous-tâche…"
            maxLength={200}
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
          <button
            className="button button--small"
            type="submit"
            disabled={add.isPending || !title.trim()}
          >
            Ajouter
          </button>
        </form>
      )}
      {(add.isError || update.isError) && <Alert>{errorMessage(add.error ?? update.error)}</Alert>}
    </Section>
  )
}

// ---------- Dépendances ----------

function RefItem({
  item,
  onRemove,
  removeLabel,
}: {
  item: TaskRef
  onRemove?: () => void
  removeLabel?: string
}) {
  const openTask = useOpenTask()
  const status = TASK_STATUS[item.status]
  return (
    <li className="dep">
      <button type="button" className="link-button dep__title" onClick={() => openTask(item.id)}>
        {item.title}
      </button>
      <span className="dep__project">{item.project_title ?? 'Suivi général'}</span>
      <StatusPill tone={status.tone}>{status.label}</StatusPill>
      {onRemove && (
        <button type="button" className="icon-button" aria-label={removeLabel} onClick={onRemove}>
          ×
        </button>
      )}
    </li>
  )
}

function Dependencies({
  spaceId,
  detail,
  canWrite,
}: {
  spaceId: string
  detail: TaskDetail
  canWrite: boolean
}) {
  const { task } = detail
  const add = useAddDependency(spaceId, task.id)
  const remove = useRemoveDependency(spaceId, task.id)
  const [adding, setAdding] = useState(false)
  const [choice, setChoice] = useState('')
  const candidates = useSpaceTasks(spaceId, false)
  const projects = useProjects(spaceId)
  const titles = new Map(projects.data?.map((p) => [p.id, p.title]))
  const excluded = new Set([task.id, ...detail.depends_on.map((t) => t.id)])
  // Les tâches du même projet d'abord, puis les autres.
  const options = (candidates.data ?? [])
    .filter((t) => !excluded.has(t.id))
    .sort(
      (a, b) => Number(b.project_id === task.project_id) - Number(a.project_id === task.project_id),
    )

  return (
    <Section title="Dépendances">
      <p className="task-drawer__hint">Cette tâche attend la fin de :</p>
      {detail.depends_on.length === 0 ? (
        <p className="muted">Aucune tâche.</p>
      ) : (
        <ul className="dep-list">
          {detail.depends_on.map((item) => (
            <RefItem
              key={item.id}
              item={item}
              onRemove={canWrite ? () => remove.mutate(item.id) : undefined}
              removeLabel={`Ne plus attendre « ${item.title} »`}
            />
          ))}
        </ul>
      )}
      {canWrite &&
        (adding ? (
          <form
            className="inline-form"
            onSubmit={(e) => {
              e.preventDefault()
              if (!choice) return
              add.mutate(choice, {
                onSuccess: () => {
                  setChoice('')
                  setAdding(false)
                },
              })
            }}
          >
            <label htmlFor="new-dependency" className="visually-hidden">
              Tâche à attendre
            </label>
            <select id="new-dependency" value={choice} onChange={(e) => setChoice(e.target.value)}>
              <option value="">Choisir une tâche ouverte…</option>
              {options.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.title} ·{' '}
                  {t.project_id ? (titles.get(t.project_id) ?? 'Projet') : 'Suivi général'}
                </option>
              ))}
            </select>
            <button
              className="button button--small"
              type="submit"
              disabled={!choice || add.isPending}
            >
              Ajouter
            </button>
            <button
              className="button button--small button--ghost"
              type="button"
              onClick={() => setAdding(false)}
            >
              Annuler
            </button>
          </form>
        ) : (
          <button type="button" className="button button--small" onClick={() => setAdding(true)}>
            Attendre une autre tâche
          </button>
        ))}
      {detail.blocking.length > 0 && (
        <>
          <p className="task-drawer__hint">Ces tâches attendent la fin de celle-ci :</p>
          <ul className="dep-list">
            {detail.blocking.map((item) => (
              <RefItem key={item.id} item={item} />
            ))}
          </ul>
        </>
      )}
      {(add.isError || remove.isError) && <Alert>{errorMessage(add.error ?? remove.error)}</Alert>}
    </Section>
  )
}

// ---------- Commentaires et mentions ----------

function memberName(member: Member) {
  return member.display_name ?? member.email
}

/** Texte du commentaire avec les @mentions mises en valeur. */
function CommentBody({ text, names }: { text: string; names: string[] }) {
  if (names.length === 0) return <>{text}</>
  const escaped = names.map((n) => n.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
  const parts = text.split(new RegExp(`(@(?:${escaped.join('|')}))`, 'g'))
  return (
    <>
      {parts.map((part, i) =>
        part.startsWith('@') && names.includes(part.slice(1)) ? (
          <mark key={i} className="mention">
            {part}
          </mark>
        ) : (
          <span key={i}>{part}</span>
        ),
      )}
    </>
  )
}

function Comments({
  spaceId,
  detail,
  canWrite,
}: {
  spaceId: string
  detail: TaskDetail
  canWrite: boolean
}) {
  const remove = useDeleteComment(spaceId, detail.task.id)
  return (
    <Section title="Commentaires" count={detail.comments.length || undefined}>
      {detail.comments.length === 0 && <p className="muted">Aucun commentaire pour l’instant.</p>}
      <ol className="comment-list">
        {detail.comments.map((comment) => (
          <li key={comment.id} className="comment">
            <Avatar name={comment.author_name} size="small" />
            <div className="comment__main">
              <p className="comment__meta">
                <strong>{comment.author_name}</strong> · {formatMoment(comment.created_at)}
                {canWrite && comment.can_delete && (
                  <button
                    type="button"
                    className="link-button comment__delete"
                    onClick={() => remove.mutate(comment.id)}
                  >
                    Retirer
                  </button>
                )}
              </p>
              <p className="comment__body">
                <CommentBody text={comment.body} names={comment.mentions.map((m) => m.name)} />
              </p>
            </div>
          </li>
        ))}
      </ol>
      {remove.isError && <Alert>{errorMessage(remove.error)}</Alert>}
      {canWrite && <CommentComposer spaceId={spaceId} taskId={detail.task.id} />}
    </Section>
  )
}

function CommentComposer({ spaceId, taskId }: { spaceId: string; taskId: string }) {
  const add = useAddComment(spaceId, taskId)
  const members = useMembers(spaceId)
  const [text, setText] = useState('')
  const [picked, setPicked] = useState<Map<string, string>>(new Map())
  const [query, setQuery] = useState<string | null>(null)
  const [active, setActive] = useState(0)
  const field = useRef<HTMLTextAreaElement>(null)
  // Position du curseur à rétablir juste après l'insertion d'une mention.
  const caret = useRef<number | null>(null)

  useLayoutEffect(() => {
    if (caret.current === null) return
    field.current?.focus()
    field.current?.setSelectionRange(caret.current, caret.current)
    caret.current = null
  }, [text])

  const mentionable = useMemo(
    () => (members.data ?? []).filter((m) => m.status === 'active'),
    [members.data],
  )
  const fold = (s: string) => s.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase()
  const suggestions =
    query === null
      ? []
      : mentionable.filter((m) => fold(memberName(m)).includes(fold(query))).slice(0, 6)

  function readQuery(value: string, caret: number) {
    const match = /(?:^|\s)@([^\s@]{0,30})$/u.exec(value.slice(0, caret))
    setQuery(match ? match[1] : null)
    setActive(0)
  }

  function choose(member: Member) {
    const at = field.current?.selectionStart ?? text.length
    const before = text.slice(0, at).replace(/@([^\s@]{0,30})$/u, `@${memberName(member)} `)
    const next = before + text.slice(at)
    setText(next)
    setPicked(new Map(picked).set(member.id, memberName(member)))
    setQuery(null)
    caret.current = before.length
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (suggestions.length === 0) return
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault()
      const step = e.key === 'ArrowDown' ? 1 : -1
      setActive((active + step + suggestions.length) % suggestions.length)
    } else if (e.key === 'Enter' || e.key === 'Tab') {
      e.preventDefault()
      choose(suggestions[active])
    } else if (e.key === 'Escape') {
      e.preventDefault() // ferme la liste, pas la fenêtre
      setQuery(null)
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault()
    const body = text.trim()
    if (!body) return
    // Seules les mentions encore présentes dans le texte sont envoyées.
    const mentions = [...picked].filter(([, name]) => body.includes(`@${name}`)).map(([id]) => id)
    add.mutate(
      { body, mentions },
      {
        onSuccess: () => {
          setText('')
          setPicked(new Map())
        },
      },
    )
  }

  return (
    <form className="comment-form" onSubmit={submit}>
      <label htmlFor="new-comment" className="visually-hidden">
        Nouveau commentaire
      </label>
      <div className="comment-form__field">
        <textarea
          id="new-comment"
          ref={field}
          rows={3}
          maxLength={2000}
          placeholder="Écrire un commentaire… Tapez @ pour mentionner quelqu’un."
          value={text}
          role="combobox"
          aria-expanded={suggestions.length > 0}
          aria-controls="mention-list"
          aria-autocomplete="list"
          onChange={(e) => {
            setText(e.target.value)
            readQuery(e.target.value, e.target.selectionStart)
          }}
          onKeyDown={onKeyDown}
          onBlur={() => setTimeout(() => setQuery(null), 150)}
        />
        {suggestions.length > 0 && (
          <ul
            className="mention-list"
            id="mention-list"
            role="listbox"
            aria-label="Membres à mentionner"
          >
            {suggestions.map((m, i) => (
              <li
                key={m.id}
                role="option"
                aria-selected={i === active}
                className={
                  i === active
                    ? 'mention-list__item mention-list__item--active'
                    : 'mention-list__item'
                }
                onMouseDown={(e) => {
                  e.preventDefault()
                  choose(m)
                }}
              >
                <Avatar name={memberName(m)} size="tiny" />
                {memberName(m)}
              </li>
            ))}
          </ul>
        )}
      </div>
      {add.isError && <Alert>{errorMessage(add.error)}</Alert>}
      <div className="comment-form__actions">
        <span className="task-drawer__hint">
          Les personnes mentionnées et les abonnés sont prévenus dans leurs alertes.
        </span>
        <button
          className="button button--primary button--small"
          type="submit"
          disabled={add.isPending || !text.trim()}
        >
          Publier
        </button>
      </div>
    </form>
  )
}

// ---------- Abonnés ----------

function FollowButton({ spaceId, detail }: { spaceId: string; detail: TaskDetail }) {
  const toggle = useFollowTask(spaceId, detail.task.id)
  return (
    <button
      type="button"
      className={
        detail.following ? 'button button--small follow follow--on' : 'button button--small follow'
      }
      aria-pressed={detail.following}
      disabled={toggle.isPending}
      onClick={() => toggle.mutate(!detail.following)}
    >
      {detail.following ? '✓ Abonné' : 'Suivre'}
    </button>
  )
}

function Followers({ detail }: { detail: TaskDetail }) {
  return (
    <Section title="Abonnés" count={detail.followers.length || undefined}>
      {detail.followers.length === 0 ? (
        <p className="muted">Personne ne suit cette tâche.</p>
      ) : (
        <ul className="followers">
          {detail.followers.map((f) => (
            <li key={f.user_id}>
              <Avatar name={f.name} size="tiny" />
              {f.name}
            </li>
          ))}
        </ul>
      )}
      <p className="task-drawer__hint">
        Les abonnés sont prévenus des commentaires et des changements (statut, échéance,
        responsable).
      </p>
    </Section>
  )
}
