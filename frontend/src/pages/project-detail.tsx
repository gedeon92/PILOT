import { useState, type FormEvent, type ReactNode } from 'react'
import { Link, useOutletContext, useParams } from 'react-router'
import { ApiError, errorMessage, type HistoryEntry, type Project } from '../api/client'
import {
  useCatalog,
  useChangeProjectStatus,
  useHistory,
  useMembers,
  useProject,
  useTasks,
  useUpdateProject,
} from '../api/queries'
import { DocumentsSection } from '../components/documents'
import { TaskAddForm, TaskRow } from '../components/task-row'
import { PlusIcon } from '../components/icons'
import { Avatar } from '../components/avatar'
import { ContributorsField } from '../components/contributors-field'
import { Country } from '../components/country'
import { PortfolioMark } from '../components/portfolio-mark'
import { ProgressBar } from '../components/progress-bar'
import { ProjectLinksSection } from '../components/project-links'
import {
  DecisionOptionsField,
  type DecisionOptionValue,
} from '../components/decision-options-field'
import { PersonField } from '../components/person-field'
import { Alert, FullPageLoader, StatusPill } from '../components/ui'
import {
  CERTAINTY,
  formatDay,
  formatMoment,
  isClosedProject,
  PROJECT_STATUS,
  RISK,
  TASK_STATUS,
  todayIso,
  type ProjectStatus,
  type TaskStatus,
} from '../labels'
import { personPayload, personValue, type PersonValue } from '../person'
import type { SpaceContext } from './space-layout'

// ---------- Changement de statut ----------

function StatusChanger({
  project,
  spaceId,
  onDone,
}: {
  project: Project
  spaceId: string
  onDone: () => void
}) {
  const change = useChangeProjectStatus(spaceId, project.id)
  const [status, setStatus] = useState<ProjectStatus | ''>('')
  const [text, setText] = useState('')
  const reopening = isClosedProject(project.status) && status !== '' && !isClosedProject(status)

  function submit(event: FormEvent) {
    event.preventDefault()
    if (!status) return
    change.mutate(
      {
        version: project.version,
        status,
        ...(status === 'done' ? { outcome: text } : {}),
        ...(status === 'cancelled' ? { reason: text } : {}),
      },
      { onSuccess: onDone },
    )
  }

  return (
    <form className="status-changer" onSubmit={submit}>
      <div className="field">
        <label htmlFor="new-status">Nouveau statut</label>
        <select
          id="new-status"
          required
          value={status}
          onChange={(e) => setStatus(e.target.value as ProjectStatus)}
        >
          <option value="">Choisir…</option>
          {(Object.keys(PROJECT_STATUS) as ProjectStatus[])
            .filter((s) => s !== project.status)
            .map((s) => (
              <option key={s} value={s}>
                {PROJECT_STATUS[s].label}
              </option>
            ))}
        </select>
      </div>
      {status === 'done' && (
        <div className="field status-changer__wide">
          <label htmlFor="status-text">Bilan du projet *</label>
          <textarea
            id="status-text"
            required
            rows={3}
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          <span className="field__hint">Résultat obtenu, actions restantes, enseignements.</span>
        </div>
      )}
      {status === 'cancelled' && (
        <div className="field status-changer__wide">
          <label htmlFor="status-text">Motif de l’annulation *</label>
          <textarea
            id="status-text"
            required
            rows={3}
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          <span className="field__hint">
            Les tâches encore ouvertes seront annulées. Le dossier et les tâches terminées sont
            conservés.
          </span>
        </div>
      )}
      {reopening && (
        <Alert tone="warn">Le projet sera rouvert. Ce changement est inscrit à l’historique.</Alert>
      )}
      {change.isError && <Alert>{errorMessage(change.error)}</Alert>}
      <div className="form-actions">
        <button
          className="button button--primary"
          type="submit"
          disabled={!status || change.isPending}
        >
          Confirmer
        </button>
        <button className="button button--ghost" type="button" onClick={onDone}>
          Annuler
        </button>
      </div>
    </form>
  )
}

// ---------- Modification de la fiche ----------

type FormState = Record<string, string>

const TEXT_FIELDS = [
  'title',
  'origin',
  'situation',
  'next_step',
  'decision_needed',
  'decision_maker',
  'objective',
  'deliverables',
  'risk_note',
  'start_date',
  'end_date',
  'due_date',
  'window_start',
  'window_end',
  'country',
  'city',
  'external_url',
] as const

function initialForm(project: Project): FormState {
  const form: FormState = {}
  for (const key of TEXT_FIELDS) form[key] = (project[key] as string | null) ?? ''
  form.portfolio_id = project.portfolio.id
  form.entity_id = project.entity?.id ?? ''
  form.project_type_id = project.project_type?.id ?? ''
  form.date_certainty = project.date_certainty ?? ''
  form.risk_level = project.risk_level ?? ''
  form.progress = project.progress === null ? '' : String(project.progress)
  return form
}

function ProjectEditForm({
  project,
  spaceId,
  onDone,
}: {
  project: Project
  spaceId: string
  onDone: () => void
}) {
  const update = useUpdateProject(spaceId, project.id)
  const detail = useProject(spaceId, project.id)
  const portfolios = useCatalog(spaceId, 'portfolios')
  const entities = useCatalog(spaceId, 'entities')
  const types = useCatalog(spaceId, 'project-types')
  const members = useMembers(spaceId)
  const [form, setForm] = useState(() => initialForm(project))
  const [owner, setOwner] = useState<PersonValue>(() => personValue(project.owner))
  const [contributors, setContributors] = useState<PersonValue[]>(() =>
    project.contributors.map(personValue),
  )
  const [options, setOptions] = useState<DecisionOptionValue[]>(() =>
    project.decision_options.map((o) => ({ label: o.label, consequence: o.consequence ?? '' })),
  )
  const programs = useCatalog(spaceId, 'programs')
  const [eventForm, setEventForm] = useState(() => ({
    venue: project.event?.venue ?? '',
    audience: project.event?.audience ?? '',
    expected_attendance:
      project.event?.expected_attendance == null ? '' : String(project.event.expected_attendance),
    program_id: project.event?.program?.id ?? '',
    edition_label: project.event?.edition_label ?? '',
  }))
  // Les champs d'événement n'apparaissent que si le type choisi est de nature « événement ».
  const isEvent = types.data?.find((t) => t.id === form.project_type_id)?.kind === 'event'
  const conflict = update.error instanceof ApiError && update.error.status === 409

  const input = (key: string, label: string, props: Record<string, unknown> = {}) => (
    <div className={`field ${props.wide ? 'form-grid__full' : ''}`}>
      <label htmlFor={`edit-${key}`}>{label}</label>
      <input
        id={`edit-${key}`}
        value={form[key]}
        onChange={(e) => setForm({ ...form, [key]: e.target.value })}
        {...Object.fromEntries(Object.entries(props).filter(([k]) => k !== 'wide'))}
      />
    </div>
  )
  const textarea = (key: string, label: string, hint?: string) => (
    <div className="field form-grid__full">
      <label htmlFor={`edit-${key}`}>{label}</label>
      <textarea
        id={`edit-${key}`}
        rows={3}
        value={form[key]}
        onChange={(e) => setForm({ ...form, [key]: e.target.value })}
      />
      {hint && <span className="field__hint">{hint}</span>}
    </div>
  )
  const select = (key: string, label: string, options: [string, string][], empty: string) => (
    <div className="field">
      <label htmlFor={`edit-${key}`}>{label}</label>
      <select
        id={`edit-${key}`}
        value={form[key]}
        onChange={(e) => setForm({ ...form, [key]: e.target.value })}
      >
        {empty && <option value="">{empty}</option>}
        {options.map(([value, text]) => (
          <option key={value} value={value}>
            {text}
          </option>
        ))}
      </select>
    </div>
  )

  // Un élément archivé reste proposé s'il est déjà rattaché au projet.
  const withCurrent = (
    items: { id: string; name: string }[] | undefined,
    current?: { id: string; name: string } | null,
  ) => {
    const list = (items ?? []).map((i) => [i.id, i.name] as [string, string])
    if (current && !list.some(([id]) => id === current.id))
      list.push([current.id, `${current.name} (archivé)`])
    return list
  }

  function submit(event: FormEvent) {
    event.preventDefault()
    const body: Record<string, unknown> = { version: detail.data?.version ?? project.version }
    for (const key of TEXT_FIELDS) body[key] = form[key].trim() || null
    body.title = form.title.trim()
    body.portfolio_id = form.portfolio_id
    body.entity_id = form.entity_id || null
    body.project_type_id = form.project_type_id || null
    body.date_certainty = form.date_certainty || null
    body.risk_level = form.risk_level || null
    body.progress = form.progress === '' ? null : Number(form.progress)
    Object.assign(body, personPayload(owner, 'owner'))
    body.contributors = contributors.map((c) =>
      c.memberId ? { member_id: c.memberId } : { label: c.label },
    )
    body.decision_options = options
      .filter((o) => o.label.trim())
      .map((o) => ({ label: o.label.trim(), consequence: o.consequence.trim() || null }))
    if (isEvent) {
      body.event = {
        venue: eventForm.venue.trim() || null,
        audience: eventForm.audience.trim() || null,
        expected_attendance:
          eventForm.expected_attendance === '' ? null : Number(eventForm.expected_attendance),
        program_id: eventForm.program_id || null,
        edition_label: eventForm.edition_label.trim() || null,
      }
    }
    update.mutate(body as Record<string, unknown> & { version: number }, { onSuccess: onDone })
  }

  return (
    <form className="card-panel form-grid" onSubmit={submit} aria-label="Modifier la fiche">
      <h2 className="form-grid__full">Modifier la fiche</h2>
      {input('title', 'Titre *', { required: true, maxLength: 200, wide: true })}
      {select(
        'portfolio_id',
        'Portefeuille *',
        withCurrent(portfolios.data, project.portfolio),
        '',
      )}
      {select('entity_id', 'Filiale', withCurrent(entities.data, project.entity), 'Non précisée')}
      {select(
        'project_type_id',
        'Type de projet',
        withCurrent(types.data, project.project_type),
        'Non précisé',
      )}
      <PersonField
        id="edit-owner"
        label="Responsable du suivi"
        members={members.data ?? []}
        value={owner}
        onChange={setOwner}
      />
      <ContributorsField
        members={members.data ?? []}
        value={contributors}
        onChange={setContributors}
      />

      <h3 className="form-grid__full form-grid__title">Situation</h3>
      {textarea(
        'situation',
        'Situation',
        'Dernier état connu. La date d’actualisation est enregistrée.',
      )}
      {textarea('next_step', 'Prochaine étape', 'Ce qui doit se passer ensuite.')}
      {textarea(
        'decision_needed',
        'Décision attendue',
        'Ce qui bloque la progression et doit être tranché.',
      )}
      {input('decision_maker', 'Décideur', { maxLength: 120 })}
      <DecisionOptionsField value={options} onChange={setOptions} />

      <h3 className="form-grid__full form-grid__title">Dates</h3>
      {input('due_date', 'Échéance', { type: 'date' })}
      {select('date_certainty', 'Certitude', Object.entries(CERTAINTY), 'Non précisée')}
      {input('start_date', 'Début', { type: 'date' })}
      {input('end_date', 'Fin', { type: 'date' })}
      {input('window_start', 'Période : du', { type: 'date' })}
      {input('window_end', 'Période : au', { type: 'date' })}
      <p className="field__hint form-grid__full">
        Une période indique une fenêtre où les jours restent à choisir : elle ne vaut pas date
        exacte.
      </p>

      {isEvent && (
        <>
          <h3 className="form-grid__full form-grid__title">Événement</h3>
          <div className="field form-grid__full">
            <label htmlFor="edit-venue">Lieu</label>
            <input
              id="edit-venue"
              maxLength={200}
              placeholder="Ex. : Centre de conférences"
              value={eventForm.venue}
              onChange={(e) => setEventForm({ ...eventForm, venue: e.target.value })}
            />
          </div>
          <div className="field">
            <label htmlFor="edit-program">Programme</label>
            <select
              id="edit-program"
              value={eventForm.program_id}
              onChange={(e) => setEventForm({ ...eventForm, program_id: e.target.value })}
            >
              <option value="">Aucun (événement unique)</option>
              {withCurrent(programs.data, project.event?.program).map(([id, name]) => (
                <option key={id} value={id}>
                  {name}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="edit-edition">Édition</label>
            <input
              id="edit-edition"
              maxLength={40}
              placeholder="Ex. : 2026"
              value={eventForm.edition_label}
              onChange={(e) => setEventForm({ ...eventForm, edition_label: e.target.value })}
            />
          </div>
          <div className="field">
            <label htmlFor="edit-audience">Public visé</label>
            <input
              id="edit-audience"
              maxLength={300}
              value={eventForm.audience}
              onChange={(e) => setEventForm({ ...eventForm, audience: e.target.value })}
            />
          </div>
          <div className="field">
            <label htmlFor="edit-attendance">Participants attendus</label>
            <input
              id="edit-attendance"
              type="number"
              min={0}
              placeholder="Non renseigné"
              value={eventForm.expected_attendance}
              onChange={(e) => setEventForm({ ...eventForm, expected_attendance: e.target.value })}
            />
          </div>
          <p className="field__hint form-grid__full">
            Les jours de l’événement sont les dates de début et de fin ci-dessus. Le suivi se
            prolonge 15 jours après la fin.
          </p>
        </>
      )}

      <h3 className="form-grid__full form-grid__title">Cadrage</h3>
      {textarea(
        'origin',
        'Origine du besoin',
        'Qui l’a demandé, lors de quelle réunion ou de quel échange.',
      )}
      {textarea('objective', 'Objectif')}
      {textarea('deliverables', 'Livrables')}
      {input('progress', 'Avancement (%)', {
        type: 'number',
        min: 0,
        max: 100,
        placeholder: 'Non renseigné',
      })}
      {select('risk_level', 'Vigilance', Object.entries(RISK), 'Aucune')}
      {textarea('risk_note', 'Justification de la vigilance')}
      {input('city', 'Ville', { maxLength: 120 })}
      {input('country', 'Pays', { maxLength: 80 })}
      {input('external_url', 'Lien externe (dossier, outil)', {
        type: 'url',
        placeholder: 'https://…',
        wide: true,
      })}

      {conflict && (
        <div className="form-grid__full stack">
          <Alert tone="warn">
            Quelqu’un a modifié ce projet pendant que vous l’éditiez. Vos saisies sont conservées :
            chargez la version actuelle puis enregistrez à nouveau.
          </Alert>
          <button
            className="button"
            type="button"
            onClick={() => detail.refetch().then(() => update.reset())}
          >
            Charger la version actuelle
          </button>
        </div>
      )}
      {update.isError && !conflict && (
        <div className="form-grid__full">
          <Alert>{errorMessage(update.error)}</Alert>
        </div>
      )}
      <div className="form-grid__full form-actions">
        <button
          className="button button--primary"
          type="submit"
          disabled={update.isPending || conflict}
        >
          {update.isPending ? 'Enregistrement…' : 'Enregistrer'}
        </button>
        <button className="button button--ghost" type="button" onClick={onDone}>
          Annuler
        </button>
      </div>
    </form>
  )
}

// ---------- Tâches ----------

function TasksSection({
  project,
  spaceId,
  canWrite,
}: {
  project: Project
  spaceId: string
  canWrite: boolean
}) {
  const tasks = useTasks(spaceId, project.id)
  const [adding, setAdding] = useState(false)
  const closed = isClosedProject(project.status)
  const open = tasks.data?.filter((t) => t.status !== 'done' && t.status !== 'cancelled') ?? []
  const done = tasks.data?.filter((t) => t.status === 'done' || t.status === 'cancelled') ?? []

  return (
    <section className="card-panel" aria-labelledby="tasks-title">
      <div className="card-panel__head">
        <h2 id="tasks-title">
          Tâches <span className="count">{open.length} ouverte(s)</span>
        </h2>
        {canWrite && !closed && !adding && (
          <button type="button" className="button button--small" onClick={() => setAdding(true)}>
            <PlusIcon /> Tâche
          </button>
        )}
      </div>
      {adding && (
        <TaskAddForm spaceId={spaceId} projectId={project.id} onDone={() => setAdding(false)} />
      )}
      {tasks.isPending && <p className="muted">Chargement…</p>}
      {tasks.data?.length === 0 && !adding && (
        <p className="muted">Aucune tâche. Déclinez la prochaine étape en actions concrètes.</p>
      )}
      {open.length > 0 && (
        <ul className="task-list">
          {open.map((task) => (
            <TaskRow key={task.id} task={task} spaceId={spaceId} canWrite={canWrite} />
          ))}
        </ul>
      )}
      {done.length > 0 && (
        <details className="task-closed">
          <summary>{done.length} tâche(s) clôturée(s)</summary>
          <ul className="task-list">
            {done.map((task) => (
              <TaskRow key={task.id} task={task} spaceId={spaceId} canWrite={canWrite} />
            ))}
          </ul>
        </details>
      )}
    </section>
  )
}

// ---------- Historique ----------

const FIELD_LABELS: Record<string, string> = {
  title: 'titre',
  situation: 'situation',
  next_step: 'prochaine étape',
  decision_needed: 'décision attendue',
  decision_maker: 'décideur',
  objective: 'objectif',
  deliverables: 'livrables',
  progress: 'avancement',
  risk_level: 'vigilance',
  risk_note: 'justification',
  start_date: 'début',
  end_date: 'fin',
  due_date: 'échéance',
  date_certainty: 'certitude',
  window_start: 'période',
  window_end: 'période',
  country: 'pays',
  city: 'ville',
  external_url: 'lien',
  portfolio_id: 'portefeuille',
  entity_id: 'filiale',
  project_type_id: 'type',
  owner_member_id: 'responsable',
  owner_label: 'responsable',
  status: 'statut',
  assignee_member_id: 'responsable',
  assignee_label: 'responsable',
  deliverable: 'livrable',
  due_certainty: 'certitude',
  origin: 'origine',
  contributors: 'contributeurs',
  decision_options: 'options de décision',
}

function statusLabel(value: unknown) {
  return PROJECT_STATUS[value as ProjectStatus]?.label ?? String(value)
}

function describe(entry: HistoryEntry): { what: string; detail?: string } {
  const before = entry.before ?? {}
  const after = entry.after ?? {}
  const fields = [...new Set(Object.keys(after).map((k) => FIELD_LABELS[k] ?? k))].join(', ')
  switch (entry.action) {
    case 'project.created':
      return { what: 'Projet créé' }
    case 'project.updated':
      return { what: 'Fiche modifiée', detail: fields }
    case 'project.updated_from_proposal':
      return { what: 'Mise à jour validée (boîte de mise à jour)', detail: fields }
    case 'project.status_changed':
      return {
        what: `Statut : ${statusLabel(before.status)} → ${statusLabel(after.status)}`,
        detail: (after.outcome ?? after.cancel_reason) as string | undefined,
      }
    case 'project.reopened':
      return { what: `Projet rouvert : ${statusLabel(after.status)}` }
    case 'task.created':
      return { what: 'Tâche ajoutée', detail: after.title as string }
    case 'task.updated':
      return {
        what: after.status
          ? `Tâche ${TASK_STATUS[after.status as TaskStatus]?.label.toLowerCase()}`
          : 'Tâche modifiée',
        detail: after.status ? undefined : fields,
      }
    case 'document.uploaded':
      return { what: 'Document ajouté', detail: after.filename as string }
    case 'document.archived':
      return { what: 'Document retiré', detail: before.filename as string }
    case 'document.replaced':
      return {
        what: `Nouvelle version d’un document (v${after.revision})`,
        detail: after.filename as string,
      }
    case 'project.linked':
      return {
        what: 'Projet lié',
        detail: [after.linked_project, after.note].filter(Boolean).join(' — '),
      }
    case 'project.unlinked':
      return { what: 'Lien retiré', detail: after.linked_project as string }
    default:
      return { what: entry.action }
  }
}

function HistorySection({ spaceId, projectId }: { spaceId: string; projectId: string }) {
  const history = useHistory(spaceId, projectId)
  return (
    <section className="card-panel" aria-labelledby="history-title">
      <h2 id="history-title">Historique</h2>
      {history.isPending && <p className="muted">Chargement…</p>}
      <ol className="history">
        {history.data?.map((entry) => {
          const { what, detail } = describe(entry)
          return (
            <li key={entry.id} className="history__item">
              <span className="history__what">{what}</span>
              {detail && <span className="history__detail">{detail}</span>}
              <span className="history__when">
                {formatMoment(entry.created_at)}
                {entry.actor_name && ` · ${entry.actor_name}`}
              </span>
            </li>
          )
        })}
      </ol>
    </section>
  )
}

// ---------- Page ----------

function EventCard({ project, today }: { project: Project; today: string }) {
  const event = project.event!
  const end = project.end_date ?? project.start_date ?? project.due_date
  let followUp: ReactNode = null
  if (event.follow_up_until && end && today > end && !isClosedProject(project.status)) {
    followUp =
      today <= event.follow_up_until ? (
        <Alert tone="warn">
          Suivi après l’événement en cours jusqu’au {formatDay(event.follow_up_until)} : relances,
          exploitation, bilan.
        </Alert>
      ) : (
        <Alert tone="warn">Le suivi de 15 jours est terminé : bilan à rédiger pour clôturer.</Alert>
      )
  }
  return (
    <section className="card-panel card-panel--event" aria-labelledby="event-title">
      <h2 id="event-title">Événement</h2>
      {followUp}
      <dl className="infos">
        <Info
          label="Jours de l’événement"
          value={
            project.start_date
              ? `${formatDay(project.start_date)}${project.end_date && project.end_date !== project.start_date ? ` → ${formatDay(project.end_date)}` : ''}${project.date_certainty ? ` · ${CERTAINTY[project.date_certainty]}` : ''}`
              : project.window_start
                ? `Période : ${formatDay(project.window_start)} – ${formatDay(project.window_end)}`
                : 'Date à fixer'
          }
        />
        <Info
          label="Lieu"
          value={
            (event.venue || project.city || project.country) && (
              <>
                {[event.venue, project.city].filter(Boolean).join(', ')}
                {(event.venue || project.city) && project.country && ', '}
                <Country name={project.country} />
              </>
            )
          }
        />
        <Info
          label="Programme"
          value={
            event.program
              ? `${event.program.name}${event.edition_label ? ` · édition ${event.edition_label}` : ''}`
              : event.edition_label && `Édition ${event.edition_label}`
          }
        />
        <Info label="Public visé" value={event.audience} />
        <Info
          label="Participants attendus"
          value={event.expected_attendance === null ? null : String(event.expected_attendance)}
        />
        <Info
          label="Fin du suivi (J+15)"
          value={event.follow_up_until && formatDay(event.follow_up_until)}
        />
      </dl>
    </section>
  )
}

/** D'où vient la dernière situation (CDC §21 « Source et fraîcheur »). */
function SituationSource({ project }: { project: Project }) {
  if (!project.situation || !project.situation_updated_at) return null
  const source =
    project.situation_source === 'manual'
      ? 'saisie sur la fiche'
      : project.situation_source === 'update'
        ? `boîte de mise à jour${project.situation_source_label ? ` (« ${project.situation_source_label} »)` : ''}`
        : project.situation_source === 'import'
          ? 'import d’une sauvegarde'
          : null
  return (
    <p className="situation__source">
      Actualisée le {formatMoment(project.situation_updated_at)}
      {project.situation_updated_by && ` par ${project.situation_updated_by}`}
      {source ? ` · Source : ${source}` : ' · Source non renseignée'}
    </p>
  )
}

function Landmark({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="landmark">
      <span className="landmark__label">{label}</span>
      <span className="landmark__value">{children}</span>
    </div>
  )
}

function Info({ label, value }: { label: string; value: ReactNode }) {
  if (value === null || value === undefined || value === '') return null
  return (
    <div className="info">
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  )
}

export function ProjectDetailPage() {
  const { space } = useOutletContext<SpaceContext>()
  const { projectId = '' } = useParams()
  const project = useProject(space.id, projectId)
  const [mode, setMode] = useState<'view' | 'edit' | 'status'>('view')
  const canWrite = space.role !== 'reader'
  const today = todayIso(space.timezone)

  if (project.isPending) return <FullPageLoader />
  if (project.isError) {
    return (
      <div className="page-content">
        <Alert>{errorMessage(project.error)}</Alert>
        <Link className="button" to={`/espaces/${space.id}/projets`}>
          Retour aux projets
        </Link>
      </div>
    )
  }

  const p = project.data
  const status = PROJECT_STATUS[p.status]
  const late = !isClosedProject(p.status) && p.due_date !== null && p.due_date < today

  return (
    <div className="page-content">
      <nav aria-label="Fil d’Ariane" className="breadcrumb">
        <Link to={`/espaces/${space.id}/projets`}>Projets</Link>
        <span aria-hidden="true">/</span>
        <span>{p.title}</span>
      </nav>

      <header className="page-header">
        <div className="page-header__text">
          <div className="title-line">
            <h1>{p.title}</h1>
            <StatusPill tone={status.tone}>{status.label}</StatusPill>
          </div>
          <p>
            Mis à jour le {formatMoment(p.updated_at)}
            {p.situation_updated_at &&
              ` · situation actualisée le ${formatMoment(p.situation_updated_at)}`}
          </p>
        </div>
        {canWrite && mode === 'view' && (
          <div className="page-header__actions">
            <button type="button" className="button" onClick={() => setMode('status')}>
              Changer le statut
            </button>
            <button
              type="button"
              className="button button--primary"
              onClick={() => setMode('edit')}
            >
              Modifier la fiche
            </button>
          </div>
        )}
      </header>

      {mode === 'status' && (
        <section className="card-panel" aria-label="Changer le statut">
          <StatusChanger project={p} spaceId={space.id} onDone={() => setMode('view')} />
        </section>
      )}

      {p.status === 'done' && p.outcome && <Alert tone="ok">Bilan : {p.outcome}</Alert>}
      {p.status === 'cancelled' && p.cancel_reason && (
        <Alert tone="warn">Annulé : {p.cancel_reason}</Alert>
      )}

      <section className="landmarks" aria-label="Repères">
        <Landmark label="Portefeuille">
          <PortfolioMark color={p.portfolio.color} emoji={p.portfolio.emoji} />
          {p.portfolio.name}
        </Landmark>
        <Landmark label="Filiale">
          {p.entity?.name ?? <span className="muted">Non précisée</span>}
        </Landmark>
        <Landmark label="Responsable du suivi">
          {p.owner.name && <Avatar name={p.owner.name} size="tiny" />}
          {p.owner.name ?? <span className="warn-text">Non attribué</span>}
          {p.owner.name && !p.owner.has_account && <span className="owner__note">Sans compte</span>}
        </Landmark>
        <Landmark label={p.due_date || !p.start_date ? 'Échéance' : 'Dates'}>
          {p.due_date ? (
            <>
              <span className={late ? 'due__date--late' : ''}>{formatDay(p.due_date)}</span>
              {p.date_certainty && (
                <span className="chip chip--small">{CERTAINTY[p.date_certainty]}</span>
              )}
            </>
          ) : p.start_date ? (
            `${formatDay(p.start_date)}${p.end_date && p.end_date !== p.start_date ? ` → ${formatDay(p.end_date)}` : ''}`
          ) : p.window_start ? (
            `${formatDay(p.window_start)} – ${formatDay(p.window_end)}`
          ) : (
            <span className="muted">Non fixée</span>
          )}
        </Landmark>
        <Landmark label="Avancement">
          {p.progress === null ? (
            <span className="muted">Non renseigné</span>
          ) : (
            <ProgressBar value={p.progress} />
          )}
        </Landmark>
      </section>

      {mode === 'edit' ? (
        <ProjectEditForm project={p} spaceId={space.id} onDone={() => setMode('view')} />
      ) : (
        <div className="detail-columns">
          <div className="detail-columns__main">
            <section className="card-panel situation" aria-label="Situation">
              <div className="situation__block">
                <h2 className="eyebrow">Situation</h2>
                <p>{p.situation ?? <span className="muted">Pas encore renseignée.</span>}</p>
                <SituationSource project={p} />
              </div>
              <div className="situation__block">
                <h2 className="eyebrow">Prochaine étape</h2>
                <p>{p.next_step ?? <span className="warn-text">À définir</span>}</p>
              </div>
              <div className="situation__block">
                <h2 className="eyebrow">Décision attendue</h2>
                <p>
                  {p.decision_needed ?? <span className="muted">Aucune décision en attente.</span>}
                  {p.decision_needed && p.decision_maker && (
                    <span className="situation__who"> · Décideur : {p.decision_maker}</span>
                  )}
                </p>
                {p.decision_needed && p.decision_options.length > 0 && (
                  <ol className="decision-list" aria-label="Options possibles">
                    {p.decision_options.map((o, i) => (
                      <li key={i}>
                        <span className="decision-options__letter" aria-hidden="true">
                          {String.fromCharCode(65 + i)}
                        </span>
                        <span>
                          <strong>{o.label}</strong>
                          {o.consequence && (
                            <span className="decision-list__consequence"> — {o.consequence}</span>
                          )}
                        </span>
                      </li>
                    ))}
                  </ol>
                )}
              </div>
            </section>
            <TasksSection project={p} spaceId={space.id} canWrite={canWrite} />
            <DocumentsSection spaceId={space.id} projectId={p.id} canWrite={canWrite} />
          </div>

          <aside className="detail-columns__side">
            {p.event && <EventCard project={p} today={today} />}
            <section className="card-panel" aria-labelledby="info-title">
              <h2 id="info-title">Informations</h2>
              <dl className="infos">
                <Info label="Type" value={p.project_type?.name} />
                <Info label="Origine du besoin" value={p.origin} />
                <Info
                  label="Contributeurs"
                  value={
                    p.contributors.length > 0 && (
                      <span className="contributors-list">
                        {p.contributors.map((c, i) => (
                          <span key={`${c.member_id ?? c.name}-${i}`} className="contributor">
                            <Avatar name={c.name ?? '?'} size="tiny" />
                            <span>
                              {c.name}
                              {!c.has_account && <span className="owner__note">Sans compte</span>}
                            </span>
                          </span>
                        ))}
                      </span>
                    )
                  }
                />
                <Info label="Objectif" value={p.objective} />
                <Info label="Livrables" value={p.deliverables} />
                <Info
                  label="Dates"
                  value={
                    p.start_date || p.end_date
                      ? `${formatDay(p.start_date) || '…'} → ${formatDay(p.end_date) || '…'}`
                      : null
                  }
                />
                <Info
                  label="Période à préciser"
                  value={
                    p.window_start
                      ? `${formatDay(p.window_start)} – ${formatDay(p.window_end)}`
                      : null
                  }
                />
                <Info
                  label="Lieu"
                  value={
                    (p.city || p.country) && (
                      <>
                        {p.city}
                        {p.city && p.country && ', '}
                        <Country name={p.country} />
                      </>
                    )
                  }
                />
                <Info
                  label="Vigilance"
                  value={
                    p.risk_level
                      ? `${RISK[p.risk_level]}${p.risk_note ? ` — ${p.risk_note}` : ''}`
                      : null
                  }
                />
                <Info
                  label="Lien"
                  value={
                    p.external_url && (
                      <a href={p.external_url} target="_blank" rel="noreferrer">
                        Ouvrir le lien
                      </a>
                    )
                  }
                />
              </dl>
            </section>
            <ProjectLinksSection spaceId={space.id} projectId={p.id} canWrite={canWrite} />
            <HistorySection spaceId={space.id} projectId={p.id} />
          </aside>
        </div>
      )}
    </div>
  )
}
