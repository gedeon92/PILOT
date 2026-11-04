import { useRef, useState, type ReactNode } from 'react'
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
import { ATTENTION, matchesAttention } from '../attention'
import { useFitRows } from '../fit'
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
  const content = (
    <>
      <div className="stat-card__head">
        <span className={`icon-tile icon-tile--${tone}`}>{icon}</span>
        <h2 className="stat-card__title">{title}</h2>
      </div>
      <div className="stat-card__body">
        <span className="stat-card__value">{value}</span>
        {children}
      </div>
    </>
  )
  if (!to)
    return (
      <section className="stat-card" aria-label={title}>
        {content}
      </section>
    )
  return (
    <Link
      className="stat-card stat-card--link"
      to={to}
      aria-label={`${title} : ${value}, voir la liste`}
    >
      {content}
    </Link>
  )
}

function NameList({ projects, detail }: { projects: Project[]; detail: (p: Project) => string }) {
  return (
    <ul className="stat-card__list">
      {projects.slice(0, 2).map((p) => (
        <li key={p.id}>
          <strong>{p.title}</strong>
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
    if (p.risk_level === 'high')
      items.push({
        project: p,
        label: 'Vigilance',
        tone: 'danger',
        text: p.risk_note ?? 'Vigilance élevée',
      })
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
  const late = open.filter((p) => matchesAttention(p, 'retard', today))
  const blocked = open.filter((p) => matchesAttention(p, 'bloques', today))
  const week = Array.from({ length: 7 }, (_, i) => addDays(today, i))
  const dueByDay = week.map((day) => open.filter((p) => p.due_date === day).length)
  const dueThisWeek = dueByDay.reduce((a, b) => a + b, 0)
  const URGENCY: Record<Tone, number> = {
    danger: 0,
    warn: 1,
    info: 2,
    violet: 2,
    ok: 3,
    neutral: 3,
  }
  const toDo = todos(open, today).sort((a, b) => URGENCY[a.tone] - URGENCY[b.tone])
  const firstName = me.user.display_name.split(/\s+/)[0]
  const base = `/espaces/${space.id}`
  // Timeline et liste dans le même bloc : tout l'essentiel tient sur un écran.
  const [view, setView] = useState<'timeline' | 'list'>('timeline')
  // La page tient dans l'écran : la timeline affiche autant de lignes que la hauteur le permet.
  const stackRef = useRef<HTMLDivElement>(null)
  const fitRows = useFitRows(stackRef, { rowHeight: 50, reserved: 360, fallback: 12 })
  const [allTodos, setAllTodos] = useState(false)
  const TODO_STRIP = 3

  return (
    <div className="page-content page-content--fit">
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
        <StatCard
          icon={<ClockIcon />}
          tone="danger"
          title="En retard"
          value={late.length}
          to={`${base}/projets?attention=retard`}
        >
          {late.length ? (
            <NameList
              projects={late}
              detail={(p) =>
                p.due_date && p.due_date < today ? 'échéance dépassée' : `${p.late_tasks} tâche(s)`
              }
            />
          ) : (
            <span className="stat-card__note">Aucun retard</span>
          )}
        </StatCard>
        <StatCard
          icon={<BlockedIcon />}
          tone="action"
          title="Bloqués"
          value={blocked.length}
          to={`${base}/projets?attention=bloques`}
        >
          {blocked.length ? (
            <NameList projects={blocked} detail={(p) => p.situation ?? 'à débloquer'} />
          ) : (
            <span className="stat-card__note">Aucun projet bloqué</span>
          )}
        </StatCard>
        <StatCard
          icon={<CalendarIcon />}
          tone="info"
          title="Échéances · 7 jours"
          to={`${base}/projets?attention=semaine`}
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

      <div className="dashboard-stack" ref={stackRef}>
        <section className="card-panel dashboard-row__main" aria-labelledby="main-view-title">
          <div className="card-panel__head">
            <h2 id="main-view-title">
              {view === 'timeline' ? 'Timeline des projets' : 'Projets actifs'}
            </h2>
            <div className="card-panel__tools">
              <div className="segmented" role="group" aria-label="Affichage">
                <button
                  type="button"
                  aria-pressed={view === 'timeline'}
                  className={
                    view === 'timeline' ? 'segmented__item segmented__item--on' : 'segmented__item'
                  }
                  onClick={() => setView('timeline')}
                >
                  Timeline
                </button>
                <button
                  type="button"
                  aria-pressed={view === 'list'}
                  className={
                    view === 'list' ? 'segmented__item segmented__item--on' : 'segmented__item'
                  }
                  onClick={() => setView('list')}
                >
                  Liste · {open.length}
                </button>
              </div>
              <Link
                className="button button--small"
                to={view === 'timeline' ? `${base}/timeline` : `${base}/projets`}
              >
                {view === 'timeline' ? 'Timeline complète' : 'Tous les projets'}
              </Link>
            </div>
          </div>
          {view === 'timeline' ? (
            <ProjectTimeline
              projects={open}
              tasks={tasks.data ?? []}
              today={today}
              spaceId={space.id}
              compact
              maxRows={fitRows}
            />
          ) : (
            <div className="card-panel__bleed">
              <ProjectTable
                projects={open.slice(0, Math.max(3, fitRows - 1))}
                compact
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
            </div>
          )}
        </section>

        <section className="card-panel dashboard-row__side" aria-label="À faire aujourd’hui">
          <div className="card-panel__head">
            <h2>
              À faire aujourd’hui {toDo.length > 0 && <span className="count">{toDo.length}</span>}
            </h2>
            {toDo.length > TODO_STRIP && (
              <button
                type="button"
                className="button button--small"
                aria-expanded={allTodos}
                onClick={() => setAllTodos((v) => !v)}
              >
                {allTodos ? 'Réduire' : `Voir les ${toDo.length} rappels`}
              </button>
            )}
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
            <>
              <ul className="todo-list todo-list--grid">
                {(allTodos ? toDo : toDo.slice(0, TODO_STRIP)).map((item, i) => (
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
              </ul>
            </>
          )}
          <details className="rules">
            <summary>Comment c’est calculé ?</summary>
            <ul>
              <li>
                <strong>Jour J / En retard</strong> : échéance aujourd’hui ou dépassée (projet
                ouvert).
              </li>
              <li>
                <strong>Bloqué</strong> : {ATTENTION.bloques.rule}
              </li>
              <li>
                <strong>Tâches</strong> : au moins une tâche ouverte dont l’échéance est passée.
              </li>
              <li>
                <strong>Décision</strong> : une décision attendue est renseignée sur le projet.
              </li>
              <li>
                <strong>Vigilance</strong> : vigilance « Élevé » sur le projet.
              </li>
              <li>
                <strong>Suivi J+15 / Bilan</strong> : événement passé, dans les 15 jours qui
                suivent, puis au-delà sans bilan.
              </li>
              <li>
                <strong>À compléter</strong> : {ATTENTION['a-completer'].rule}
              </li>
            </ul>
            <p>
              Ordre : rouge (urgent), puis orange (à surveiller), puis gris. Les dates s’entendent
              dans le fuseau de l’espace. Un signal invite à vérifier, il ne juge pas le projet.
            </p>
          </details>
        </section>
      </div>
    </div>
  )
}
