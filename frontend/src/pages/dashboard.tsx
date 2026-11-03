import type { ReactNode } from 'react'
import { Link, useOutletContext } from 'react-router'
import {
  BellIcon,
  BlockedIcon,
  CalendarIcon,
  ClockIcon,
  FolderIcon,
  PlusIcon,
} from '../components/icons'
import { PageHeader } from '../components/ui'
import type { SpaceContext } from './space-layout'

const DAY_MS = 86_400_000

/** La date du jour dans le fuseau de l'espace, à minuit UTC (pour compter les jours sans décalage). */
function todayIn(timeZone: string): Date {
  const iso = new Intl.DateTimeFormat('en-CA', { timeZone }).format(new Date())
  return new Date(`${iso}T00:00:00Z`)
}

function formatUtc(date: Date, options: Intl.DateTimeFormatOptions) {
  return new Intl.DateTimeFormat('fr-FR', { ...options, timeZone: 'UTC' }).format(date)
}

function capitalize(text: string) {
  return text.charAt(0).toUpperCase() + text.slice(1)
}

/** Trois mois centrés sur le mois en cours, et la position d'aujourd'hui dans cette période. */
function timelineWindow(today: Date) {
  const year = today.getUTCFullYear()
  const month = today.getUTCMonth()
  const start = new Date(Date.UTC(year, month - 1, 1))
  const end = new Date(Date.UTC(year, month + 2, 1))
  const total = (end.getTime() - start.getTime()) / DAY_MS
  const months = [0, 1, 2].map((i) => {
    const from = new Date(Date.UTC(year, month - 1 + i, 1))
    const to = new Date(Date.UTC(year, month + i, 1))
    return {
      label: capitalize(formatUtc(from, { month: 'long' })),
      days: (to.getTime() - from.getTime()) / DAY_MS,
    }
  })
  const todayOffset = (today.getTime() - start.getTime()) / DAY_MS + 0.5
  return { months, todayPercent: (todayOffset / total) * 100 }
}

function StatCard({
  icon,
  tone,
  title,
  children,
}: {
  icon: ReactNode
  tone: 'danger' | 'action' | 'info'
  title: string
  children: ReactNode
}) {
  return (
    <section className="stat-card" aria-label={title}>
      <div className="stat-card__head">
        <span className={`icon-tile icon-tile--${tone}`}>{icon}</span>
        <h2 className="stat-card__title">{title}</h2>
      </div>
      <div className="stat-card__body">{children}</div>
    </section>
  )
}

export function DashboardPage() {
  const { space, me } = useOutletContext<SpaceContext>()
  const today = todayIn(space.timezone)
  const week = Array.from({ length: 7 }, (_, i) => new Date(today.getTime() + i * DAY_MS))
  const { months, todayPercent } = timelineWindow(today)
  const firstName = me.user.display_name.split(/\s+/)[0]
  const isOwner = space.role === 'owner'

  return (
    <div className="page-content">
      <PageHeader
        title={`Bonjour, ${firstName}`}
        subtitle={`${capitalize(formatUtc(today, { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' }))} · ${space.name}`}
        actions={
          isOwner && (
            <Link className="button button--primary" to={`/espaces/${space.id}/membres`}>
              Inviter des membres <PlusIcon />
            </Link>
          )
        }
      />

      <div className="stat-grid">
        <StatCard icon={<ClockIcon />} tone="danger" title="En retard">
          <span className="stat-card__value">0</span>
          <span className="stat-card__note">Aucune échéance dépassée</span>
        </StatCard>
        <StatCard icon={<BlockedIcon />} tone="action" title="Bloqués">
          <span className="stat-card__value">0</span>
          <span className="stat-card__note">Aucun projet bloqué</span>
        </StatCard>
        <StatCard icon={<CalendarIcon />} tone="info" title="Échéances · 7 jours">
          <span className="stat-card__value">0</span>
          <div
            className="dot-week"
            role="img"
            aria-label="Aucune échéance dans les sept prochains jours"
          >
            {week.map((day) => (
              <div key={day.toISOString()} className="dot-week__day">
                {[0, 1, 2, 3].map((slot) => (
                  <span key={slot} className="dot" />
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
            <div
              className="timeline__months"
              style={{ gridTemplateColumns: months.map((m) => `${m.days}fr`).join(' ') }}
            >
              {months.map((m) => (
                <span key={m.label}>{m.label}</span>
              ))}
            </div>
            <div className="timeline__track">
              <div
                className="timeline__today"
                style={{ left: `${todayPercent}%` }}
                aria-hidden="true"
              />
              <p className="timeline__empty">Aucun projet daté pour l’instant.</p>
            </div>
          </div>
          <p className="card-panel__foot">
            Le calendrier montre les dates prévues. Il ne mesure pas l’avancement.
          </p>
        </section>

        <section className="card-panel dashboard-row__side" aria-label="À faire aujourd’hui">
          <div className="card-panel__head">
            <h2>À faire aujourd’hui</h2>
          </div>
          <div className="mini-empty">
            <span className="icon-tile icon-tile--neutral">
              <BellIcon size={18} />
            </span>
            <p>
              <strong>Rien à faire aujourd’hui.</strong>
              <br />
              Les rappels apparaîtront ici dès que les projets auront des échéances.
            </p>
          </div>
        </section>
      </div>

      <section className="card-panel card-panel--flush" aria-label="Projets actifs">
        <div className="card-panel__head card-panel__head--padded">
          <h2>Projets actifs</h2>
        </div>
        <div className="table-scroll table-scroll--flush">
          <table className="table">
            <thead>
              <tr>
                <th scope="col">Projet</th>
                <th scope="col">Filiale</th>
                <th scope="col">Responsable</th>
                <th scope="col">Prochaine étape</th>
                <th scope="col">Échéance</th>
                <th scope="col">Statut</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td colSpan={6}>
                  <div className="table-empty">
                    <span className="icon-tile icon-tile--action">
                      <FolderIcon />
                    </span>
                    <span>
                      <strong>Aucun projet pour l’instant.</strong> La création des projets et des
                      tâches arrive à la prochaine étape.
                    </span>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}
