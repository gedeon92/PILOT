import { useState } from 'react'
import { useOutletContext } from 'react-router'
import { errorMessage } from '../api/client'
import { useCatalog, useProjects, useSpaceTasks } from '../api/queries'
import { ProjectTimeline } from '../components/timeline'
import { Alert, PageHeader } from '../components/ui'
import { isClosedProject, todayIso } from '../labels'
import type { SpaceContext } from './space-layout'

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
    </div>
  )
}
