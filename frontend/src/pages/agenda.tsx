import { Link, useOutletContext, useSearchParams } from 'react-router'
import { canWriteSpace, errorMessage, type Agenda } from '../api/client'
import { useAgenda, useProjects } from '../api/queries'
import { OccurrenceCard } from '../components/occurrence-card'
import { useOpenTask } from '../components/task-dialog'
import { Alert, PageHeader, Skeleton, StatusPill } from '../components/ui'
import { addDays, formatDay, isClosedProject, todayIso } from '../labels'
import type { SpaceContext } from './space-layout'

/** Étape F5 (cahier V2, VIS01) : « Ma journée » et « Ma semaine ». Tout ce qui revient à la
 * personne — ses tâches, ses décisions à porter ou exécuter, ses jalons et ses routines — sur
 * une seule page. Ce qui est en retard reste en haut, jamais masqué. */

const KIND = { task: 'Tâche', decision: 'Décision', milestone: 'Jalon' } as const

function mondayOf(day: string): string {
  const weekday = (new Date(`${day}T00:00:00Z`).getUTCDay() + 6) % 7
  return addDays(day, -weekday)
}

function weekdayName(day: string) {
  return new Date(`${day}T00:00:00Z`).toLocaleDateString('fr-FR', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    timeZone: 'UTC',
  })
}

function Items({ spaceId, agenda, day }: { spaceId: string; agenda: Agenda; day?: string }) {
  const openTask = useOpenTask()
  const items = agenda.items.filter((i) =>
    day === undefined
      ? true
      : day === agenda.today
        ? i.late || i.due_date === day
        : i.due_date === day && !i.late,
  )
  if (items.length === 0) return null
  return (
    <ul className="agenda-items">
      {items.map((i) => (
        <li
          key={`${i.kind}-${i.id}`}
          className={i.late ? 'agenda-item agenda-item--late' : 'agenda-item'}
        >
          <span className="agenda-item__kind">{KIND[i.kind]}</span>
          <span className="agenda-item__main">
            {i.kind === 'task' ? (
              <button type="button" className="link-button" onClick={() => openTask(i.id)}>
                {i.title}
              </button>
            ) : i.kind === 'decision' ? (
              <Link to={`/espaces/${spaceId}/decisions`}>{i.title}</Link>
            ) : (
              <Link to={`/espaces/${spaceId}/projets/${i.project_id}`}>{i.title}</Link>
            )}
            <span className="agenda-item__meta">
              {[i.project_title, i.detail, i.due_date ? `échéance ${formatDay(i.due_date)}` : null]
                .filter(Boolean)
                .join(' · ')}
            </span>
          </span>
          {i.late && <StatusPill tone="danger">En retard</StatusPill>}
        </li>
      ))}
    </ul>
  )
}

export function AgendaPage() {
  const { space } = useOutletContext<SpaceContext>()
  const [params, setParams] = useSearchParams()
  const view = params.get('vue') === 'semaine' ? 'week' : 'day'
  const today = todayIso(space.timezone)
  const start = view === 'week' ? mondayOf(today) : today
  const end = view === 'week' ? addDays(start, 6) : today
  const agenda = useAgenda(space.id, start, end)
  const projects = (useProjects(space.id).data ?? []).filter((p) => !isClosedProject(p.status))
  const canWrite = canWriteSpace(space.role)
  const data = agenda.data

  const tabs = (
    <div className="segmented" role="group" aria-label="Période">
      {(
        [
          ['day', 'Ma journée'],
          ['week', 'Ma semaine'],
        ] as const
      ).map(([key, label]) => (
        <button
          key={key}
          type="button"
          className={view === key ? 'segmented__item segmented__item--on' : 'segmented__item'}
          aria-pressed={view === key}
          onClick={() => setParams(key === 'week' ? { vue: 'semaine' } : {}, { replace: true })}
        >
          {label}
        </button>
      ))}
    </div>
  )

  const days = view === 'week' ? Array.from({ length: 7 }, (_, n) => addDays(start, n)) : [today]
  const late = data?.occurrences.filter((o) => o.late) ?? []

  return (
    <div className="page-content">
      <PageHeader
        title={view === 'week' ? 'Ma semaine' : 'Ma journée'}
        subtitle={
          view === 'week'
            ? `Du ${formatDay(start)} au ${formatDay(end)} : vos actions, routines et jalons.`
            : `${weekdayName(today)} : vos décisions, actions, jalons et routines du jour.`
        }
        actions={tabs}
      />
      {agenda.isError && <Alert>{errorMessage(agenda.error)}</Alert>}
      {agenda.isPending && <Skeleton lines={5} />}
      {data && (
        <>
          {data.items.length === 0 && data.occurrences.length === 0 && (
            <section className="card-panel">
              <p className="muted">
                Rien à signaler pour cette période. Les tâches qui vous sont attribuées, les
                décisions que vous portez, vos jalons et vos routines apparaîtront ici.
              </p>
              <Link className="button button--small" to={`/espaces/${space.id}/routines`}>
                Mettre en place mes routines
              </Link>
            </section>
          )}
          {late.length > 0 && (
            <section className="card-panel card-panel--warn" aria-labelledby="agenda-late">
              <h2 id="agenda-late">Routines en retard</h2>
              <div className="occ-list">
                {late.map((o) => (
                  <OccurrenceCard
                    key={o.id}
                    spaceId={space.id}
                    occurrence={o}
                    canWrite={canWrite}
                    projects={projects}
                    today={data.today}
                    showDate
                  />
                ))}
              </div>
            </section>
          )}
          {days.map((day) => {
            const occurrences = data.occurrences.filter((o) => o.due_date === day && !o.late)
            const hasItems = data.items.some((i) =>
              day === data.today ? i.late || i.due_date === day : i.due_date === day && !i.late,
            )
            if (view === 'week' && occurrences.length === 0 && !hasItems) return null
            return (
              <section key={day} className="card-panel" aria-labelledby={`agenda-${day}`}>
                <h2 id={`agenda-${day}`} className="agenda-day">
                  {weekdayName(day)}
                  {day === data.today && view === 'week' && (
                    <StatusPill tone="violet">Aujourd’hui</StatusPill>
                  )}
                </h2>
                <Items spaceId={space.id} agenda={data} day={day} />
                {occurrences.length > 0 && (
                  <div className="occ-list">
                    {occurrences.map((o) => (
                      <OccurrenceCard
                        key={o.id}
                        spaceId={space.id}
                        occurrence={o}
                        canWrite={canWrite}
                        projects={projects}
                        today={data.today}
                      />
                    ))}
                  </div>
                )}
                {occurrences.length === 0 && !hasItems && <p className="muted">Rien de prévu.</p>}
              </section>
            )
          })}
        </>
      )}
    </div>
  )
}
