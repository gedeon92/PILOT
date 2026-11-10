import { useState, type FormEvent } from 'react'
import { Link, useOutletContext, useSearchParams } from 'react-router'
import { canWriteSpace, errorMessage, type Decision, type Meeting } from '../api/client'
import {
  useCreateDecision,
  useCreateMeeting,
  useDecisionAction,
  useDecisions,
  useMeetings,
  useMembers,
  useProjects,
  useUpdateDecision,
  useUpdateMeeting,
} from '../api/queries'
import { PersonField, type PersonValue } from '../components/person-field'
import { Alert, PageHeader, Skeleton, StatusPill, type Tone } from '../components/ui'
import { formatDay, formatMoment, isClosedProject } from '../labels'
import { personValue } from '../person'
import type { SpaceContext } from './space-layout'

/** Étape F3 (cahier V2, DEC01–DEC05) : registre des décisions et suivi des relevés.
 * Une décision est distincte des tâches qui l'exécutent ; elle reste en brouillon tant qu'il
 * manque un responsable nommé, une échéance ou un critère observable. */

const STATE: Record<Decision['state'], { label: string; tone: Tone }> = {
  draft: { label: 'Brouillon', tone: 'neutral' },
  open: { label: 'À exécuter', tone: 'info' },
  done: { label: 'Exécutée', tone: 'ok' },
  cancelled: { label: 'Caduque', tone: 'neutral' },
}

const MINUTES: Record<
  Meeting['minutes_state'],
  { label: string; next?: Meeting['minutes_state'] }
> = {
  to_write: { label: 'Relevé à rédiger', next: 'written' },
  written: { label: 'Relevé rédigé', next: 'validated' },
  validated: { label: 'Relevé validé', next: 'sent' },
  sent: { label: 'Relevé envoyé' },
}
const NEXT_LABEL: Record<string, string> = {
  written: 'Marquer rédigé',
  validated: 'Marquer validé',
  sent: 'Déclarer envoyé',
}

function payload(prefix: 'decider' | 'executor', value: PersonValue) {
  return value.memberId
    ? { [`${prefix}_member_id`]: value.memberId, [`${prefix}_label`]: null }
    : { [`${prefix}_member_id`]: null, [`${prefix}_label`]: value.label.trim() || null }
}

function DecisionForm({
  spaceId,
  decision,
  meetingId,
  onDone,
}: {
  spaceId: string
  decision?: Decision
  meetingId?: string | null
  onDone: () => void
}) {
  const create = useCreateDecision(spaceId)
  const update = useUpdateDecision(spaceId)
  const members = useMembers(spaceId)
  const projects = useProjects(spaceId)
  const meetings = useMeetings(spaceId)
  const [statement, setStatement] = useState(decision?.statement ?? '')
  const [project, setProject] = useState(decision?.project?.id ?? '')
  const [meeting, setMeeting] = useState(decision?.meeting?.id ?? meetingId ?? '')
  const [source, setSource] = useState(decision?.source ?? '')
  const [decider, setDecider] = useState<PersonValue>(
    decision ? personValue(decision.decider) : { memberId: null, label: '' },
  )
  const [executor, setExecutor] = useState<PersonValue>(
    decision ? personValue(decision.executor) : { memberId: null, label: '' },
  )
  const [due, setDue] = useState(decision?.due_date ?? '')
  const [criterion, setCriterion] = useState(decision?.criterion ?? '')
  const [secret, setSecret] = useState(decision?.private ?? false)
  const error = create.error ?? update.error
  const pending = create.isPending || update.isPending
  const openProjects = (projects.data ?? []).filter(
    (p) => !isClosedProject(p.status) && (p.my_role === 'owner' || p.my_role === 'contributor'),
  )

  function fields() {
    return {
      statement: statement.trim(),
      project_id: project || null,
      meeting_id: meeting || null,
      source: source.trim() || null,
      due_date: due || null,
      criterion: criterion.trim() || null,
      private: secret,
      ...payload('decider', decider),
      ...payload('executor', executor),
    }
  }

  function submit(event: FormEvent, validate = false) {
    event.preventDefault()
    if (decision) {
      update.mutate({ decision, changes: fields() }, { onSuccess: onDone })
    } else {
      create.mutate({ ...fields(), validate_now: validate }, { onSuccess: onDone })
    }
  }

  return (
    <form
      className="form-grid decision-form"
      onSubmit={(e) => submit(e)}
      aria-label={decision ? 'Modifier la décision' : 'Nouvelle décision'}
    >
      <div className="field form-grid__full">
        <label htmlFor="dc-statement">Décision *</label>
        <textarea
          id="dc-statement"
          autoFocus
          required
          rows={2}
          maxLength={2000}
          placeholder="Ex. : Moussa envoie le devis au client"
          value={statement}
          onChange={(e) => setStatement(e.target.value)}
        />
      </div>
      <PersonField
        id="dc-executor"
        label="Responsable d’exécution"
        members={members.data ?? []}
        value={executor}
        onChange={setExecutor}
      />
      <div className="field">
        <label htmlFor="dc-due">Échéance</label>
        <input id="dc-due" type="date" value={due} onChange={(e) => setDue(e.target.value)} />
      </div>
      <div className="field form-grid__full">
        <label htmlFor="dc-criterion">Critère observable</label>
        <input
          id="dc-criterion"
          maxLength={500}
          placeholder="Ce qui prouvera l’exécution (ex. : devis envoyé et accusé de réception)"
          value={criterion}
          onChange={(e) => setCriterion(e.target.value)}
        />
      </div>
      <PersonField
        id="dc-decider"
        label="Décideur"
        members={members.data ?? []}
        value={decider}
        onChange={setDecider}
      />
      <div className="field">
        <label htmlFor="dc-project">Projet lié</label>
        <select id="dc-project" value={project} onChange={(e) => setProject(e.target.value)}>
          <option value="">Aucun</option>
          {openProjects.map((p) => (
            <option key={p.id} value={p.id}>
              {p.title}
            </option>
          ))}
        </select>
      </div>
      <div className="field">
        <label htmlFor="dc-meeting">Réunion</label>
        <select id="dc-meeting" value={meeting} onChange={(e) => setMeeting(e.target.value)}>
          <option value="">Aucune</option>
          {(meetings.data ?? []).map((m) => (
            <option key={m.id} value={m.id}>
              {m.title} — {formatMoment(m.ended_at)}
            </option>
          ))}
        </select>
      </div>
      <div className="field">
        <label htmlFor="dc-source">Autre source</label>
        <input
          id="dc-source"
          maxLength={200}
          placeholder="Ex. : appel avec le client"
          value={source}
          onChange={(e) => setSource(e.target.value)}
        />
      </div>
      <label className="field field--check form-grid__full">
        <input type="checkbox" checked={secret} onChange={(e) => setSecret(e.target.checked)} />
        Confidentielle
        <span className="field__hint">
          Visible seulement des propriétaires, de son auteur, du décideur et du responsable.
        </span>
      </label>
      {error && (
        <div className="form-grid__full">
          <Alert>{errorMessage(error)}</Alert>
        </div>
      )}
      <div className="form-grid__full form-actions">
        {decision ? (
          <button className="button button--primary" type="submit" disabled={pending}>
            Enregistrer
          </button>
        ) : (
          <>
            <button
              className="button button--primary"
              type="button"
              disabled={pending}
              onClick={(e) => submit(e as unknown as FormEvent, true)}
            >
              Enregistrer et valider
            </button>
            <button className="button" type="submit" disabled={pending}>
              Garder en brouillon
            </button>
          </>
        )}
        <button className="button button--ghost" type="button" onClick={onDone}>
          Annuler
        </button>
      </div>
      {!decision && (
        <p className="field__hint form-grid__full">
          Pour valider, il faut un responsable nommé (pas « l’équipe »), une échéance et un critère
          observable. Sinon, la décision reste en brouillon et apparaît dans « À traiter ».
        </p>
      )}
    </form>
  )
}

function DecisionCard({ decision, spaceId }: { decision: Decision; spaceId: string }) {
  const act = useDecisionAction(spaceId, 'Décision enregistrée')
  const [mode, setMode] = useState<null | 'edit' | 'done' | 'cancelled'>(null)
  const [note, setNote] = useState('')
  const state = STATE[decision.state]
  const active = decision.state === 'draft' || decision.state === 'open'
  const write = decision.can_write

  if (mode === 'edit') {
    return (
      <li className="decision">
        <DecisionForm spaceId={spaceId} decision={decision} onDone={() => setMode(null)} />
      </li>
    )
  }
  return (
    <li className={`decision decision--${decision.state}${decision.late ? ' decision--late' : ''}`}>
      <div className="decision__head">
        <strong className="decision__statement">{decision.statement}</strong>
        <span className="decision__badges">
          <StatusPill tone={state.tone}>{state.label}</StatusPill>
          {decision.private && <span className="task-badge">🔒 Confidentielle</span>}
          {decision.late && (
            <span className="task-badge task-badge--late">En retard : à escalader</span>
          )}
          {decision.orphan_days !== null && (
            <span
              className={
                decision.orphan_days >= 30
                  ? 'task-badge task-badge--late'
                  : 'task-badge task-badge--postponed'
              }
            >
              Sans porteur accepté · {decision.orphan_days} j
            </span>
          )}
        </span>
      </div>
      <dl className="decision__facts">
        <div>
          <dt>Responsable</dt>
          <dd>
            {decision.executor.name ?? <span className="muted">à désigner</span>}
            {decision.executor.name && !decision.executor_accepted && (
              <span className="muted"> (n’a pas encore accepté)</span>
            )}
          </dd>
        </div>
        <div>
          <dt>Échéance</dt>
          <dd className={decision.late ? 'due__date--late' : undefined}>
            {decision.due_date ? formatDay(decision.due_date) : <span className="muted">—</span>}
            {decision.reminder_on && decision.state === 'open' && (
              <span className="muted"> · relance le {formatDay(decision.reminder_on)}</span>
            )}
          </dd>
        </div>
        {decision.criterion && (
          <div>
            <dt>Critère</dt>
            <dd>{decision.criterion}</dd>
          </div>
        )}
        {decision.decider.name && (
          <div>
            <dt>Décideur</dt>
            <dd>{decision.decider.name}</dd>
          </div>
        )}
        {(decision.meeting || decision.source) && (
          <div>
            <dt>Source</dt>
            <dd>{decision.meeting?.name ?? decision.source}</dd>
          </div>
        )}
        {decision.project && (
          <div>
            <dt>Projet</dt>
            <dd>
              <Link to={`/espaces/${spaceId}/projets/${decision.project.id}`}>
                {decision.project.name}
              </Link>
            </dd>
          </div>
        )}
        {decision.tasks.length > 0 && (
          <div>
            <dt>Tâches</dt>
            <dd>
              {decision.tasks.map((t, i) => (
                <span key={t.id}>
                  {i > 0 && ', '}
                  <Link to={`/espaces/${spaceId}/projets/${t.project_id}?tache=${t.id}`}>
                    {t.title}
                  </Link>
                  {(t.status === 'done' || t.status === 'cancelled') && ' ✓'}
                </span>
              ))}
            </dd>
          </div>
        )}
        {decision.proof && (
          <div>
            <dt>Preuve</dt>
            <dd>{decision.proof}</dd>
          </div>
        )}
        {decision.cancel_reason && (
          <div>
            <dt>Motif</dt>
            <dd>{decision.cancel_reason}</dd>
          </div>
        )}
      </dl>
      {decision.missing.length > 0 && (
        <p className="decision__missing">
          Pour valider, il manque : {decision.missing.join(', ')}.
        </p>
      )}
      {(mode === 'done' || mode === 'cancelled') && (
        <form
          className="inline-form decision__close"
          onSubmit={(e) => {
            e.preventDefault()
            act.mutate(
              { decision, action: 'close', body: { state: mode, note: note.trim() } },
              { onSuccess: () => setMode(null) },
            )
          }}
        >
          <label htmlFor={`note-${decision.id}`}>
            {mode === 'done' ? 'Preuve d’exécution *' : 'Motif de l’annulation *'}
          </label>
          <input
            id={`note-${decision.id}`}
            required
            autoFocus
            maxLength={1000}
            placeholder={
              mode === 'done'
                ? (decision.criterion ?? 'Ex. : devis envoyé le 12')
                : 'Ex. : devenue sans objet'
            }
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
          <button className="button button--small button--primary" disabled={act.isPending}>
            Enregistrer
          </button>
          <button type="button" className="button button--small" onClick={() => setMode(null)}>
            Annuler
          </button>
        </form>
      )}
      <div className="decision__actions">
        {decision.is_executor && !decision.executor_accepted && active && (
          <button
            type="button"
            className="button button--small button--primary"
            disabled={act.isPending}
            onClick={() => act.mutate({ decision, action: 'accept' })}
          >
            J’accepte cette responsabilité
          </button>
        )}
        {write && !mode && decision.state === 'draft' && (
          <button
            type="button"
            className="button button--small button--primary"
            disabled={act.isPending || decision.missing.length > 0}
            onClick={() => act.mutate({ decision, action: 'validate' })}
          >
            Valider
          </button>
        )}
        {write && !mode && decision.state === 'open' && (
          <>
            <button
              type="button"
              className="button button--small button--primary"
              onClick={() => setMode('done')}
            >
              ✓ Exécutée
            </button>
            {decision.project && (
              <button
                type="button"
                className="button button--small"
                disabled={act.isPending}
                onClick={() => act.mutate({ decision, action: 'tasks' })}
              >
                + Tâche d’exécution
              </button>
            )}
          </>
        )}
        {write && !mode && active && (
          <>
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
              onClick={() => setMode('cancelled')}
            >
              Caduque
            </button>
          </>
        )}
        {write && !active && (
          <button
            type="button"
            className="button button--small"
            disabled={act.isPending}
            onClick={() => act.mutate({ decision, action: 'reopen' })}
          >
            Rouvrir
          </button>
        )}
      </div>
      {act.isError && <Alert>{errorMessage(act.error)}</Alert>}
    </li>
  )
}

function MeetingForm({ spaceId, onDone }: { spaceId: string; onDone: () => void }) {
  const create = useCreateMeeting(spaceId)
  const projects = useProjects(spaceId)
  const [title, setTitle] = useState('')
  const [ended, setEnded] = useState('')
  const [project, setProject] = useState('')
  const [participants, setParticipants] = useState('')
  return (
    <form
      className="form-grid decision-form"
      aria-label="Nouvelle réunion"
      onSubmit={(e) => {
        e.preventDefault()
        create.mutate(
          {
            title: title.trim(),
            ended_at: new Date(ended).toISOString(),
            project_id: project || null,
            participants: participants.trim() || null,
          },
          { onSuccess: onDone },
        )
      }}
    >
      <div className="field">
        <label htmlFor="mt-title">Réunion *</label>
        <input
          id="mt-title"
          autoFocus
          required
          maxLength={200}
          placeholder="Ex. : Comité du lundi"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
        />
      </div>
      <div className="field">
        <label htmlFor="mt-ended">Fin de la réunion *</label>
        <input
          id="mt-ended"
          type="datetime-local"
          required
          value={ended}
          onChange={(e) => setEnded(e.target.value)}
        />
      </div>
      <div className="field">
        <label htmlFor="mt-project">Projet lié</label>
        <select id="mt-project" value={project} onChange={(e) => setProject(e.target.value)}>
          <option value="">Aucun</option>
          {(projects.data ?? [])
            .filter((p) => !isClosedProject(p.status))
            .map((p) => (
              <option key={p.id} value={p.id}>
                {p.title}
              </option>
            ))}
        </select>
      </div>
      <div className="field">
        <label htmlFor="mt-participants">Participants</label>
        <input
          id="mt-participants"
          maxLength={1000}
          value={participants}
          onChange={(e) => setParticipants(e.target.value)}
        />
      </div>
      <p className="field__hint form-grid__full">
        Le relevé doit être diffusé dans les 24 heures après la fin de la réunion : PILOT vous le
        rappelle s’il ne l’est pas.
      </p>
      {create.isError && (
        <div className="form-grid__full">
          <Alert>{errorMessage(create.error)}</Alert>
        </div>
      )}
      <div className="form-grid__full form-actions">
        <button className="button button--primary" type="submit" disabled={create.isPending}>
          Ajouter la réunion
        </button>
        <button className="button button--ghost" type="button" onClick={onDone}>
          Annuler
        </button>
      </div>
    </form>
  )
}

function MeetingCard({
  meeting,
  spaceId,
  canWrite,
  openCount,
  onAddDecision,
}: {
  meeting: Meeting
  spaceId: string
  canWrite: boolean
  openCount: number
  onAddDecision: () => void
}) {
  const update = useUpdateMeeting(spaceId)
  const [sending, setSending] = useState(false)
  const [channel, setChannel] = useState('')
  const [recipients, setRecipients] = useState('')
  const [url, setUrl] = useState('')
  const step = MINUTES[meeting.minutes_state]

  return (
    <li className={`meeting${meeting.minutes_late ? ' meeting--late' : ''}`}>
      <div className="decision__head">
        <strong>{meeting.title}</strong>
        <span className="decision__badges">
          <StatusPill
            tone={
              meeting.minutes_state === 'sent' ? 'ok' : meeting.minutes_late ? 'danger' : 'warn'
            }
          >
            {step.label}
          </StatusPill>
          {meeting.minutes_late && (
            <span className="task-badge task-badge--late">Délai de 24 h dépassé</span>
          )}
        </span>
      </div>
      <p className="milestone__meta">
        Terminée le {formatMoment(meeting.ended_at)}
        {meeting.project && (
          <>
            {' · '}
            <Link to={`/espaces/${spaceId}/projets/${meeting.project.id}`}>
              {meeting.project.name}
            </Link>
          </>
        )}
        {' · '}
        {meeting.decisions_count} décision(s)
      </p>
      {meeting.minutes_state !== 'sent' ? (
        <p className="milestone__meta muted">
          Relevé à diffuser avant le {formatMoment(meeting.minutes_due_at)}
        </p>
      ) : (
        <p className="milestone__meta">
          Envoi déclaré le {meeting.minutes_sent_at ? formatMoment(meeting.minutes_sent_at) : '—'}
          {meeting.minutes_channel && ` · ${meeting.minutes_channel}`}
          {meeting.minutes_recipients && ` · à ${meeting.minutes_recipients}`}
          {meeting.minutes_url && (
            <>
              {' · '}
              <a href={meeting.minutes_url} target="_blank" rel="noreferrer">
                version envoyée
              </a>
            </>
          )}
          <span className="muted"> (déclaration, sans preuve automatique de remise)</span>
        </p>
      )}
      {sending && (
        <form
          className="form-grid decision-form"
          aria-label="Déclarer l’envoi du relevé"
          onSubmit={(e) => {
            e.preventDefault()
            update.mutate(
              {
                meeting,
                changes: {
                  minutes_state: 'sent',
                  minutes_channel: channel.trim() || null,
                  minutes_recipients: recipients.trim() || null,
                  minutes_url: url.trim() || null,
                },
              },
              { onSuccess: () => setSending(false) },
            )
          }}
        >
          <div className="field">
            <label htmlFor={`ch-${meeting.id}`}>Canal</label>
            <input
              id={`ch-${meeting.id}`}
              maxLength={120}
              placeholder="Ex. : e-mail, Teams"
              value={channel}
              onChange={(e) => setChannel(e.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor={`rc-${meeting.id}`}>Destinataires</label>
            <input
              id={`rc-${meeting.id}`}
              maxLength={1000}
              value={recipients}
              onChange={(e) => setRecipients(e.target.value)}
            />
          </div>
          <div className="field form-grid__full">
            <label htmlFor={`url-${meeting.id}`}>Lien vers la version envoyée</label>
            <input
              id={`url-${meeting.id}`}
              type="url"
              maxLength={500}
              placeholder="https://…"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
            />
          </div>
          <div className="form-grid__full form-actions">
            <button className="button button--primary" type="submit" disabled={update.isPending}>
              Déclarer envoyé
            </button>
            <button
              className="button button--ghost"
              type="button"
              onClick={() => setSending(false)}
            >
              Annuler
            </button>
          </div>
        </form>
      )}
      {canWrite && !sending && (
        <div className="decision__actions">
          {step.next && (
            <button
              type="button"
              className="button button--small button--primary"
              disabled={update.isPending}
              onClick={() =>
                step.next === 'sent'
                  ? setSending(true)
                  : update.mutate({ meeting, changes: { minutes_state: step.next } })
              }
            >
              {NEXT_LABEL[step.next]}
            </button>
          )}
          <button type="button" className="button button--small" onClick={onAddDecision}>
            + Décision de cette réunion
          </button>
          {openCount > 0 && (
            <span className="muted">
              À revoir en ouverture : {openCount} décision(s) encore ouverte(s).
            </span>
          )}
        </div>
      )}
      {update.isError && <Alert>{errorMessage(update.error)}</Alert>}
    </li>
  )
}

type Tab = 'todo' | 'open' | 'closed' | 'meetings'

export function DecisionsPage() {
  const { space } = useOutletContext<SpaceContext>()
  const canWrite = canWriteSpace(space.role)
  const [params, setParams] = useSearchParams()
  const decisions = useDecisions(space.id)
  const meetings = useMeetings(space.id)
  const [adding, setAdding] = useState<null | 'decision' | 'meeting'>(null)
  const [meetingForDecision, setMeetingForDecision] = useState<string | null>(null)
  const all = decisions.data ?? []
  const needsAction = (d: Decision) =>
    d.state === 'draft' || d.late || (d.orphan_days !== null && d.state !== 'cancelled')
  const lists: Record<Tab, Decision[]> = {
    todo: all.filter(needsAction),
    open: all.filter((d) => d.state === 'open'),
    closed: all.filter((d) => d.state === 'done' || d.state === 'cancelled'),
    meetings: [],
  }
  const lateMinutes = (meetings.data ?? []).filter((m) => m.minutes_late).length
  const tab = (params.get('vue') as Tab | null) ?? (lists.todo.length ? 'todo' : 'open')
  const openCount = all.filter((d) => d.state === 'open' || d.state === 'draft').length
  if (!space.advanced_mode) {
    return (
      <div className="page-content page-content--narrow">
        <PageHeader title="Décisions" />
        <Alert tone="info">
          Le registre des décisions fait partie du mode complet.{' '}
          {space.role === 'owner'
            ? 'Vous pouvez l’activer dans Paramètres → Mode d’affichage.'
            : 'Un propriétaire de l’espace peut l’activer dans les Paramètres.'}
        </Alert>
      </div>
    )
  }
  const TABS: [Tab, string, number][] = [
    ['todo', 'À traiter', lists.todo.length],
    ['open', 'À exécuter', lists.open.length],
    ['closed', 'Clôturées', lists.closed.length],
    ['meetings', 'Réunions', (meetings.data ?? []).length],
  ]

  return (
    <div className="page-content">
      <PageHeader
        title="Décisions"
        subtitle="Chaque décision a un responsable nommé, une échéance et un critère : PILOT la suit jusqu’à sa preuve."
      />
      {canWrite && (
        <div className="decision-toolbar">
          <button
            type="button"
            className="button button--primary"
            onClick={() => {
              setMeetingForDecision(null)
              setAdding('decision')
            }}
          >
            + Décision
          </button>
          <button type="button" className="button" onClick={() => setAdding('meeting')}>
            + Réunion
          </button>
        </div>
      )}
      {adding === 'decision' && (
        <div className="card-panel">
          <DecisionForm
            spaceId={space.id}
            meetingId={meetingForDecision}
            onDone={() => setAdding(null)}
          />
        </div>
      )}
      {adding === 'meeting' && (
        <div className="card-panel">
          <MeetingForm spaceId={space.id} onDone={() => setAdding(null)} />
        </div>
      )}
      <div className="segmented upd-tabs" role="group" aria-label="Vue du registre">
        {TABS.map(([key, label, count]) => (
          <button
            key={key}
            type="button"
            aria-pressed={tab === key}
            className={tab === key ? 'segmented__item segmented__item--on' : 'segmented__item'}
            onClick={() => setParams({ vue: key })}
          >
            {label} · {count}
            {key === 'meetings' && lateMinutes > 0 && ` (${lateMinutes} en retard)`}
          </button>
        ))}
      </div>
      {(decisions.isPending || meetings.isPending) && <Skeleton />}
      {decisions.isError && <Alert>{errorMessage(decisions.error)}</Alert>}
      {tab !== 'meetings' && decisions.data && (
        <section className="card-panel" aria-label="Décisions">
          {lists[tab].length === 0 ? (
            <p className="muted">
              {tab === 'todo'
                ? 'Rien à traiter : aucun brouillon, aucun retard, aucun sujet sans porteur.'
                : 'Aucune décision ici pour l’instant.'}
            </p>
          ) : (
            <ul className="decision-list">
              {lists[tab].map((d) => (
                <DecisionCard key={d.id} decision={d} spaceId={space.id} />
              ))}
            </ul>
          )}
        </section>
      )}
      {tab === 'meetings' && meetings.data && (
        <section className="card-panel" aria-label="Réunions">
          {meetings.data.length === 0 ? (
            <p className="muted">
              Aucune réunion. Ajoutez-en une pour suivre son relevé et y rattacher ses décisions.
            </p>
          ) : (
            <ul className="decision-list">
              {meetings.data.map((m) => (
                <MeetingCard
                  key={m.id}
                  meeting={m}
                  spaceId={space.id}
                  canWrite={canWrite}
                  openCount={openCount}
                  onAddDecision={() => {
                    setMeetingForDecision(m.id)
                    setAdding('decision')
                    window.scrollTo?.({ top: 0 })
                  }}
                />
              ))}
            </ul>
          )}
        </section>
      )}
    </div>
  )
}
