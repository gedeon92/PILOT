import { useState, type FormEvent } from 'react'
import { Link } from 'react-router'
import { errorMessage } from '../api/client'
import {
  useAddProjectLink,
  useProjectLinks,
  useProjects,
  useRemoveProjectLink,
} from '../api/queries'
import { PROJECT_STATUS } from '../labels'
import { PortfolioMark } from './portfolio-mark'
import { Alert, StatusPill } from './ui'

/** Projets liés (CDC §5) : relier deux projets sans dupliquer l'un dans l'autre.
 * Le lien est visible depuis les deux fiches et inscrit dans leurs historiques. */
export function ProjectLinksSection({
  spaceId,
  projectId,
  canWrite,
}: {
  spaceId: string
  projectId: string
  canWrite: boolean
}) {
  const links = useProjectLinks(spaceId, projectId)
  const add = useAddProjectLink(spaceId, projectId)
  const remove = useRemoveProjectLink(spaceId, projectId)
  const [adding, setAdding] = useState(false)
  const projects = useProjects(spaceId)
  const [target, setTarget] = useState('')
  const [note, setNote] = useState('')
  const linked = new Set((links.data ?? []).map((l) => l.project.id))
  const candidates = (projects.data ?? []).filter((p) => p.id !== projectId && !linked.has(p.id))

  function submit(event: FormEvent) {
    event.preventDefault()
    add.mutate(
      { project_id: target, note: note.trim() || null },
      {
        onSuccess: () => {
          setTarget('')
          setNote('')
          setAdding(false)
        },
      },
    )
  }

  return (
    <section className="card-panel" aria-labelledby="links-title">
      <div className="card-panel__head">
        <h2 id="links-title">
          Projets liés <span className="count">{links.data?.length ?? 0}</span>
        </h2>
        {canWrite && !adding && (
          <button type="button" className="button button--small" onClick={() => setAdding(true)}>
            Lier un projet
          </button>
        )}
      </div>
      {adding && (
        <form className="links-form" onSubmit={submit} aria-label="Lier un projet">
          <div className="field">
            <label htmlFor="link-project">Projet</label>
            <select
              id="link-project"
              required
              value={target}
              onChange={(e) => setTarget(e.target.value)}
            >
              <option value="">Choisir…</option>
              {candidates.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.title}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="link-note">Pourquoi ce lien ? (facultatif)</label>
            <input
              id="link-note"
              maxLength={200}
              placeholder="Ex. : même audience, dépend de sa livraison"
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
          </div>
          {add.isError && <Alert>{errorMessage(add.error)}</Alert>}
          <div className="form-actions">
            <button
              className="button button--primary button--small"
              type="submit"
              disabled={!target || add.isPending}
            >
              Lier
            </button>
            <button
              className="button button--ghost button--small"
              type="button"
              onClick={() => setAdding(false)}
            >
              Annuler
            </button>
          </div>
        </form>
      )}
      {links.isError && <Alert>{errorMessage(links.error)}</Alert>}
      {links.data?.length === 0 && !adding && (
        <p className="muted">Aucun projet lié. Un lien relie deux projets sans les dupliquer.</p>
      )}
      {links.data && links.data.length > 0 && (
        <ul className="links-list">
          {links.data.map((link) => {
            const status = PROJECT_STATUS[link.project.status]
            return (
              <li key={link.id}>
                <PortfolioMark
                  color={link.project.portfolio.color}
                  emoji={link.project.portfolio.emoji}
                />
                <span className="links-list__text">
                  <Link to={`/espaces/${spaceId}/projets/${link.project.id}`}>
                    {link.project.title}
                  </Link>
                  {link.note && <span className="links-list__note">{link.note}</span>}
                </span>
                <StatusPill tone={status.tone}>{status.label}</StatusPill>
                {canWrite && (
                  <button
                    type="button"
                    className="button button--small button--ghost"
                    aria-label={`Retirer le lien avec ${link.project.title}`}
                    disabled={remove.isPending}
                    onClick={() => remove.mutate(link.project.id)}
                  >
                    ×
                  </button>
                )}
              </li>
            )
          })}
        </ul>
      )}
      {remove.isError && <Alert>{errorMessage(remove.error)}</Alert>}
    </section>
  )
}
