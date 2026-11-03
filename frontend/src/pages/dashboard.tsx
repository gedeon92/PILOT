import type { ReactNode } from 'react'
import { Link, useOutletContext } from 'react-router'
import type { Project } from '../api/client'
import { useProjects } from '../api/queries'
import {
  BellIcon,
  BlockedIcon,
  CalendarIcon,
  ClockIcon,
  FolderIcon,
  PlusIcon,
} from '../components/icons'
import { ProjectTable } from '../components/project-table'
import { PageHeader, type Tone } from '../components/ui'
import { addDays, formatDay, isClosedProject, PROJECT_STATUS, todayIso } from '../labels'
import type { SpaceContext } from './space-layout'

const DAY_MS = 86_400_000

function utc(iso: string) {
  return new Date(`${iso}T00:00:00Z`)
}

function formatUtc(iso: string, options: Intl.DateTimeFormatOptions) {
  return new Intl.DateTimeFormat('fr-FR', { ...options, timeZone: 'UTC' }).format(utc(iso))
}

function capitalize(text: string) {
  return text.charAt(0).toUpperCase() + text.slice(1)
}

/** Trois mois centrés sur le mois en cours. */
function timelineWindow(today: string) {
  const d = utc(today)
  const year = d.getUTCFullYear()
  const month = d.getUTCMonth()
  const start = Date.UTC(year, month - 1, 1)
  const end = Date.UTC(year, month + 2, 1)
  const months = [0, 1, 2].map((i) => {
    const from = Date.UTC(year, month - 1 + i, 1)
    const to = Date.UTC(year, month + i, 1)
    return {
      label: capitalize(
        new Intl.DateTimeFormat('fr-FR', { month: 'long', timeZone: 'UTC' }).format(from),
      ),
      days: (to - from) / DAY_MS,
    }
  })
  const percent = (iso: string) => ((utc(iso).getTime() - start) / (end - start)) * 100
  return { months, percent, start, end }
}

const TONE_DOT: Record<Tone, string> = {
  info: '#2563EB',
  danger: '#DC2626',
  warn: '#CA8A04',
  violet: '#7C3AED',
  ok: '#16A34A',
  neutral: '#71717A',
}

/** Position d'un projet sur la timeline : dates de début/fin, échéance ou période à préciser. */
function span(p: Project): { from: string; to: string; window: boolean } | null {
  if (p.start_date || p.end_date) {
    const from = p.start_date ?? p.end_date!
    return { from, to: p.end_date ?? p.due_date ?? from, window: false }
  }
  if (p.window_start && p.window_end)
    return { from: p.window_start, to: p.window_end, window: true }
  if (p.due_date) return { from: p.due_date, to: p.due_date, window: false }
  return null
}

function StatCard({
  icon,
  tone,
  title,
  value,
  to,
  children,
}: {
  icon: ReactNode
  tone: 'danger' | 'action' | 'info'
  title: string
  value: number
  to?: string
  children: ReactNode
}) {
  return (
    <section className="stat-card" aria-label={title}>
      <div className="stat-card__head">
        <span className={`icon-tile icon-tile--${tone}`}>{icon}</span>
        <h2 className="stat-card__title">{title}</h2>
      </div>
      <div className="stat-card__body">
        <span className="stat-card__value">{value}</span>
        {children}
      </div>
      {to && value > 0 && (
        <Link className="stat-card__link" to={to}>
          Voir la liste
        </Link>
      )}
    </section>
  )
}

function NameList({
  projects,
  spaceId,
  detail,
}: {
  projects: Project[]
  spaceId: string
  detail: (p: Project) => string
}) {
  return (
    <ul className="stat-card__list">
      {projects.slice(0, 3).map((p) => (
        <li key={p.id}>
          <Link to={`/espaces/${spaceId}/projets/${p.id}`}>{p.title}</Link>
          <span> · {detail(p)}</span>
        </li>
      ))}
    </ul>
  )
}

type Todo = { project: Project; label: string; tone: Tone; text: string }

function todos(open: Project[], today: string): Todo[] {
  const items: Todo[] = []
  for (const p of open) {
    // Événement passé : suivi de 15 jours (relances, exploitation, bilan), puis bilan attendu.
    const eventEnd = p.event ? (p.end_date ?? p.start_date ?? p.due_date) : null
    if (p.event?.follow_up_until && eventEnd && today > eventEnd) {
      if (today <= p.event.follow_up_until)
        items.push({
          project: p,
          label: 'Suivi J+15',
          tone: 'warn',
          text: `Relances et bilan jusqu’au ${formatDay(p.event.follow_up_until)}`,
        })
      else
        items.push({
          project: p,
          label: 'Bilan',
          tone: 'danger',
          text: 'Suivi terminé : bilan à rédiger',
        })
      continue
    }
    if (p.due_date === today)
      items.push({
        project: p,
        label: 'Jour J',
        tone: 'danger',
        text: p.next_step ?? 'Échéance aujourd’hui',
      })
    else if (p.due_date && p.due_date < today)
      items.push({
        project: p,
        label: 'En retard',
        tone: 'danger',
        text: p.next_step ?? 'Échéance dépassée',
      })
    if (p.status === 'blocked')
      items.push({
        project: p,
        label: 'Bloqué',
        tone: 'danger',
        text: p.situation ?? 'Projet bloqué',
      })
    if (p.late_tasks > 0)
      items.push({
        project: p,
        label: 'Tâches',
        tone: 'warn',
        text: `${p.late_tasks} tâche(s) en retard`,
      })
    if (p.decision_needed)
      items.push({ project: p, label: 'Décision', tone: 'warn', text: p.decision_needed })
    if (!p.owner.name || !p.next_step)
      items.push({
        project: p,
        label: 'À compléter',
        tone: 'neutral',
        text: !p.owner.name ? 'Aucun responsable du suivi' : 'Aucune prochaine étape',
      })
  }
  return items
}

export function DashboardPage() {
  const { space, me } = useOutletContext<SpaceContext>()
  const projects = useProjects(space.id)
  const today = todayIso(space.timezone)
  const all = projects.data ?? []
  const open = all.filter((p) => !isClosedProject(p.status))
  const late = open.filter((p) => (p.due_date !== null && p.due_date < today) || p.late_tasks > 0)
  const blocked = open.filter((p) => p.status === 'blocked')
  const week = Array.from({ length: 7 }, (_, i) => addDays(today, i))
  const dueByDay = week.map((day) => open.filter((p) => p.due_date === day).length)
  const dueThisWeek = dueByDay.reduce((a, b) => a + b, 0)
  const timeline = timelineWindow(today)
  const rows = open
    .map((p) => ({ p, s: span(p) }))
    .filter(
      ({ s }) => s && utc(s.to).getTime() >= timeline.start && utc(s.from).getTime() < timeline.end,
    )
    .slice(0, 8)
  const toDo = todos(open, today)
  const firstName = me.user.display_name.split(/\s+/)[0]
  const base = `/espaces/${space.id}`
  const clamp = (n: number) => Math.min(100, Math.max(0, n))

  return (
    <div className="page-content">
      <PageHeader
        title={`Bonjour, ${firstName}`}
        subtitle={`${capitalize(formatUtc(today, { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' }))} · ${space.name}`}
        actions={
          space.role !== 'reader' && (
            <Link className="button button--primary" to={`${base}/projets/nouveau`}>
              Nouveau projet <PlusIcon />
            </Link>
          )
        }
      />

      <div className="stat-grid">
        <StatCard icon={<ClockIcon />} tone="danger" title="En retard" value={late.length}>
          {late.length ? (
            <NameList
              projects={late}
              spaceId={space.id}
              detail={(p) =>
                p.due_date && p.due_date < today ? 'échéance dépassée' : `${p.late_tasks} tâche(s)`
              }
            />
          ) : (
            <span className="stat-card__note">Aucune échéance dépassée</span>
          )}
        </StatCard>
        <StatCard
          icon={<BlockedIcon />}
          tone="action"
          title="Bloqués"
          value={blocked.length}
          to={`${base}/projets`}
        >
          {blocked.length ? (
            <NameList
              projects={blocked}
              spaceId={space.id}
              detail={(p) => p.situation ?? 'à débloquer'}
            />
          ) : (
            <span className="stat-card__note">Aucun projet bloqué</span>
          )}
        </StatCard>
        <StatCard
          icon={<CalendarIcon />}
          tone="info"
          title="Échéances · 7 jours"
          value={dueThisWeek}
        >
          <div
            className="dot-week"
            role="img"
            aria-label={`Échéances par jour : ${week.map((d, i) => `${formatUtc(d, { weekday: 'long' })} ${dueByDay[i]}`).join(', ')}`}
          >
            {week.map((day, i) => (
              <div key={day} className="dot-week__day">
                {[3, 2, 1, 0].map((slot) => (
                  <span key={slot} className={slot < dueByDay[i] ? 'dot dot--on' : 'dot'} />
                ))}
                <span className="dot-week__label">
                  {capitalize(formatUtc(day, { weekday: 'short' }).slice(0, 2))}
                </span>
              </div>
            ))}
          </div>
        </StatCard>
      </div>

      <div className="dashboard-row">
        <section className="card-panel dashboard-row__main" aria-label="Timeline des projets">
          <div className="card-panel__head">
            <h2>Timeline des projets</h2>
            <span className="chip chip--action">
              Aujourd’hui · {formatUtc(today, { day: 'numeric', month: 'short' })}
            </span>
          </div>
          <div className="timeline">
            <div className="timeline__grid">
              <span />
              <div
                className="timeline__months"
                style={{ gridTemplateColumns: timeline.months.map((m) => `${m.days}fr`).join(' ') }}
              >
                {timeline.months.map((m) => (
                  <span key={m.label}>{m.label}</span>
                ))}
              </div>
            </div>
            {rows.length === 0 ? (
              <div className="timeline__track">
                <div
                  className="timeline__today"
                  style={{ left: `${timeline.percent(today)}%` }}
                  aria-hidden="true"
                />
                <p className="timeline__empty">Aucun projet daté sur cette période.</p>
              </div>
            ) : (
              <div className="timeline__rows">
                <div
                  className="timeline__today timeline__today--rows"
                  style={{
                    left: `calc(140px + (100% - 140px) * ${timeline.percent(today) / 100})`,
                  }}
                  aria-hidden="true"
                />
                {rows.map(({ p, s }) => {
                  const left = clamp(timeline.percent(s!.from))
                  const right = clamp(timeline.percent(addDays(s!.to, 1)))
                  const color = TONE_DOT[PROJECT_STATUS[p.status].tone]
                  return (
                    <div key={p.id} className="timeline__row">
                      <Link className="timeline__label" to={`${base}/projets/${p.id}`}>
                        {p.title}
                      </Link>
                      <div className="timeline__lane">
                        <span
                          className={
                            s!.window ? 'timeline__bar timeline__bar--window' : 'timeline__bar'
                          }
                          style={{
                            left: `${left}%`,
                            width: `max(${right - left}%, 10px)`,
                            ['--bar' as string]: color,
                          }}
                          title={`${p.title} · ${PROJECT_STATUS[p.status].label}${s!.window ? ' · période à préciser' : ''}`}
                        />
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
          <p className="card-panel__foot">
            Le calendrier montre les dates prévues. Il ne mesure pas l’avancement.
          </p>
        </section>

        <section className="card-panel dashboard-row__side" aria-label="À faire aujourd’hui">
          <div className="card-panel__head">
            <h2>À faire aujourd’hui</h2>
          </div>
          {toDo.length === 0 ? (
            <div className="mini-empty">
              <span className="icon-tile icon-tile--neutral">
                <BellIcon size={18} />
              </span>
              <p>
                <strong>Rien à faire aujourd’hui.</strong>
                <br />
                Les rappels apparaissent ici dès que les projets ont des échéances.
              </p>
            </div>
          ) : (
            <ul className="todo-list">
              {toDo.slice(0, 6).map((item, i) => (
                <li key={`${item.project.id}-${i}`}>
                  <Link className="todo" to={`${base}/projets/${item.project.id}`}>
                    <span className="todo__text">
                      <span className="todo__title">{item.project.title}</span>
                      <span className="todo__detail">{item.text}</span>
                    </span>
                    <span className={`todo__tag todo__tag--${item.tone}`}>{item.label}</span>
                  </Link>
                </li>
              ))}
              {toDo.length > 6 && <li className="muted">… et {toDo.length - 6} autre(s)</li>}
            </ul>
          )}
        </section>
      </div>

      <section className="card-panel card-panel--flush" aria-label="Projets actifs">
        <div className="card-panel__head card-panel__head--padded">
          <h2>Projets actifs</h2>
          {open.length > 0 && (
            <Link className="button button--small" to={`${base}/projets`}>
              Tous les projets
            </Link>
          )}
        </div>
        <ProjectTable
          projects={open.slice(0, 8)}
          spaceId={space.id}
          today={today}
          empty={
            <div className="table-empty">
              <span className="icon-tile icon-tile--action">
                <FolderIcon />
              </span>
              <span>
                <strong>{projects.isPending ? 'Chargement…' : 'Aucun projet actif.'}</strong>{' '}
                {!projects.isPending &&
                  space.role !== 'reader' &&
                  'Créez le premier avec « Nouveau projet ».'}
              </span>
            </div>
          }
        />
      </section>
    </div>
  )
}
