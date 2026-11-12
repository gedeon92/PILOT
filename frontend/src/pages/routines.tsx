import { useState, type FormEvent } from 'react'
import { useOutletContext } from 'react-router'
import { canWriteSpace, errorMessage, type Routine } from '../api/client'
import {
  useAddProfiles,
  useCreateRoutine,
  useMembers,
  useOccurrences,
  useProjects,
  useRoutineAction,
  useRoutineProfiles,
  useRoutines,
  useUpdateRoutine,
} from '../api/queries'
import { OccurrenceCard } from '../components/occurrence-card'
import { PersonField, type PersonValue } from '../components/person-field'
import { Alert, PageHeader, Skeleton, StatusPill } from '../components/ui'
import { formatDay, isClosedProject, todayIso } from '../labels'
import { personPayload, personValue } from '../person'
import type { SpaceContext } from './space-layout'

/** Étape F5 (cahier V2, RIT01–RIT07) : routines de pilotage. Une routine est un modèle
 * (fréquence, durée, responsable, checklist, résultat attendu) ; ses occurrences sont créées
 * une seule fois par date. Elles vivent dans PILOT : rien n'est envoyé ailleurs. */

const WEEKDAYS = ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim']
const FREQUENCY: Record<Routine['frequency'], string> = {
  daily: 'Chaque jour',
  weekly: 'Chaque semaine',
  biweekly: 'Toutes les deux semaines',
  twice_monthly: 'Deux fois par mois',
  monthly: 'Chaque mois',
  quarterly: 'Chaque trimestre',
}
const NTH = { '1': '1er', '2': '2e', '3': '3e', '4': '4e', '-1': 'Dernier' } as const

function cadence(
  r: Pick<
    Routine,
    'frequency' | 'weekdays' | 'month_days' | 'nth_weekday' | 'time_of_day' | 'duration_minutes'
  >,
) {
  let text = FREQUENCY[r.frequency]
  if (['daily', 'weekly', 'biweekly'].includes(r.frequency) && r.weekdays.length) {
    text += ` · ${r.weekdays.map((d) => WEEKDAYS[d]).join(', ')}`
  } else if (r.nth_weekday) {
    text += ` · ${NTH[String(r.nth_weekday.n) as keyof typeof NTH]} ${WEEKDAYS[r.nth_weekday.weekday].toLowerCase()}.`
  } else if (r.month_days.length) {
    text += ` · le ${r.month_days.join(' et le ')}`
  }
  if (r.time_of_day) text += ` · ${r.time_of_day}`
  if (r.duration_minutes) text += ` · ${r.duration_minutes} min`
  return text
}

type Draft = {
  title: string
  purpose: string
  frequency: Routine['frequency']
  weekdays: number[]
  day1: string
  day2: string
  useNth: boolean
  nthN: string
  nthWeekday: string
  time: string
  duration: string
  owner: PersonValue
  participants: string
  checklist: { id?: string; label: string; mandatory: boolean }[]
  expected: string
  start: string
}

function draftOf(r: Routine | undefined, today: string): Draft {
  return {
    title: r?.title ?? '',
    purpose: r?.purpose ?? '',
    frequency: r?.frequency ?? 'weekly',
    weekdays: r?.weekdays ?? [0],
    day1: String(r?.month_days[0] ?? 1),
    day2: String(r?.month_days[1] ?? 15),
    useNth: Boolean(r?.nth_weekday),
    nthN: String(r?.nth_weekday?.n ?? 1),
    nthWeekday: String(r?.nth_weekday?.weekday ?? 0),
    time: r?.time_of_day ?? '',
    duration: r?.duration_minutes ? String(r.duration_minutes) : '',
    owner: r ? personValue(r.owner) : { memberId: null, label: '' },
    participants: r?.participants ?? '',
    checklist: r?.checklist.map((c) => ({ ...c })) ?? [{ label: '', mandatory: true }],
    expected: r?.expected_output ?? '',
    start: r?.start_date ?? today,
  }
}

function RoutineForm({
  spaceId,
  routine,
  today,
  onDone,
}: {
  spaceId: string
  routine?: Routine
  today: string
  onDone: () => void
}) {
  const create = useCreateRoutine(spaceId)
  const update = useUpdateRoutine(spaceId)
  const members = useMembers(spaceId).data ?? []
  const [d, setD] = useState<Draft>(() => draftOf(routine, today))
  const [scope, setScope] = useState<'model' | 'following'>('following')
  const set = (patch: Partial<Draft>) => setD((x) => ({ ...x, ...patch }))
  const byWeek = ['daily', 'weekly', 'biweekly'].includes(d.frequency)
  const pending = create.isPending || update.isPending
  const error = create.error ?? update.error
  const p = routine ? `r-${routine.id}` : 'r-new'

  function submit(event: FormEvent) {
    event.preventDefault()
    const monthly = d.frequency === 'monthly' && d.useNth
    const owner = personPayload(d.owner, 'owner')
    const body: Record<string, unknown> = {
      title: d.title,
      purpose: d.purpose.trim() || null,
      frequency: d.frequency,
      weekdays: byWeek ? d.weekdays : [],
      month_days:
        byWeek || monthly
          ? []
          : d.frequency === 'twice_monthly'
            ? [Number(d.day1), Number(d.day2)]
            : [Number(d.day1)],
      nth_weekday: monthly ? { n: Number(d.nthN), weekday: Number(d.nthWeekday) } : null,
      time_of_day: d.time || null,
      duration_minutes: d.duration ? Number(d.duration) : null,
      owner_member_id: null,
      owner_label: null,
      ...owner,
      participants: d.participants.trim() || null,
      checklist: d.checklist
        .filter((c) => c.label.trim())
        .map((c) => ({ ...c, label: c.label.trim() })),
      expected_output: d.expected.trim() || null,
    }
    if (routine) {
      update.mutate({ routine, ...body, scope }, { onSuccess: onDone })
    } else {
      create.mutate({ ...body, start_date: d.start }, { onSuccess: onDone })
    }
  }

  return (
    <form className="item-form routine-form" onSubmit={submit}>
      <div className="field item-form__name">
        <label htmlFor={`${p}-title`}>Nom de la routine</label>
        <input
          id={`${p}-title`}
          required
          maxLength={160}
          value={d.title}
          onChange={(e) => set({ title: e.target.value })}
        />
      </div>
      <div className="field">
        <label htmlFor={`${p}-freq`}>Fréquence</label>
        <select
          id={`${p}-freq`}
          value={d.frequency}
          onChange={(e) => set({ frequency: e.target.value as Routine['frequency'] })}
        >
          {Object.entries(FREQUENCY).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </div>
      {byWeek ? (
        <fieldset className="routine-days">
          <legend>Jours</legend>
          {WEEKDAYS.map((name, i) => (
            <label key={name} className="checkbox">
              <input
                type="checkbox"
                checked={d.weekdays.includes(i)}
                onChange={(e) =>
                  set({
                    weekdays: e.target.checked
                      ? [...d.weekdays, i].sort()
                      : d.weekdays.filter((x) => x !== i),
                  })
                }
              />
              {name}
            </label>
          ))}
        </fieldset>
      ) : (
        <>
          {d.frequency === 'monthly' && (
            <label className="field field--check">
              <input
                type="checkbox"
                checked={d.useNth}
                onChange={(e) => set({ useNth: e.target.checked })}
              />
              Un jour de la semaine (ex. le premier lundi)
            </label>
          )}
          {d.frequency === 'monthly' && d.useNth ? (
            <>
              <div className="field">
                <label htmlFor={`${p}-nth`}>Lequel</label>
                <select
                  id={`${p}-nth`}
                  value={d.nthN}
                  onChange={(e) => set({ nthN: e.target.value })}
                >
                  {Object.entries(NTH).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label htmlFor={`${p}-nthday`}>Jour</label>
                <select
                  id={`${p}-nthday`}
                  value={d.nthWeekday}
                  onChange={(e) => set({ nthWeekday: e.target.value })}
                >
                  {WEEKDAYS.map((name, i) => (
                    <option key={name} value={i}>
                      {name}
                    </option>
                  ))}
                </select>
              </div>
            </>
          ) : (
            <>
              <div className="field">
                <label htmlFor={`${p}-day1`}>
                  {d.frequency === 'twice_monthly' ? 'Premier jour du mois' : 'Jour du mois'}
                </label>
                <input
                  id={`${p}-day1`}
                  type="number"
                  min={1}
                  max={31}
                  required
                  value={d.day1}
                  onChange={(e) => set({ day1: e.target.value })}
                />
              </div>
              {d.frequency === 'twice_monthly' && (
                <div className="field">
                  <label htmlFor={`${p}-day2`}>Second jour du mois</label>
                  <input
                    id={`${p}-day2`}
                    type="number"
                    min={1}
                    max={31}
                    required
                    value={d.day2}
                    onChange={(e) => set({ day2: e.target.value })}
                  />
                </div>
              )}
            </>
          )}
        </>
      )}
      <div className="field">
        <label htmlFor={`${p}-time`}>Heure (facultatif)</label>
        <input
          id={`${p}-time`}
          type="time"
          value={d.time}
          onChange={(e) => set({ time: e.target.value })}
        />
      </div>
      <div className="field">
        <label htmlFor={`${p}-duration`}>Durée (minutes)</label>
        <input
          id={`${p}-duration`}
          type="number"
          min={5}
          max={480}
          value={d.duration}
          onChange={(e) => set({ duration: e.target.value })}
        />
      </div>
      {!routine && (
        <div className="field">
          <label htmlFor={`${p}-start`}>À partir du</label>
          <input
            id={`${p}-start`}
            type="date"
            required
            value={d.start}
            onChange={(e) => set({ start: e.target.value })}
          />
        </div>
      )}
      <div className="field item-form__name">
        <PersonField
          id={`${p}-owner`}
          label="Responsable"
          members={members}
          value={d.owner}
          onChange={(owner) => set({ owner })}
        />
      </div>
      <div className="field item-form__name">
        <label htmlFor={`${p}-purpose`}>Finalité (facultatif)</label>
        <input
          id={`${p}-purpose`}
          maxLength={4000}
          value={d.purpose}
          onChange={(e) => set({ purpose: e.target.value })}
        />
      </div>
      <fieldset className="routine-checklist item-form__name">
        <legend>Checklist courte</legend>
        {d.checklist.map((c, i) => (
          <div key={c.id ?? `new-${i}`} className="cf-options__row">
            <label className="visually-hidden" htmlFor={`${p}-chk-${i}`}>
              Contrôle {i + 1}
            </label>
            <input
              id={`${p}-chk-${i}`}
              maxLength={200}
              placeholder="ex. Relevés de la semaine diffusés"
              value={c.label}
              onChange={(e) =>
                set({
                  checklist: d.checklist.map((x, j) =>
                    j === i ? { ...x, label: e.target.value } : x,
                  ),
                })
              }
            />
            <label className="checkbox">
              <input
                type="checkbox"
                checked={c.mandatory}
                onChange={(e) =>
                  set({
                    checklist: d.checklist.map((x, j) =>
                      j === i ? { ...x, mandatory: e.target.checked } : x,
                    ),
                  })
                }
              />
              Obligatoire
            </label>
          </div>
        ))}
        {d.checklist.length < 20 && (
          <button
            type="button"
            className="button button--small button--ghost"
            onClick={() => set({ checklist: [...d.checklist, { label: '', mandatory: true }] })}
          >
            + Contrôle
          </button>
        )}
      </fieldset>
      <div className="field item-form__name">
        <label htmlFor={`${p}-expected`}>Résultat attendu (facultatif)</label>
        <input
          id={`${p}-expected`}
          maxLength={4000}
          value={d.expected}
          onChange={(e) => set({ expected: e.target.value })}
        />
      </div>
      {routine && (
        <fieldset className="routine-scope item-form__name">
          <legend>Appliquer le changement</legend>
          <label className="checkbox">
            <input
              type="radio"
              name={`${p}-scope`}
              checked={scope === 'following'}
              onChange={() => setScope('following')}
            />
            Aux occurrences à venir (celles déjà commencées ou reportées ne bougent pas)
          </label>
          <label className="checkbox">
            <input
              type="radio"
              name={`${p}-scope`}
              checked={scope === 'model'}
              onChange={() => setScope('model')}
            />
            Au modèle seulement (nouvelles occurrences)
          </label>
          <p className="field__hint">
            Pour une seule occurrence, ouvrez-la et utilisez « Reporter ».
          </p>
        </fieldset>
      )}
      {error && <Alert>{errorMessage(error)}</Alert>}
      <div className="item-form__actions">
        <button className="button button--primary" disabled={pending}>
          {routine ? 'Enregistrer' : 'Créer la routine'}
        </button>
        <button type="button" className="button button--ghost" onClick={onDone}>
          Annuler
        </button>
      </div>
    </form>
  )
}

function Profiles({ spaceId, onDone }: { spaceId: string; onDone: () => void }) {
  const profiles = useRoutineProfiles(spaceId)
  const add = useAddProfiles(spaceId)
  const [chosen, setChosen] = useState<string[]>([])
  return (
    <div className="routine-profiles">
      <p className="card-panel__help">
        Les routines types reprennent les horaires et durées des routines fournies. Elles restent
        modifiables ; choisissez seulement celles qui correspondent à votre organisation.
      </p>
      {profiles.isPending && <Skeleton lines={3} />}
      <ul className="item-list">
        {profiles.data?.map((p) => (
          <li key={p.key} className="item-row">
            <label className="checkbox routine-profiles__item">
              <input
                type="checkbox"
                disabled={p.already_added}
                checked={p.already_added || chosen.includes(p.key)}
                onChange={(e) =>
                  setChosen((c) =>
                    e.target.checked ? [...c, p.key] : c.filter((k) => k !== p.key),
                  )
                }
              />
              <span className="item-row__text">
                <span className="item-row__name">
                  {p.title}{' '}
                  {p.already_added && <StatusPill tone="neutral">Déjà ajoutée</StatusPill>}
                </span>
                <span className="item-row__details">
                  {cadence({ ...p, nth_weekday: null })} — {p.purpose}
                </span>
              </span>
            </label>
          </li>
        ))}
      </ul>
      {add.isError && <Alert>{errorMessage(add.error)}</Alert>}
      <div className="item-form__actions">
        <button
          type="button"
          className="button button--primary"
          disabled={chosen.length === 0 || add.isPending}
          onClick={() => add.mutate(chosen, { onSuccess: onDone })}
        >
          Ajouter {chosen.length || ''} routine(s)
        </button>
        <button type="button" className="button button--ghost" onClick={onDone}>
          Fermer
        </button>
      </div>
    </div>
  )
}

function RoutineRow({
  spaceId,
  routine,
  canWrite,
  today,
}: {
  spaceId: string
  routine: Routine
  canWrite: boolean
  today: string
}) {
  const action = useRoutineAction(spaceId)
  const [editing, setEditing] = useState(false)
  const [archiving, setArchiving] = useState(false)
  const [reason, setReason] = useState('')
  const [showOcc, setShowOcc] = useState(false)
  const occurrences = useOccurrences(spaceId, { routine_id: routine.id }, showOcc)
  const projects = (useProjects(spaceId).data ?? []).filter((p) => !isClosedProject(p.status))

  if (editing) {
    return (
      <li className="item-row item-row--editing">
        <RoutineForm
          spaceId={spaceId}
          routine={routine}
          today={today}
          onDone={() => setEditing(false)}
        />
      </li>
    )
  }
  return (
    <li className="item-row routine-row">
      <div className="routine-row__line">
        <span className="item-row__text">
          <span className="item-row__name">
            {routine.title}{' '}
            {routine.archived ? (
              <StatusPill tone="neutral">Arrêtée</StatusPill>
            ) : routine.paused ? (
              <StatusPill tone="warn">En pause</StatusPill>
            ) : routine.late_count > 0 ? (
              <StatusPill tone="danger">{routine.late_count} en retard</StatusPill>
            ) : null}
          </span>
          <span className="item-row__details">
            {cadence(routine)} · {routine.owner.name ?? 'Sans responsable'}
            {routine.next_date && ` · prochaine le ${formatDay(routine.next_date)}`}
            {routine.archive_reason && ` · motif : ${routine.archive_reason}`}
          </span>
        </span>
        <span className="item-row__actions">
          <button
            type="button"
            className="button button--small button--ghost"
            aria-expanded={showOcc}
            onClick={() => setShowOcc((v) => !v)}
          >
            {showOcc ? 'Masquer' : 'Occurrences'}
          </button>
          {canWrite && !routine.archived && (
            <>
              <button
                type="button"
                className="button button--small"
                onClick={() => setEditing(true)}
              >
                Modifier
              </button>
              <button
                type="button"
                className="button button--small"
                disabled={action.isPending}
                onClick={() =>
                  action.mutate({ id: routine.id, action: routine.paused ? 'resume' : 'pause' })
                }
              >
                {routine.paused ? 'Reprendre' : 'Pause'}
              </button>
              <button
                type="button"
                className="button button--small button--ghost"
                onClick={() => setArchiving(true)}
              >
                Arrêter
              </button>
            </>
          )}
          {canWrite && routine.archived && (
            <button
              type="button"
              className="button button--small"
              onClick={() => action.mutate({ id: routine.id, action: 'restore' })}
            >
              Reprendre
            </button>
          )}
        </span>
      </div>
      {archiving && (
        <form
          className="inline-form"
          onSubmit={(e) => {
            e.preventDefault()
            action.mutate(
              { id: routine.id, action: 'archive', reason },
              { onSuccess: () => setArchiving(false) },
            )
          }}
        >
          <label htmlFor={`arch-${routine.id}`}>Motif de l’arrêt</label>
          <input
            id={`arch-${routine.id}`}
            required
            minLength={3}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
          <button className="button button--small button--primary" disabled={action.isPending}>
            Arrêter la routine
          </button>
          <button
            type="button"
            className="button button--small button--ghost"
            onClick={() => setArchiving(false)}
          >
            Annuler
          </button>
        </form>
      )}
      {action.isError && <Alert>{errorMessage(action.error)}</Alert>}
      {showOcc && (
        <div className="occ-list">
          {occurrences.isPending && <Skeleton lines={2} />}
          {occurrences.data?.length === 0 && (
            <p className="muted">Aucune occurrence sur la période.</p>
          )}
          {occurrences.data?.map((o) => (
            <OccurrenceCard
              key={o.id}
              spaceId={spaceId}
              occurrence={o}
              canWrite={canWrite}
              projects={projects}
              today={today}
              showDate
            />
          ))}
        </div>
      )}
    </li>
  )
}

export function RoutinesPage() {
  const { space } = useOutletContext<SpaceContext>()
  const routines = useRoutines(space.id)
  const canWrite = canWriteSpace(space.role)
  const today = todayIso(space.timezone)
  const [panel, setPanel] = useState<null | 'new' | 'profiles'>(null)
  const [showArchived, setShowArchived] = useState(false)
  const all = routines.data ?? []
  const shown = all.filter((r) => showArchived || !r.archived)

  return (
    <div className="page-content">
      <PageHeader
        title="Routines de pilotage"
        subtitle="Vos rendez-vous réguliers de préparation, de relance et de bouclage. Chaque occurrence a sa checklist et son résultat."
        actions={
          canWrite &&
          !panel && (
            <>
              <button type="button" className="button" onClick={() => setPanel('profiles')}>
                Routines types
              </button>
              <button
                type="button"
                className="button button--primary"
                onClick={() => setPanel('new')}
              >
                Nouvelle routine
              </button>
            </>
          )
        }
      />
      {panel && (
        <section
          className="card-panel"
          aria-label={panel === 'new' ? 'Nouvelle routine' : 'Routines types'}
        >
          {panel === 'new' ? (
            <RoutineForm spaceId={space.id} today={today} onDone={() => setPanel(null)} />
          ) : (
            <Profiles spaceId={space.id} onDone={() => setPanel(null)} />
          )}
        </section>
      )}
      <section className="card-panel" aria-label="Routines">
        {routines.isError && <Alert>{errorMessage(routines.error)}</Alert>}
        {routines.isPending ? (
          <Skeleton lines={4} />
        ) : shown.length === 0 ? (
          <p className="muted">
            Aucune routine pour l’instant. Commencez par les routines types, ou créez la vôtre.
          </p>
        ) : (
          <ul className="item-list">
            {shown.map((r) => (
              <RoutineRow
                key={r.id}
                spaceId={space.id}
                routine={r}
                canWrite={canWrite}
                today={today}
              />
            ))}
          </ul>
        )}
        {all.some((r) => r.archived) && (
          <label className="checkbox">
            <input
              type="checkbox"
              checked={showArchived}
              onChange={(e) => setShowArchived(e.target.checked)}
            />
            Afficher les routines arrêtées
          </label>
        )}
      </section>
    </div>
  )
}
