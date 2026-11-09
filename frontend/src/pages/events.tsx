import { useMemo, useState } from 'react'
import { Link, useOutletContext } from 'react-router'
import { canWriteSpace, errorMessage } from '../api/client'
import { useCatalog, useProjects } from '../api/queries'
import { colorHex } from '../colors'
import { CalendarIcon, PlusIcon } from '../components/icons'
import { ProjectTable } from '../components/project-table'
import { Alert, PageHeader } from '../components/ui'
import { addDays, formatDay, todayIso } from '../labels'
import type { SpaceContext } from './space-layout'
import { eventDays, findOverlaps } from '../events'
import { countryFlag } from '../countries'

function monthLabel(year: number, month: number) {
  const text = new Intl.DateTimeFormat('fr-FR', {
    month: 'long',
    year: 'numeric',
    timeZone: 'UTC',
  }).format(Date.UTC(year, month, 1))
  return text.charAt(0).toUpperCase() + text.slice(1)
}

/** Semaines du mois (lundi → dimanche), en jours AAAA-MM-JJ. */
function monthGrid(year: number, month: number): string[][] {
  const first = new Date(Date.UTC(year, month, 1))
  const offset = (first.getUTCDay() + 6) % 7
  let day = addDays(first.toISOString().slice(0, 10), -offset)
  const weeks: string[][] = []
  do {
    const week = Array.from({ length: 7 }, (_, i) => addDays(day, i))
    weeks.push(week)
    day = addDays(day, 7)
  } while (new Date(`${day}T00:00:00Z`).getUTCMonth() === month)
  return weeks
}

const WEEKDAYS = ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim']

export function EventsPage() {
  const { space } = useOutletContext<SpaceContext>()
  const today = todayIso(space.timezone)
  const [program, setProgram] = useState('')
  const [portfolio, setPortfolio] = useState('')
  const [entity, setEntity] = useState('')
  const [country, setCountry] = useState('')
  const [showCancelled, setShowCancelled] = useState(false)
  const [cursor, setCursor] = useState(() => {
    const d = new Date(`${today}T00:00:00Z`)
    return { year: d.getUTCFullYear(), month: d.getUTCMonth() }
  })
  const programs = useCatalog(space.id, 'programs')
  const portfolios = useCatalog(space.id, 'portfolios')
  const entities = useCatalog(space.id, 'entities')
  const query = useProjects(space.id, {
    kind: 'event',
    program_id: program,
    portfolio_id: portfolio,
  })

  const all = useMemo(() => query.data ?? [], [query.data])
  const countries = [
    ...new Set(all.map((p) => p.country).filter((c): c is string => Boolean(c))),
  ].sort()
  const events = all.filter(
    (p) =>
      (!entity || p.entity?.id === entity) &&
      (!country || p.country === country) &&
      (showCancelled || p.status !== 'cancelled'),
  )
  // Du plus proche au plus lointain ; les périodes puis les événements sans date ensuite.
  const sortKey = (p: (typeof events)[number]) => eventDays(p)?.from ?? p.window_start ?? '9999'
  events.sort((a, b) => sortKey(a).localeCompare(sortKey(b)))
  const overlaps = findOverlaps(events)
  const undated = events.filter((p) => !eventDays(p) && !p.window_start)
  const weeks = monthGrid(cursor.year, cursor.month)
  const monthStart = weeks[0][0]
  const monthEnd = weeks[weeks.length - 1][6]
  const windows = events.filter(
    (p) =>
      !eventDays(p) &&
      p.window_start &&
      p.window_end &&
      p.window_start <= monthEnd &&
      p.window_end >= monthStart,
  )
  const move = (delta: number) =>
    setCursor(({ year, month }) => {
      const d = new Date(Date.UTC(year, month + delta, 1))
      return { year: d.getUTCFullYear(), month: d.getUTCMonth() }
    })
  const base = `/espaces/${space.id}`

  return (
    <div className="page-content">
      <PageHeader
        title="Événements"
        subtitle="Les projets de nature « événement » : dates, lieux, éditions et chevauchements."
        actions={
          canWriteSpace(space.role) && (
            <Link className="button button--primary" to={`${base}/projets/nouveau`}>
              Nouvel événement <PlusIcon />
            </Link>
          )
        }
      />

      <div className="filters">
        <select aria-label="Programme" value={program} onChange={(e) => setProgram(e.target.value)}>
          <option value="">Tous les programmes</option>
          {programs.data?.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
        <select
          aria-label="Portefeuille"
          value={portfolio}
          onChange={(e) => setPortfolio(e.target.value)}
        >
          <option value="">Tous les portefeuilles</option>
          {portfolios.data?.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
        <select aria-label="Filiale" value={entity} onChange={(e) => setEntity(e.target.value)}>
          <option value="">Toutes les filiales</option>
          {entities.data?.map((e) => (
            <option key={e.id} value={e.id}>
              {e.name}
            </option>
          ))}
        </select>
        <select aria-label="Pays" value={country} onChange={(e) => setCountry(e.target.value)}>
          <option value="">Tous les pays</option>
          {countries.map((c) => (
            <option key={c} value={c}>
              {`${countryFlag(c)} ${c}`.trim()}
            </option>
          ))}
        </select>
        <label className="checkbox">
          <input
            type="checkbox"
            checked={showCancelled}
            onChange={(e) => setShowCancelled(e.target.checked)}
          />
          Afficher les éditions annulées
        </label>
      </div>

      {query.isError && <Alert>{errorMessage(query.error)}</Alert>}

      {overlaps.length > 0 && (
        <section className="card-panel card-panel--warn" aria-labelledby="overlaps-title">
          <h2 id="overlaps-title">Chevauchements à vérifier</h2>
          <p className="card-panel__help">
            Règle : au moins un jour commun entre deux événements non annulés.
          </p>
          <ul className="overlaps">
            {overlaps.map(({ a, b, from, to }) => (
              <li key={`${a.id}-${b.id}`}>
                <Link to={`${base}/projets/${a.id}`}>{a.title}</Link> et{' '}
                <Link to={`${base}/projets/${b.id}`}>{b.title}</Link> ·{' '}
                {from === to ? formatDay(from) : `${formatDay(from)} → ${formatDay(to)}`}
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="card-panel" aria-labelledby="calendar-title">
        <div className="card-panel__head">
          <h2 id="calendar-title">{monthLabel(cursor.year, cursor.month)}</h2>
          <div className="form-actions">
            <button
              type="button"
              className="button button--small"
              onClick={() => move(-1)}
              aria-label="Mois précédent"
            >
              ‹
            </button>
            <button
              type="button"
              className="button button--small"
              onClick={() => {
                const d = new Date(`${today}T00:00:00Z`)
                setCursor({ year: d.getUTCFullYear(), month: d.getUTCMonth() })
              }}
            >
              Aujourd’hui
            </button>
            <button
              type="button"
              className="button button--small"
              onClick={() => move(1)}
              aria-label="Mois suivant"
            >
              ›
            </button>
          </div>
        </div>
        <div className="calendar-scroll">
          <table className="calendar">
            <thead>
              <tr>
                {WEEKDAYS.map((d) => (
                  <th key={d} scope="col">
                    {d}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {weeks.map((week) => (
                <tr key={week[0]}>
                  {week.map((day) => {
                    const inMonth = new Date(`${day}T00:00:00Z`).getUTCMonth() === cursor.month
                    const onDay = events.filter((p) => {
                      const d = eventDays(p)
                      return d && d.from <= day && day <= d.to
                    })
                    const classes = ['calendar__day']
                    if (!inMonth) classes.push('calendar__day--out')
                    if (day === today) classes.push('calendar__day--today')
                    return (
                      <td key={day} className={classes.join(' ')}>
                        <span className="calendar__num">{Number(day.slice(8))}</span>
                        {onDay.map((p) => (
                          <Link
                            key={p.id}
                            to={`${base}/projets/${p.id}`}
                            className={
                              p.status === 'cancelled'
                                ? 'calendar__event calendar__event--cancelled'
                                : 'calendar__event'
                            }
                            style={{ ['--bar' as string]: colorHex(p.portfolio.color) }}
                            title={`${p.title}${p.date_certainty === 'confirmed' ? ' · confirmée' : ' · date non confirmée'}`}
                          >
                            {p.title}
                          </Link>
                        ))}
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {windows.length > 0 && (
          <div className="windows">
            <h3>Périodes à préciser</h3>
            <p className="card-panel__help">
              Ces événements ont une fenêtre, pas encore de jours fixés : ils ne durent pas toute la
              période.
            </p>
            <ul>
              {windows.map((p) => (
                <li key={p.id}>
                  <Link to={`${base}/projets/${p.id}`}>{p.title}</Link> ·{' '}
                  {formatDay(p.window_start)} – {formatDay(p.window_end)}
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>

      {undated.length > 0 && (
        <section className="card-panel" aria-labelledby="undated-title">
          <h2 id="undated-title">Sans date</h2>
          <p className="card-panel__help">Présents dans le suivi, sans date inventée.</p>
          <ul className="overlaps">
            {undated.map((p) => (
              <li key={p.id}>
                <Link to={`${base}/projets/${p.id}`}>{p.title}</Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="card-panel card-panel--flush" aria-label="Liste des événements">
        <div className="card-panel__head card-panel__head--padded">
          <h2>Tous les événements</h2>
        </div>
        <ProjectTable
          projects={events}
          spaceId={space.id}
          today={today}
          empty={
            <div className="table-empty">
              <span className="icon-tile icon-tile--info">
                <CalendarIcon />
              </span>
              <span>
                <strong>{query.isPending ? 'Chargement…' : 'Aucun événement.'}</strong>{' '}
                {!query.isPending &&
                  'Un événement est un projet dont le type est de nature « événement » (Paramètres et structure).'}
              </span>
            </div>
          }
        />
      </section>
    </div>
  )
}
