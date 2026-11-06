import { useEffect, useState } from 'react'
import { Link, useLocation, useOutletContext } from 'react-router'
import { errorMessage, type Project } from '../api/client'
import { useCatalog, useProjects, useSpaceTasks } from '../api/queries'
import { ProjectTimeline } from '../components/timeline'
import { Alert, PageHeader, StatusPill } from '../components/ui'
import { isClosedProject, PROJECT_STATUS, todayIso } from '../labels'
import { projectSpan } from '../timeline'
import type { SpaceContext } from './space-layout'

/** Projets sans aucune date : ils ne peuvent pas figurer sur la timeline, on les liste à part. */
function UndatedProjects({ projects, spaceId }: { projects: Project[]; spaceId: string }) {
  const undated = projects
    .filter((p) => p.status !== 'cancelled' && !projectSpan(p))
    .sort((a, b) => a.title.localeCompare(b.title, 'fr'))
  return (
    <section
      className="card-panel card-panel--flush undated"
      id="sans-date"
      aria-labelledby="undated-title"
    >
      <div className="undated__head">
        <h2 id="undated-title">
          Projets sans date <span className="count">{undated.length}</span>
        </h2>
        <p className="muted">
          Ni début, ni fin, ni échéance, ni période connue : ils n’apparaissent pas sur la timeline.
          Ouvrez la fiche pour ajouter une date, même approximative (une période suffit).
        </p>
      </div>
      {undated.length === 0 ? (
        <p className="undated__empty">Tous les projets affichés ont au moins une date. 👍</p>
      ) : (
        <div className="table-scroll table-scroll--flush">
          <table className="table">
            <thead>
              <tr>
                <th scope="col">Projet</th>
                <th scope="col">Portefeuille</th>
                <th scope="col">Statut</th>
                <th scope="col">Responsable</th>
              </tr>
            </thead>
            <tbody>
              {undated.map((p) => (
                <tr key={p.id}>
                  <td>
                    <Link
                      className="project-cell__title"
                      to={`/espaces/${spaceId}/projets/${p.id}`}
                    >
                      {p.title}
                    </Link>
                  </td>
                  <td>{p.portfolio.name}</td>
                  <td>
                    <StatusPill tone={PROJECT_STATUS[p.status].tone}>
                      {PROJECT_STATUS[p.status].label}
                    </StatusPill>
                  </td>
                  <td>{p.owner.name ?? <span className="muted">Non désigné</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

export function TimelinePage() {
  const { space } = useOutletContext<SpaceContext>()
  const [portfolio, setPortfolio] = useState('')
  const [entity, setEntity] = useState('')
  const [kind, setKind] = useState('')
  const [withDone, setWithDone] = useState(false)
  const portfolios = useCatalog(space.id, 'portfolios')
  const entities = useCatalog(space.id, 'entities')
  const projects = useProjects(space.id, { portfolio_id: portfolio, kind })
  const tasks = useSpaceTasks(space.id)
  const visible = (projects.data ?? []).filter(
    (p) => (!entity || p.entity?.id === entity) && (withDone || !isClosedProject(p.status)),
  )
  const { hash } = useLocation()
  const loaded = projects.isSuccess
  useEffect(() => {
    if (loaded && hash === '#sans-date')
      document.getElementById('sans-date')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [loaded, hash])

  return (
    <div className="page-content">
      <PageHeader
        title="Timeline"
        subtitle="Tous les projets dans le temps : survolez une barre pour voir le détail, cliquez pour ouvrir la fiche."
      />
      <div className="filters">
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
        <select aria-label="Nature" value={kind} onChange={(e) => setKind(e.target.value)}>
          <option value="">Projets et événements</option>
          <option value="standard">Projets seulement</option>
          <option value="event">Événements seulement</option>
        </select>
        <label className="checkbox">
          <input
            type="checkbox"
            checked={withDone}
            onChange={(e) => setWithDone(e.target.checked)}
          />
          Inclure les projets terminés
        </label>
      </div>
      {projects.isError && <Alert>{errorMessage(projects.error)}</Alert>}
      <section className="card-panel" aria-label="Timeline des projets">
        {projects.isPending ? (
          <p className="muted">Chargement…</p>
        ) : (
          <ProjectTimeline
            projects={visible}
            tasks={tasks.data ?? []}
            today={todayIso(space.timezone)}
            spaceId={space.id}
          />
        )}
        <p className="card-panel__foot">
          Le calendrier montre les dates prévues. Il ne mesure pas l’avancement. Les projets annulés
          n’y figurent pas.
        </p>
      </section>
      {projects.isSuccess && <UndatedProjects projects={visible} spaceId={space.id} />}
    </div>
  )
}
