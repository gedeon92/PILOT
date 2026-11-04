import type { ReactNode } from 'react'
import { Link, useOutletContext } from 'react-router'
import type { Project } from '../api/client'
import { useProjects, useSpaceTasks } from '../api/queries'
import {
  BellIcon,
  BlockedIcon,
  CalendarIcon,
  ClockIcon,
  FolderIcon,
  PlusIcon,
} from '../components/icons'
import { ProjectTable } from '../components/project-table'
import { ProjectTimeline } from '../components/timeline'
import { PageHeader, type Tone } from '../components/ui'
import { addDays, formatDay, isClosedProject, todayIso } from '../labels'
import type { SpaceContext } from './space-layout'

function utc(iso: string) {
  return new Date(`${iso}T00:00:00Z`)
}

function formatUtc(iso: string, options: Intl.DateTimeFormatOptions) {
  return new Intl.DateTimeFormat('fr-FR', { ...options, timeZone: 'UTC' }).format(utc(iso))
}

function capitalize(text: string) {
  return text.charAt(0).toUpperCase() + text.slice(1)
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
  const tasks = useSpaceTasks(space.id)
  const today = todayIso(space.timezone)
  const all = projects.data ?? []
  const open = all.filter((p) => !isClosedProject(p.status))
  const late = open.filter((p) => (p.due_date !== null && p.due_date < today) || p.late_tasks > 0)
  const blocked = open.filter((p) => p.status === 'blocked')
  const week = Array.from({ length: 7 }, (_, i) => addDays(today, i))
  const dueByDay = week.map((day) => open.filter((p) => p.due_date === day).length)
  const dueThisWeek = dueByDay.reduce((a, b) => a + b, 0)
  const toDo = todos(open, today)
  const firstName = me.user.display_name.split(/\s+/)[0]
  const base = `/espaces/${space.id}`

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

      <section className="card-panel" aria-label="Timeline des projets">
        <div className="card-panel__head">
          <h2>Timeline des projets</h2>
          <Link className="button button--small" to={`${base}/timeline`}>
            Timeline complète
          </Link>
        </div>
        <ProjectTimeline
          projects={open}
          tasks={tasks.data ?? []}
          today={today}
          spaceId={space.id}
          compact
        />
        <p className="card-panel__foot">
          Le calendrier montre les dates prévues. Il ne mesure pas l’avancement.
        </p>
      </section>

      <div className="dashboard-row">
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
