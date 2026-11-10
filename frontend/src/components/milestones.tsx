import { useState, type FormEvent } from 'react'
import { errorMessage, type Milestone, type Project, type Task } from '../api/client'
import {
  useCloseMilestone,
  useCreateMilestone,
  useMembers,
  useMilestones,
  useMilestoneTasks,
  useReopenMilestone,
  useSections,
  useTasks,
  useUpdateMilestone,
} from '../api/queries'
import { formatDay, isClosedProject } from '../labels'
import { personPayload, personValue } from '../person'
import { PersonField, type PersonValue } from './person-field'
import { Alert, Skeleton, StatusPill, type Tone } from './ui'

/** Étape F2 (cahier V2, TCH04) : les jalons d'un projet. Un jalon est un résultat de passage
 * daté (porteur, date engagée, critère, tâches dont il dépend). Repousser sa date demande un
 * motif ; après deux reports, une revue de cadrage est demandée avant toute nouvelle date. */

const STATE: Record<Milestone['state'], { label: string; tone: Tone }> = {
  planned: { label: 'À venir', tone: 'info' },
  reached: { label: 'Atteint', tone: 'ok' },
  missed: { label: 'Manqué', tone: 'danger' },
  cancelled: { label: 'Annulé', tone: 'neutral' },
}

const closedTask = (t: { status: string }) => t.status === 'done' || t.status === 'cancelled'

function TaskPicker({
  tasks,
  value,
  onChange,
}: {
  tasks: Task[]
  value: string[]
  onChange: (ids: string[]) => void
}) {
  if (tasks.length === 0) {
    return <p className="field__hint">Aucune tâche dans ce projet pour l’instant.</p>
  }
  return (
    <fieldset className="milestone-picker">
      <legend>Tâches dont dépend le jalon</legend>
      {tasks.map((t) => (
        <label key={t.id} className="milestone-picker__item">
          <input
            type="checkbox"
            checked={value.includes(t.id)}
            onChange={(e) =>
              onChange(e.target.checked ? [...value, t.id] : value.filter((id) => id !== t.id))
            }
          />
          <span className={closedTask(t) ? 'muted' : undefined}>{t.title}</span>
        </label>
      ))}
    </fieldset>
  )
}

function MilestoneForm({
  spaceId,
  project,
  milestone,
  onDone,
}: {
  spaceId: string
  project: Project
  milestone?: Milestone
  onDone: () => void
}) {
  const create = useCreateMilestone(spaceId, project.id)
  const update = useUpdateMilestone(spaceId, project.id)
  const links = useMilestoneTasks(spaceId, project.id)
  const members = useMembers(spaceId)
  const sections = useSections(spaceId, project.id)
  const tasks = useTasks(spaceId, project.id)
  const [title, setTitle] = useState(milestone?.title ?? '')
  const [due, setDue] = useState(milestone?.due_date ?? '')
  const [criterion, setCriterion] = useState(milestone?.criterion ?? '')
  const [owner, setOwner] = useState<PersonValue>(
    milestone ? personValue(milestone.owner) : { memberId: null, label: '' },
  )
  const [section, setSection] = useState(milestone?.section_id ?? '')
  const [critical, setCritical] = useState(milestone?.critical ?? false)
  const [taskIds, setTaskIds] = useState<string[]>(milestone?.tasks.map((t) => t.id) ?? [])
  const activeSections = (sections.data ?? []).filter((s) => !s.archived)
  const candidates = (tasks.data ?? []).filter((t) => !t.parent_id)
  const pending = create.isPending || update.isPending || links.isPending
  const error = create.error ?? update.error ?? links.error

  function submit(event: FormEvent) {
    event.preventDefault()
    const fields = {
      title: title.trim(),
      criterion: criterion.trim() || null,
      section_id: section || null,
      critical,
      ...personPayload(owner, 'owner'),
    }
    if (!milestone) {
      create.mutate({ ...fields, due_date: due, task_ids: taskIds }, { onSuccess: onDone })
      return
    }
    const before = milestone.tasks
      .map((t) => t.id)
      .sort()
      .join()
    const tasksChanged = before !== [...taskIds].sort().join()
    update.mutate(
      { milestone, changes: fields },
      {
        onSuccess: (saved) =>
          tasksChanged
            ? links.mutate({ milestone: saved, taskIds }, { onSuccess: onDone })
            : onDone(),
      },
    )
  }

  return (
    <form
      className="form-grid milestone-form"
      onSubmit={submit}
      aria-label={milestone ? 'Modifier le jalon' : 'Nouveau jalon'}
    >
      <div className="field form-grid__full">
        <label htmlFor="ms-title">Jalon *</label>
        <input
          id="ms-title"
          autoFocus
          required
          maxLength={200}
          placeholder="Ex. : Salle confirmée"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
        />
      </div>
      {!milestone && (
        <div className="field">
          <label htmlFor="ms-due">Date engagée *</label>
          <input
            id="ms-due"
            type="date"
            required
            value={due}
            onChange={(e) => setDue(e.target.value)}
          />
        </div>
      )}
      <PersonField
        id="ms-owner"
        label="Porteur"
        members={members.data ?? []}
        value={owner}
        onChange={setOwner}
      />
      <div className="field form-grid__full">
        <label htmlFor="ms-criterion">Critère de passage</label>
        <input
          id="ms-criterion"
          maxLength={500}
          placeholder="Ce qui prouve que le jalon est atteint (ex. : contrat signé)"
          value={criterion}
          onChange={(e) => setCriterion(e.target.value)}
        />
      </div>
      {activeSections.length > 0 && (
        <div className="field">
          <label htmlFor="ms-section">Section</label>
          <select id="ms-section" value={section} onChange={(e) => setSection(e.target.value)}>
            <option value="">Sans section</option>
            {activeSections.map((s) => (
              <option key={s.id} value={s.id}>
                {s.title}
              </option>
            ))}
          </select>
        </div>
      )}
      <label className="field field--check">
        <input type="checkbox" checked={critical} onChange={(e) => setCritical(e.target.checked)} />
        Jalon critique
        <span className="field__hint">
          Ses alertes de risque vont aussi aux propriétaires de l’espace.
        </span>
      </label>
      <div className="form-grid__full">
        <TaskPicker tasks={candidates} value={taskIds} onChange={setTaskIds} />
      </div>
      {error && (
        <div className="form-grid__full">
          <Alert>{errorMessage(error)}</Alert>
        </div>
      )}
      <div className="form-grid__full form-actions">
        <button className="button button--primary" type="submit" disabled={pending}>
          {milestone ? 'Enregistrer' : 'Ajouter le jalon'}
        </button>
        <button className="button button--ghost" type="button" onClick={onDone}>
          Annuler
        </button>
      </div>
    </form>
  )
}

function PostponeForm({
  spaceId,
  projectId,
  milestone,
  onDone,
}: {
  spaceId: string
  projectId: string
  milestone: Milestone
  onDone: () => void
}) {
  const update = useUpdateMilestone(spaceId, projectId)
  const [due, setDue] = useState('')
  const [reason, setReason] = useState('')
  const [review, setReview] = useState('')
  const needsReview = milestone.reframe_needed

  function submit(event: FormEvent) {
    event.preventDefault()
    update.mutate(
      {
        milestone,
        changes: {
          due_date: due,
          postpone_reason: reason.trim(),
          ...(needsReview ? { reframe_note: review.trim() } : {}),
        },
      },
      { onSuccess: onDone },
    )
  }

  return (
    <form className="form-grid milestone-form" onSubmit={submit} aria-label="Reporter le jalon">
      {needsReview && (
        <div className="form-grid__full">
          <Alert tone="warn">
            Ce jalon a déjà été reporté {milestone.postpone_count} fois. Avant une nouvelle date,
            faites une <strong>revue de cadrage</strong> : qu’est-ce qui change, et pourquoi la
            nouvelle date est-elle tenable ?
          </Alert>
        </div>
      )}
      <div className="field">
        <label htmlFor="pp-due">Nouvelle date *</label>
        <input
          id="pp-due"
          type="date"
          required
          min={milestone.due_date}
          value={due}
          onChange={(e) => setDue(e.target.value)}
        />
      </div>
      <div className="field">
        <label htmlFor="pp-reason">Motif du report *</label>
        <input
          id="pp-reason"
          required
          maxLength={500}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
      </div>
      {needsReview && (
        <div className="field form-grid__full">
          <label htmlFor="pp-review">Revue de cadrage *</label>
          <textarea
            id="pp-review"
            required
            rows={3}
            maxLength={2000}
            value={review}
            onChange={(e) => setReview(e.target.value)}
          />
        </div>
      )}
      <p className="field__hint form-grid__full">
        Date engagée actuelle : {formatDay(milestone.due_date)}
        {milestone.original_due_date &&
          ` · date d’origine : ${formatDay(milestone.original_due_date)}`}
      </p>
      {update.isError && (
        <div className="form-grid__full">
          <Alert>{errorMessage(update.error)}</Alert>
        </div>
      )}
      <div className="form-grid__full form-actions">
        <button className="button button--primary" type="submit" disabled={update.isPending}>
          Reporter
        </button>
        <button className="button button--ghost" type="button" onClick={onDone}>
          Annuler
        </button>
      </div>
    </form>
  )
}

function CloseForm({
  spaceId,
  projectId,
  milestone,
  initial,
  onDone,
}: {
  spaceId: string
  projectId: string
  milestone: Milestone
  initial: 'reached' | 'missed' | 'cancelled'
  onDone: () => void
}) {
  const close = useCloseMilestone(spaceId, projectId)
  const [state, setState] = useState(initial)
  const [note, setNote] = useState('')
  const needsNote = state !== 'reached'

  return (
    <form
      className="form-grid milestone-form"
      aria-label="Clôturer le jalon"
      onSubmit={(e) => {
        e.preventDefault()
        close.mutate({ milestone, state, note: note.trim() || null }, { onSuccess: onDone })
      }}
    >
      <div className="field">
        <label htmlFor="cl-state">Résultat</label>
        <select
          id="cl-state"
          value={state}
          onChange={(e) => setState(e.target.value as typeof state)}
        >
          <option value="reached">Atteint</option>
          <option value="missed">Manqué</option>
          <option value="cancelled">Annulé</option>
        </select>
      </div>
      <div className="field">
        <label htmlFor="cl-note">{needsNote ? 'Motif *' : 'Preuve (facultatif)'}</label>
        <input
          id="cl-note"
          required={needsNote}
          maxLength={1000}
          placeholder={
            needsNote
              ? 'Pourquoi le jalon est manqué ou annulé'
              : milestone.criterion
                ? `Critère : ${milestone.criterion}`
                : 'Ex. : contrat signé le 3'
          }
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
      </div>
      {close.isError && (
        <div className="form-grid__full">
          <Alert>{errorMessage(close.error)}</Alert>
        </div>
      )}
      <div className="form-grid__full form-actions">
        <button className="button button--primary" type="submit" disabled={close.isPending}>
          Enregistrer
        </button>
        <button className="button button--ghost" type="button" onClick={onDone}>
          Annuler
        </button>
      </div>
    </form>
  )
}

function MilestoneRow({
  milestone,
  spaceId,
  project,
  canWrite,
}: {
  milestone: Milestone
  spaceId: string
  project: Project
  canWrite: boolean
}) {
  const reopen = useReopenMilestone(spaceId, project.id)
  const [mode, setMode] = useState<null | 'edit' | 'postpone' | 'reached' | 'missed' | 'cancelled'>(
    null,
  )
  const state = STATE[milestone.state]
  const open = milestone.state === 'planned'
  const done = milestone.tasks.filter(closedTask).length
  const flag = milestone.late ? 'late' : milestone.at_risk ? 'risk' : null

  if (mode === 'edit') {
    return (
      <li className="milestone">
        <MilestoneForm
          spaceId={spaceId}
          project={project}
          milestone={milestone}
          onDone={() => setMode(null)}
        />
      </li>
    )
  }

  return (
    <li className={`milestone milestone--${milestone.state}${flag ? ` milestone--${flag}` : ''}`}>
      <div className="milestone__main">
        <span className="milestone__diamond" aria-hidden="true">
          ◆
        </span>
        <div className="milestone__text">
          <div className="milestone__title">
            <strong>{milestone.title}</strong>
            <StatusPill tone={state.tone}>{state.label}</StatusPill>
            {milestone.critical && <span className="task-badge task-badge--urgent">Critique</span>}
            {milestone.late && <span className="task-badge task-badge--late">En retard</span>}
            {milestone.at_risk && <span className="task-badge task-badge--high">⚠ À risque</span>}
            {milestone.postpone_count > 0 && (
              <span className="task-badge task-badge--postponed">
                ↷ Reporté {milestone.postpone_count} fois
              </span>
            )}
            {milestone.reframe_needed && (
              <span className="task-badge task-badge--blocked">Revue de cadrage</span>
            )}
          </div>
          <p className="milestone__meta">
            <span className={milestone.late ? 'due__date--late' : undefined}>
              {formatDay(milestone.due_date)}
            </span>
            {milestone.original_due_date && (
              <span className="muted">
                {' '}
                (prévu au départ le {formatDay(milestone.original_due_date)})
              </span>
            )}
            {' · '}
            {milestone.owner.name ?? <span className="muted">sans porteur</span>}
            {milestone.tasks.length > 0 &&
              ` · ${done}/${milestone.tasks.length} tâche(s) terminée(s)`}
          </p>
          {milestone.criterion && (
            <p className="milestone__meta muted">Critère : {milestone.criterion}</p>
          )}
          {milestone.risk_reasons.length > 0 && (
            <p className="milestone__risk">⚠ {milestone.risk_reasons.join(' · ')}</p>
          )}
          {milestone.close_note && !open && (
            <p className="milestone__meta">
              {milestone.state === 'reached' ? 'Preuve' : 'Motif'} : {milestone.close_note}
            </p>
          )}
          {milestone.reframe_note && open && (
            <p className="milestone__meta muted">Revue de cadrage : {milestone.reframe_note}</p>
          )}
        </div>
        {canWrite && !mode && (
          <div className="milestone__actions">
            {open ? (
              <>
                <button
                  type="button"
                  className="button button--small button--primary"
                  onClick={() => setMode('reached')}
                >
                  ✓ Atteint
                </button>
                <button
                  type="button"
                  className="button button--small"
                  onClick={() => setMode('postpone')}
                >
                  Reporter
                </button>
                <button
                  type="button"
                  className="button button--small button--ghost"
                  onClick={() => setMode('edit')}
                >
                  Modifier
                </button>
                <button
                  type="button"
                  className="button button--small button--ghost"
                  onClick={() => setMode('missed')}
                >
                  Manqué / annulé
                </button>
              </>
            ) : (
              <button
                type="button"
                className="button button--small"
                disabled={reopen.isPending}
                onClick={() => reopen.mutate(milestone)}
              >
                Rouvrir
              </button>
            )}
          </div>
        )}
      </div>
      {mode === 'postpone' && (
        <PostponeForm
          spaceId={spaceId}
          projectId={project.id}
          milestone={milestone}
          onDone={() => setMode(null)}
        />
      )}
      {(mode === 'reached' || mode === 'missed' || mode === 'cancelled') && (
        <CloseForm
          spaceId={spaceId}
          projectId={project.id}
          milestone={milestone}
          initial={mode}
          onDone={() => setMode(null)}
        />
      )}
      {reopen.isError && <Alert>{errorMessage(reopen.error)}</Alert>}
    </li>
  )
}

/** Panneau « Jalons » de la fiche projet. */
export function MilestonesSection({
  project,
  spaceId,
  canWrite,
}: {
  project: Project
  spaceId: string
  canWrite: boolean
}) {
  const milestones = useMilestones(spaceId, project.id)
  const [adding, setAdding] = useState(false)
  const closedProject = isClosedProject(project.status)
  const writable = canWrite && !closedProject
  const all = milestones.data ?? []
  const upcoming = all.filter((m) => m.state === 'planned')
  const closed = all.filter((m) => m.state !== 'planned')
  const risky = upcoming.filter((m) => m.at_risk || m.late).length

  return (
    <section className="card-panel" aria-labelledby="milestones-title">
      <div className="card-panel__head">
        <h2 id="milestones-title">
          Jalons{' '}
          <span className="count">
            {upcoming.length} à venir{risky > 0 ? ` · ${risky} à surveiller` : ''}
          </span>
        </h2>
        {writable && !adding && (
          <button type="button" className="button button--small" onClick={() => setAdding(true)}>
            + Jalon
          </button>
        )}
      </div>
      {adding && (
        <MilestoneForm spaceId={spaceId} project={project} onDone={() => setAdding(false)} />
      )}
      {milestones.isPending && <Skeleton lines={2} />}
      {milestones.isError && <Alert>{errorMessage(milestones.error)}</Alert>}
      {milestones.data && all.length === 0 && !adding && (
        <p className="muted">
          Aucun jalon. Un jalon marque un résultat de passage daté (ex. « Salle confirmée »), pas
          une tâche.
        </p>
      )}
      {upcoming.length > 0 && (
        <ul className="milestone-list">
          {upcoming.map((m) => (
            <MilestoneRow
              key={m.id}
              milestone={m}
              spaceId={spaceId}
              project={project}
              canWrite={writable}
            />
          ))}
        </ul>
      )}
      {closed.length > 0 && (
        <details className="task-closed">
          <summary>{closed.length} jalon(s) clôturé(s)</summary>
          <ul className="milestone-list">
            {closed.map((m) => (
              <MilestoneRow
                key={m.id}
                milestone={m}
                spaceId={spaceId}
                project={project}
                canWrite={writable}
              />
            ))}
          </ul>
        </details>
      )}
    </section>
  )
}
