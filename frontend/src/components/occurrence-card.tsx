import { useState, type FormEvent } from 'react'
import { Link } from 'react-router'
import { errorMessage, type Occurrence, type Project } from '../api/client'
import {
  useCloseOccurrence,
  useFollowUp,
  useReopenOccurrence,
  useUpdateOccurrence,
} from '../api/queries'
import { formatDay } from '../labels'
import { Alert, StatusPill, type Tone } from './ui'

/** Une occurrence de routine (étape F5, RIT01) : checklist courte, résultat à produire,
 * clôture (contrôles obligatoires ou exception motivée), report de cette occurrence seulement,
 * et constats transformés en tâche ou en décision. */

function stateOf(o: Occurrence): { label: string; tone: Tone } {
  if (o.state === 'cancelled') return { label: 'Annulée', tone: 'neutral' }
  if (o.state === 'done') {
    return o.exception_reason
      ? { label: 'Faite avec exception', tone: 'warn' }
      : { label: 'Faite', tone: 'ok' }
  }
  return o.late ? { label: 'En retard', tone: 'danger' } : { label: 'À faire', tone: 'info' }
}

type Mode = null | 'close' | 'postpone' | 'cancel' | 'task' | 'decision'

export function OccurrenceCard({
  spaceId,
  occurrence: o,
  canWrite,
  projects,
  today,
  showDate = false,
}: {
  spaceId: string
  occurrence: Occurrence
  canWrite: boolean
  projects: Project[]
  today: string
  showDate?: boolean
}) {
  const update = useUpdateOccurrence(spaceId)
  const close = useCloseOccurrence(spaceId)
  const reopen = useReopenOccurrence(spaceId)
  const followUp = useFollowUp(spaceId)
  const [open, setOpen] = useState(false)
  const [mode, setMode] = useState<Mode>(null)
  const [result, setResult] = useState(o.result ?? '')
  const [reason, setReason] = useState('')
  const [date, setDate] = useState(o.due_date)
  const [title, setTitle] = useState('')
  const [projectId, setProjectId] = useState('')
  const [due, setDue] = useState('')
  const state = stateOf(o)
  const planned = o.state === 'planned'
  const editable = canWrite && planned
  const error = update.error ?? close.error ?? reopen.error ?? followUp.error
  const id = `occ-${o.id}`

  function done() {
    setMode(null)
    setReason('')
  }

  function submit(event: FormEvent) {
    event.preventDefault()
    if (mode === 'close') {
      close.mutate(
        {
          occurrence: o,
          state: 'done',
          result: result.trim() || null,
          exception_reason: o.missing_mandatory.length ? reason.trim() : null,
        },
        { onSuccess: done },
      )
    } else if (mode === 'cancel') {
      close.mutate(
        { occurrence: o, state: 'cancelled', cancel_reason: reason.trim() },
        { onSuccess: done },
      )
    } else if (mode === 'postpone') {
      update.mutate(
        { occurrence: o, due_date: date, postpone_reason: reason.trim() },
        { onSuccess: done },
      )
    } else if (mode === 'task' || mode === 'decision') {
      followUp.mutate(
        {
          occurrenceId: o.id,
          kind: mode,
          title: title.trim(),
          project_id: projectId || null,
          due_date: due || null,
        },
        {
          onSuccess: () => {
            setTitle('')
            setDue('')
            done()
          },
        },
      )
    }
  }

  return (
    <article className={`occ occ--${o.late ? 'late' : o.state}`} aria-labelledby={`${id}-title`}>
      <button
        type="button"
        className="occ__head"
        aria-expanded={open}
        aria-controls={`${id}-body`}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="occ__time">{o.time_of_day ?? '—'}</span>
        <span className="occ__main">
          <span className="occ__title" id={`${id}-title`}>
            {o.routine_title}
          </span>
          <span className="occ__meta">
            {(showDate || o.due_date !== today) && <>{formatDay(o.due_date)} · </>}
            {o.duration_minutes ? `${o.duration_minutes} min · ` : ''}
            {o.owner.name ?? 'Sans responsable'}
            {o.postponed && ` · reportée du ${formatDay(o.scheduled_date)}`}
            {o.checklist.length > 0 &&
              ` · ${o.checklist.filter((c) => o.checks[c.id]).length}/${o.checklist.length} contrôles`}
          </span>
        </span>
        <StatusPill tone={state.tone}>{state.label}</StatusPill>
      </button>

      {open && (
        <div className="occ__body" id={`${id}-body`}>
          {o.checklist.length > 0 && (
            <fieldset className="occ__checks">
              <legend>Checklist</legend>
              {o.checklist.map((c) => (
                <label key={c.id} className="checkbox">
                  <input
                    type="checkbox"
                    checked={Boolean(o.checks[c.id])}
                    disabled={!editable || update.isPending}
                    onChange={(e) =>
                      update.mutate({ occurrence: o, checks: { [c.id]: e.target.checked } })
                    }
                  />
                  {c.label}
                  {c.mandatory && <span className="occ__mandatory"> · obligatoire</span>}
                </label>
              ))}
            </fieldset>
          )}
          {o.expected_output && (
            <p className="field__hint">Résultat attendu : {o.expected_output}</p>
          )}
          {editable ? (
            <div className="field">
              <label htmlFor={`${id}-result`}>Résultat / constat</label>
              <textarea
                id={`${id}-result`}
                rows={2}
                maxLength={4000}
                value={result}
                onChange={(e) => setResult(e.target.value)}
                onBlur={() =>
                  result.trim() !== (o.result ?? '') &&
                  update.mutate({ occurrence: o, result: result.trim() || null })
                }
              />
            </div>
          ) : (
            o.result && <p className="occ__result">{o.result}</p>
          )}
          {o.postpone_reason && <p className="muted">Motif du report : {o.postpone_reason}</p>}
          {o.exception_reason && <p className="muted">Exception : {o.exception_reason}</p>}
          {o.cancel_reason && <p className="muted">Motif d’annulation : {o.cancel_reason}</p>}

          {o.links.length > 0 && (
            <ul className="occ__links">
              {o.links.map((l) => (
                <li key={l.id}>
                  {l.kind === 'task' ? 'Tâche' : 'Décision'} :{' '}
                  {l.kind === 'task' && l.project_id ? (
                    <Link to={`/espaces/${spaceId}/projets/${l.project_id}?tache=${l.id}`}>
                      {l.title}
                    </Link>
                  ) : l.kind === 'decision' ? (
                    <Link to={`/espaces/${spaceId}/decisions`}>{l.title}</Link>
                  ) : (
                    l.title
                  )}
                </li>
              ))}
            </ul>
          )}

          {mode && (
            <form className="occ__form" onSubmit={submit}>
              {mode === 'close' && o.missing_mandatory.length > 0 && (
                <div className="field">
                  <Alert tone="warn">
                    Contrôles obligatoires non faits : {o.missing_mandatory.join(', ')}. Cochez-les,
                    ou motivez l’exception (elle restera visible).
                  </Alert>
                  <label htmlFor={`${id}-exception`}>Motif de l’exception</label>
                  <input
                    id={`${id}-exception`}
                    required
                    minLength={3}
                    value={reason}
                    onChange={(e) => setReason(e.target.value)}
                  />
                </div>
              )}
              {mode === 'postpone' && (
                <>
                  <div className="field">
                    <label htmlFor={`${id}-date`}>Nouvelle date (cette occurrence seulement)</label>
                    <input
                      id={`${id}-date`}
                      type="date"
                      required
                      value={date}
                      onChange={(e) => setDate(e.target.value)}
                    />
                  </div>
                  <div className="field">
                    <label htmlFor={`${id}-reason`}>Motif du report</label>
                    <input
                      id={`${id}-reason`}
                      required
                      value={reason}
                      onChange={(e) => setReason(e.target.value)}
                    />
                  </div>
                </>
              )}
              {mode === 'cancel' && (
                <div className="field">
                  <label htmlFor={`${id}-cancel`}>Motif de l’annulation</label>
                  <input
                    id={`${id}-cancel`}
                    required
                    value={reason}
                    onChange={(e) => setReason(e.target.value)}
                  />
                </div>
              )}
              {(mode === 'task' || mode === 'decision') && (
                <>
                  <div className="field">
                    <label htmlFor={`${id}-fu-title`}>
                      {mode === 'task' ? 'Tâche à créer' : 'Décision à consigner (brouillon)'}
                    </label>
                    <input
                      id={`${id}-fu-title`}
                      required
                      maxLength={200}
                      value={title}
                      onChange={(e) => setTitle(e.target.value)}
                    />
                  </div>
                  <div className="field">
                    <label htmlFor={`${id}-fu-project`}>Projet</label>
                    <select
                      id={`${id}-fu-project`}
                      required={mode === 'task'}
                      value={projectId}
                      onChange={(e) => setProjectId(e.target.value)}
                    >
                      <option value="">{mode === 'task' ? '— Choisir —' : 'Aucun projet'}</option>
                      {projects.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.title}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="field">
                    <label htmlFor={`${id}-fu-due`}>Échéance</label>
                    <input
                      id={`${id}-fu-due`}
                      type="date"
                      value={due}
                      onChange={(e) => setDue(e.target.value)}
                    />
                  </div>
                </>
              )}
              <div className="item-form__actions">
                <button
                  className="button button--primary button--small"
                  disabled={close.isPending || update.isPending || followUp.isPending}
                >
                  {mode === 'close'
                    ? 'Clôturer comme faite'
                    : mode === 'postpone'
                      ? 'Reporter'
                      : mode === 'cancel'
                        ? 'Annuler l’occurrence'
                        : 'Créer'}
                </button>
                <button type="button" className="button button--ghost button--small" onClick={done}>
                  Fermer
                </button>
              </div>
            </form>
          )}

          {error && <Alert>{errorMessage(error)}</Alert>}

          {canWrite && !mode && (
            <div className="occ__actions">
              {planned ? (
                <>
                  <button
                    type="button"
                    className="button button--small button--primary"
                    onClick={() => setMode('close')}
                  >
                    Clôturer
                  </button>
                  <button
                    type="button"
                    className="button button--small"
                    onClick={() => setMode('task')}
                  >
                    + Tâche
                  </button>
                  <button
                    type="button"
                    className="button button--small"
                    onClick={() => setMode('decision')}
                  >
                    + Décision
                  </button>
                  <button
                    type="button"
                    className="button button--small button--ghost"
                    onClick={() => setMode('postpone')}
                  >
                    Reporter
                  </button>
                  <button
                    type="button"
                    className="button button--small button--ghost"
                    onClick={() => setMode('cancel')}
                  >
                    Annuler
                  </button>
                </>
              ) : (
                <button
                  type="button"
                  className="button button--small button--ghost"
                  disabled={reopen.isPending}
                  onClick={() => reopen.mutate(o)}
                >
                  Rouvrir
                </button>
              )}
            </div>
          )}
        </div>
      )}
    </article>
  )
}
