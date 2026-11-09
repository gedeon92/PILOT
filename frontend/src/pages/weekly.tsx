import type { ReactNode } from 'react'
import { Link, useOutletContext } from 'react-router'
import { errorMessage, type Project, type Task } from '../api/client'
import { useProjects, useSpaceTasks } from '../api/queries'
import { PortfolioMark } from '../components/portfolio-mark'
import { Alert, PageHeader, StatusPill, Skeleton } from '../components/ui'
import { matchesAttention } from '../attention'
import {
  addDays,
  formatDay,
  formatMoment,
  isClosedProject,
  PROJECT_STATUS,
  todayIso,
} from '../labels'
import { projectSpan } from '../timeline'
import type { SpaceContext } from './space-layout'

// Au-delà, une situation est jugée ancienne (même seuil que l'alerte « sans nouvelles »).
const STALE_DAYS = 14

/** Lundi de la semaine du jour donné. */
function mondayOf(day: string): string {
  const weekday = (new Date(`${day}T00:00:00Z`).getUTCDay() + 6) % 7
  return addDays(day, -weekday)
}

function sourceText(p: Project): string {
  switch (p.situation_source) {
    case 'manual':
      return 'saisie sur la fiche'
    case 'update':
      return p.situation_source_label
        ? `boîte de mise à jour (« ${p.situation_source_label} »)`
        : 'boîte de mise à jour'
    case 'import':
      return 'import d’une sauvegarde'
    default:
      return 'source non renseignée'
  }
}

function missingInfo(p: Project, today: string): string[] {
  const missing: string[] = []
  if (!p.owner.name) missing.push('responsable du suivi')
  if (!p.next_step) missing.push('prochaine étape')
  if (!projectSpan(p)) missing.push('date')
  if (!p.situation) missing.push('situation')
  else if (
    p.situation_updated_at &&
    p.situation_updated_at.slice(0, 10) < addDays(today, -STALE_DAYS)
  )
    missing.push(`situation à actualiser (plus de ${STALE_DAYS} jours)`)
  return missing
}

function ProjectLine({
  p,
  spaceId,
  children,
}: {
  p: Project
  spaceId: string
  children?: ReactNode
}) {
  const status = PROJECT_STATUS[p.status]
  return (
    <li className="weekly-line">
      <div className="weekly-line__head">
        <PortfolioMark color={p.portfolio.color} emoji={p.portfolio.emoji} />
        <Link className="weekly-line__title" to={`/espaces/${spaceId}/projets/${p.id}`}>
          {p.title}
        </Link>
        <StatusPill tone={status.tone}>{status.label}</StatusPill>
        <span className="weekly-line__owner">
          {p.owner.name ?? <span className="warn-text">Sans responsable</span>}
        </span>
      </div>
      {children}
    </li>
  )
}

function Situation({ p }: { p: Project }) {
  return (
    <p className="weekly-line__detail">
      {p.situation ?? <span className="muted">Situation non renseignée.</span>}
      {p.situation && p.situation_updated_at && (
        <span className="weekly-line__meta">
          {' '}
          — au {formatMoment(p.situation_updated_at)}, {sourceText(p)}
        </span>
      )}
    </p>
  )
}

function Block({
  title,
  help,
  count,
  empty,
  children,
}: {
  title: string
  help: string
  count: number
  empty: string
  children: ReactNode
}) {
  const id = `weekly-${title.replace(/\W+/g, '-').toLowerCase()}`
  return (
    <section className="card-panel weekly-block" aria-labelledby={id}>
      <h2 id={id}>
        {title} <span className="count">{count}</span>
      </h2>
      <p className="card-panel__help">{help}</p>
      {count === 0 ? <p className="muted">{empty}</p> : <ul className="weekly-list">{children}</ul>}
    </section>
  )
}

export function WeeklyPage() {
  const { space } = useOutletContext<SpaceContext>()
  const today = todayIso(space.timezone)
  const monday = mondayOf(today)
  const sunday = addDays(monday, 6)
  const projects = useProjects(space.id)
  const tasks = useSpaceTasks(space.id)
  const loadedAt = projects.dataUpdatedAt ? new Date(projects.dataUpdatedAt).toISOString() : null

  const open = (projects.data ?? []).filter((p) => !isClosedProject(p.status))
  const byId = new Map((projects.data ?? []).map((p) => [p.id, p]))
  const watch = open.filter(
    (p) =>
      matchesAttention(p, 'retard', today) ||
      matchesAttention(p, 'bloques', today) ||
      p.risk_level === 'high',
  )
  const dueProjects = open.filter(
    (p) => p.due_date !== null && p.due_date >= monday && p.due_date <= sunday,
  )
  const dueTasks = (tasks.data ?? []).filter(
    (t: Task) => t.due_date !== null && t.due_date >= monday && t.due_date <= sunday,
  )
  const decisions = open.filter((p) => p.decision_needed)
  const changed = (projects.data ?? [])
    .filter((p) => p.updated_at.slice(0, 10) >= monday)
    .sort((a, b) => b.updated_at.localeCompare(a.updated_at))
  const incomplete = open
    .map((p) => ({ p, missing: missingInfo(p, today) }))
    .filter((x) => x.missing.length > 0)

  return (
    <div className="page-content weekly">
      <PageHeader
        title="Point hebdo"
        subtitle={`Semaine du ${formatDay(monday)} au ${formatDay(sunday)} — pour préparer la réunion de suivi ou le point de direction.`}
        actions={
          <button type="button" className="button" onClick={() => window.print()}>
            Imprimer ou enregistrer en PDF
          </button>
        }
      />
      <p className="weekly__stamp">
        Données à jour au {loadedAt ? formatMoment(loadedAt) : '…'} · photographie du moment : la
        version imprimée ne se met pas à jour.
      </p>
      {projects.isError && <Alert>{errorMessage(projects.error)}</Alert>}
      {projects.isPending ? (
        <Skeleton />
      ) : (
        <div className="weekly__grid">
          <Block
            title="À surveiller"
            help="Projets en retard, bloqués ou en vigilance élevée."
            count={watch.length}
            empty="Rien de bloqué ni en retard. 👍"
          >
            {watch.map((p) => (
              <ProjectLine key={p.id} p={p} spaceId={space.id}>
                <Situation p={p} />
                {p.next_step && (
                  <p className="weekly-line__detail">
                    <strong>Prochaine étape :</strong> {p.next_step}
                  </p>
                )}
              </ProjectLine>
            ))}
          </Block>

          <Block
            title="Décisions attendues"
            help="Ce qui doit être tranché, par qui, et les options possibles."
            count={decisions.length}
            empty="Aucune décision en attente."
          >
            {decisions.map((p) => (
              <ProjectLine key={p.id} p={p} spaceId={space.id}>
                <p className="weekly-line__detail">
                  <strong>{p.decision_needed}</strong>
                  <span className="weekly-line__meta">
                    {' '}
                    — décideur : {p.decision_maker ?? 'non précisé'}
                  </span>
                </p>
                {p.decision_options.length > 0 && (
                  <ol className="decision-list">
                    {p.decision_options.map((o, i) => (
                      <li key={i}>
                        <span className="decision-options__letter" aria-hidden="true">
                          {String.fromCharCode(65 + i)}
                        </span>
                        <span>
                          {o.label}
                          {o.consequence && (
                            <span className="decision-list__consequence"> — {o.consequence}</span>
                          )}
                        </span>
                      </li>
                    ))}
                  </ol>
                )}
              </ProjectLine>
            ))}
          </Block>

          <Block
            title="Échéances de la semaine"
            help="Projets et tâches à rendre entre lundi et dimanche."
            count={dueProjects.length + dueTasks.length}
            empty="Aucune échéance cette semaine."
          >
            {dueProjects.map((p) => (
              <ProjectLine key={p.id} p={p} spaceId={space.id}>
                <p className="weekly-line__detail">
                  Échéance du projet : <strong>{formatDay(p.due_date)}</strong>
                </p>
              </ProjectLine>
            ))}
            {dueTasks.map((t) => {
              const p = t.project_id ? byId.get(t.project_id) : undefined
              return (
                <li key={t.id} className="weekly-line">
                  <div className="weekly-line__head">
                    <span className="weekly-line__title">✓ {t.title}</span>
                    <span className="weekly-line__meta">
                      {p && (
                        <>
                          <Link to={`/espaces/${space.id}/projets/${p.id}`}>{p.title}</Link>
                          {' · '}
                        </>
                      )}
                      {formatDay(t.due_date)}
                      {t.assignee.name && ` · ${t.assignee.name}`}
                    </span>
                  </div>
                </li>
              )
            })}
          </Block>

          <Block
            title="Ce qui a changé cette semaine"
            help="Fiches modifiées depuis lundi, avec la date et la source de leur situation."
            count={changed.length}
            empty="Aucune fiche modifiée depuis lundi."
          >
            {changed.map((p) => (
              <ProjectLine key={p.id} p={p} spaceId={space.id}>
                <Situation p={p} />
              </ProjectLine>
            ))}
          </Block>

          <Block
            title="Informations manquantes"
            help="À compléter avant la réunion : sans elles, le point reste incomplet."
            count={incomplete.length}
            empty="Toutes les fiches ouvertes sont complètes."
          >
            {incomplete.map(({ p, missing }) => (
              <ProjectLine key={p.id} p={p} spaceId={space.id}>
                <p className="weekly-line__detail warn-text">Manque : {missing.join(', ')}</p>
              </ProjectLine>
            ))}
          </Block>
        </div>
      )}
    </div>
  )
}
