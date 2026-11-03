import { Link } from 'react-router'
import type { Project } from '../api/client'
import { colorHex } from '../colors'
import { CERTAINTY, formatDay, isClosedProject, PROJECT_STATUS } from '../labels'
import { StatusPill } from './ui'

function Owner({ project }: { project: Project }) {
  const { owner } = project
  if (!owner.name) return <span className="owner owner--none">Non attribué</span>
  return (
    <span className="owner">
      <span
        className={
          owner.has_account ? 'avatar avatar--small' : 'avatar avatar--small avatar--label'
        }
        aria-hidden="true"
      >
        {owner.name
          .split(/\s+/)
          .slice(0, 2)
          .map((p) => p[0]?.toUpperCase())
          .join('')}
      </span>
      <span className="owner__text">
        <span>{owner.name}</span>
        {!owner.has_account && <span className="owner__note">Sans compte</span>}
      </span>
    </span>
  )
}

function Due({ project, today }: { project: Project; today: string }) {
  if (project.due_date) {
    const late = !isClosedProject(project.status) && project.due_date < today
    return (
      <span className="due">
        <span className={late ? 'due__date due__date--late' : 'due__date'}>
          {formatDay(project.due_date)}
        </span>
        <span className="due__note">
          {late
            ? 'Dépassée'
            : project.date_certainty
              ? CERTAINTY[project.date_certainty]
              : 'Certitude non précisée'}
        </span>
      </span>
    )
  }
  if (project.window_start && project.window_end) {
    return (
      <span className="due">
        <span className="due__date">
          {formatDay(project.window_start)} – {formatDay(project.window_end)}
        </span>
        <span className="due__note">Période · jours à choisir</span>
      </span>
    )
  }
  return <span className="muted">—</span>
}

export function ProjectTable({
  projects,
  spaceId,
  today,
  empty,
}: {
  projects: Project[]
  spaceId: string
  today: string
  empty: React.ReactNode
}) {
  return (
    <div className="table-scroll table-scroll--flush">
      <table className="table table--projects">
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
          {projects.length === 0 && (
            <tr>
              <td colSpan={6}>{empty}</td>
            </tr>
          )}
          {projects.map((project) => {
            const status = PROJECT_STATUS[project.status]
            return (
              <tr key={project.id}>
                <td>
                  <Link className="project-cell" to={`/espaces/${spaceId}/projets/${project.id}`}>
                    <span
                      className="swatch"
                      style={{ background: colorHex(project.portfolio.color) }}
                      aria-hidden="true"
                    />
                    <span className="project-cell__text">
                      <span className="project-cell__title">{project.title}</span>
                      <span className="project-cell__meta">
                        {project.portfolio.name}
                        {project.project_type && ` · ${project.project_type.name}`}
                        {project.late_tasks > 0 && (
                          <span className="project-cell__late">
                            {' '}
                            · {project.late_tasks} tâche(s) en retard
                          </span>
                        )}
                      </span>
                    </span>
                  </Link>
                </td>
                <td>{project.entity?.name ?? <span className="muted">—</span>}</td>
                <td>
                  <Owner project={project} />
                </td>
                <td className="next-step">
                  {project.next_step ?? <span className="muted">À définir</span>}
                </td>
                <td>
                  <Due project={project} today={today} />
                </td>
                <td>
                  <StatusPill tone={status.tone}>{status.label}</StatusPill>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
