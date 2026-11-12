import { useState, type FormEvent } from 'react'
import { useOutletContext, useSearchParams } from 'react-router'
import { errorMessage, type Indicator } from '../api/client'
import {
  useCapacity,
  useIndicators,
  useMembers,
  useSetCapacity,
  useSetTargets,
} from '../api/queries'
import { Alert, PageHeader, Skeleton, StatusPill } from '../components/ui'
import { addDays, formatDay, formatMoment, todayIso } from '../labels'
import type { SpaceContext } from './space-layout'

/** Étape F6 (cahier V2, VIS02–VIS03 et CAP02) : indicateurs de référence et charge face à la
 * capacité. Chaque chiffre montre sa période, son périmètre, sa cible et ses cas ; une donnée
 * absente est dite « non calculable » ou « non mesurée », jamais inventée. */

const PERIODS = [
  ['30', '30 derniers jours'],
  ['90', '90 derniers jours'],
  ['365', '12 derniers mois'],
] as const

function valueText(i: Indicator) {
  if (i.value === null)
    return i.na_reason?.startsWith('Non mesuré') ? 'Non mesuré' : 'Non calculable'
  return i.unit === '%' ? `${i.value.toLocaleString('fr-FR')} %` : String(i.value)
}

function targetText(i: Indicator) {
  const unit = i.unit === '%' ? ' %' : ''
  if (i.comparator === '<=')
    return i.target === 0 ? 'Cible : zéro' : `Cible : ${i.target}${unit} au plus`
  return `Cible : ${i.target}${unit} au moins`
}

function IndicatorsView({
  spaceId,
  canManage,
  today,
}: {
  spaceId: string
  canManage: boolean
  today: string
}) {
  const [days, setDays] = useState<string>('90')
  const start = addDays(today, -(Number(days) - 1))
  const data = useIndicators(spaceId, start, today)
  const setTargets = useSetTargets(spaceId)
  const [editing, setEditing] = useState(false)
  const [targets, setTargetsDraft] = useState<Record<string, string>>({})

  function submit(event: FormEvent) {
    event.preventDefault()
    const values = Object.fromEntries(
      Object.entries(targets)
        .filter(([, v]) => v !== '')
        .map(([k, v]) => [k, Number(v)]),
    )
    setTargets.mutate(values, { onSuccess: () => setEditing(false) })
  }

  return (
    <>
      <div className="filters" role="group" aria-label="Période des indicateurs">
        <select aria-label="Période" value={days} onChange={(e) => setDays(e.target.value)}>
          {PERIODS.map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
        {canManage && !editing && data.data && (
          <button
            type="button"
            className="button button--small button--ghost"
            onClick={() => {
              setTargetsDraft(
                Object.fromEntries(data.data.indicators.map((i) => [i.key, String(i.target)])),
              )
              setEditing(true)
            }}
          >
            Modifier les cibles
          </button>
        )}
      </div>
      {data.isError && <Alert>{errorMessage(data.error)}</Alert>}
      {data.isPending && <Skeleton lines={6} />}
      {data.data && (
        <>
          <p className="muted indicators__frame">
            Période : du {formatDay(data.data.start)} au {formatDay(data.data.end)} · Périmètre :{' '}
            {data.data.scope} · Calculé le {formatMoment(data.data.computed_at)}
          </p>
          {editing && (
            <form
              className="card-panel item-form"
              onSubmit={submit}
              aria-label="Cibles des indicateurs"
            >
              {data.data.indicators.map((i) => (
                <div className="field" key={i.key}>
                  <label htmlFor={`target-${i.key}`}>
                    {i.label} {i.unit === '%' ? '(%)' : '(nombre)'}
                  </label>
                  <input
                    id={`target-${i.key}`}
                    type="number"
                    min={0}
                    max={100}
                    step="any"
                    value={targets[i.key] ?? ''}
                    onChange={(e) => setTargetsDraft((t) => ({ ...t, [i.key]: e.target.value }))}
                  />
                </div>
              ))}
              {setTargets.isError && <Alert>{errorMessage(setTargets.error)}</Alert>}
              <div className="item-form__actions">
                <button className="button button--primary" disabled={setTargets.isPending}>
                  Enregistrer les cibles
                </button>
                <button
                  type="button"
                  className="button button--ghost"
                  onClick={() => setEditing(false)}
                >
                  Annuler
                </button>
              </div>
            </form>
          )}
          <div className="indicators">
            {data.data.indicators.map((i) => (
              <article
                key={i.key}
                className={`indicator indicator--${i.status}`}
                aria-labelledby={`ind-${i.key}`}
              >
                <header className="indicator__head">
                  <h2 id={`ind-${i.key}`}>{i.label}</h2>
                  <StatusPill
                    tone={i.status === 'ok' ? 'ok' : i.status === 'below' ? 'warn' : 'neutral'}
                  >
                    {i.status === 'ok'
                      ? 'Atteint'
                      : i.status === 'below'
                        ? 'Sous la cible'
                        : 'Sans mesure'}
                  </StatusPill>
                </header>
                <p className="indicator__value">{valueText(i)}</p>
                <p className="indicator__measure">{i.measure}</p>
                <p className="indicator__facts">
                  {targetText(i)}
                  {i.denominator !== null &&
                    i.unit === '%' &&
                    ` · ${i.numerator} sur ${i.denominator} cas`}
                  {i.cancelled > 0 && ` · ${i.cancelled} annulé(s), comptés à part`}
                </p>
                {i.na_reason && <p className="indicator__note">{i.na_reason}</p>}
                {i.note && <p className="indicator__note">{i.note}</p>}
              </article>
            ))}
          </div>
        </>
      )}
    </>
  )
}

function CapacityCell({
  spaceId,
  memberId,
  value,
  canEdit,
}: {
  spaceId: string
  memberId: string
  value: number | null
  canEdit: boolean
}) {
  const save = useSetCapacity(spaceId)
  const [editing, setEditing] = useState(false)
  const [hours, setHours] = useState(value === null ? '' : String(value))
  if (!editing) {
    return (
      <span className="capacity__cap">
        {value === null ? (
          <span className="capacity__unknown">Capacité à vérifier</span>
        ) : (
          `${value} h / sem.`
        )}
        {canEdit && (
          <button type="button" className="link-button" onClick={() => setEditing(true)}>
            {value === null ? 'Saisir' : 'Modifier'}
          </button>
        )}
      </span>
    )
  }
  return (
    <form
      className="inline-form"
      onSubmit={(e) => {
        e.preventDefault()
        save.mutate(
          { memberId, hours: hours === '' ? null : Number(hours) },
          { onSuccess: () => setEditing(false) },
        )
      }}
    >
      <label className="visually-hidden" htmlFor={`cap-${memberId}`}>
        Heures disponibles par semaine
      </label>
      <input
        id={`cap-${memberId}`}
        type="number"
        min={0}
        max={168}
        step="any"
        autoFocus
        value={hours}
        onChange={(e) => setHours(e.target.value)}
      />
      <button className="button button--small button--primary" disabled={save.isPending}>
        OK
      </button>
      {save.isError && <Alert>{errorMessage(save.error)}</Alert>}
    </form>
  )
}

function CapacityView({ spaceId, canManage }: { spaceId: string; canManage: boolean }) {
  const data = useCapacity(spaceId)
  const myMemberId = useMembers(spaceId).data?.find((m) => m.is_me)?.id
  if (data.isPending) return <Skeleton lines={5} />
  if (data.isError) return <Alert>{errorMessage(data.error)}</Alert>
  const { weeks, people, note } = data.data
  const cell = (hours: number, unestimated: number) =>
    hours === 0 && unestimated === 0
      ? '—'
      : `${hours} h${unestimated ? ` + ${unestimated} non estimée(s)` : ''}`
  return (
    <section className="card-panel card-panel--flush" aria-label="Charge et capacité">
      <p className="card-panel__help capacity__note">{note}</p>
      <div className="table-scroll">
        <table className="capacity">
          <thead>
            <tr>
              <th scope="col">Personne</th>
              <th scope="col">Capacité</th>
              <th scope="col">En retard</th>
              {weeks.map((w) => (
                <th scope="col" key={w}>
                  Sem. du {formatDay(w)}
                </th>
              ))}
              <th scope="col">Sans échéance</th>
            </tr>
          </thead>
          <tbody>
            {people.map((p) => (
              <tr key={p.member_id}>
                <th scope="row">
                  {p.name}
                  {p.sustained_overload && <StatusPill tone="danger">Surcharge durable</StatusPill>}
                </th>
                <td>
                  <CapacityCell
                    spaceId={spaceId}
                    memberId={p.member_id}
                    value={p.capacity}
                    canEdit={canManage || p.member_id === myMemberId}
                  />
                </td>
                <td>{cell(p.late_hours, p.late_unestimated)}</td>
                {p.weeks.map((w) => (
                  <td key={w.start} className={w.over ? 'capacity__over' : undefined}>
                    {cell(w.hours, w.unestimated)}
                    {w.over && <span className="visually-hidden"> (au-dessus de la capacité)</span>}
                  </td>
                ))}
                <td>{cell(p.undated_hours, p.undated_unestimated)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

export function PilotagePage() {
  const { space } = useOutletContext<SpaceContext>()
  const [params, setParams] = useSearchParams()
  const view = params.get('vue') === 'charge' ? 'capacity' : 'indicators'
  const today = todayIso(space.timezone)
  const canManage = space.role === 'owner'
  const tabs = (
    <div className="segmented" role="group" aria-label="Vue">
      {(
        [
          ['indicators', 'Indicateurs'],
          ['capacity', 'Charge et capacité'],
        ] as const
      ).map(([key, label]) => (
        <button
          key={key}
          type="button"
          className={view === key ? 'segmented__item segmented__item--on' : 'segmented__item'}
          aria-pressed={view === key}
          onClick={() => setParams(key === 'capacity' ? { vue: 'charge' } : {}, { replace: true })}
        >
          {label}
        </button>
      ))}
    </div>
  )
  return (
    <div className="page-content">
      <PageHeader
        title="Pilotage"
        subtitle={
          view === 'capacity'
            ? 'Heures estimées des tâches ouvertes face à la capacité déclarée, semaine par semaine.'
            : 'Indicateurs de référence, calculés à partir de vos données, avec leur mode de calcul.'
        }
        actions={tabs}
      />
      {view === 'indicators' ? (
        <IndicatorsView spaceId={space.id} canManage={canManage} today={today} />
      ) : (
        <CapacityView spaceId={space.id} canManage={canManage} />
      )}
    </div>
  )
}
