import { useState } from 'react'
import { Link, useOutletContext } from 'react-router'
import { errorMessage, canWriteSpace } from '../api/client'
import { downloadUrl, useProjects, useSpaceDocuments } from '../api/queries'
import { FileBadge, UPLOAD_HELP, UploadStatus, useUploader } from '../components/documents'
import { DocumentIcon } from '../components/icons'
import { Alert, PageHeader } from '../components/ui'
import { formatSize } from '../files'
import { formatMoment } from '../labels'
import type { SpaceContext } from './space-layout'

// Les documents arrivent par pages de 50 ; au-delà de 450, affinez la recherche.
const PAGE = 50
const MAX = 450

/** Ajout direct depuis la page Documents : on choisit le projet, puis les fichiers. */
function AddDocuments({ spaceId, spaceWriter }: { spaceId: string; spaceWriter: boolean }) {
  const projects = useProjects(spaceId)
  const [chosen, setChosen] = useState('')
  // Seulement les projets où l'on peut ajouter une pièce : le rôle sur le projet compte (lot C).
  const list = (projects.data ?? []).filter((p) =>
    p.my_role ? p.my_role !== 'reader' : spaceWriter,
  )
  const projectId = chosen || list[0]?.id || ''
  const { input, uploads, busy, send } = useUploader(spaceId, projectId)

  if (projects.isSuccess && list.length === 0 && !spaceWriter) return null
  return (
    <section className="card-panel add-docs" aria-labelledby="add-docs-title">
      <h2 id="add-docs-title">Ajouter des documents</h2>
      {projects.isSuccess && list.length === 0 ? (
        <p className="muted">
          Créez d’abord un projet : chaque document est rangé dans un projet.{' '}
          <Link to={`/espaces/${spaceId}/projets`}>Aller aux projets</Link>
        </p>
      ) : (
        <>
          <div className="add-docs__row">
            <label className="field add-docs__project">
              <span className="field__label">Projet</span>
              <select value={projectId} onChange={(e) => setChosen(e.target.value)}>
                {list.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.title}
                  </option>
                ))}
              </select>
            </label>
            <input
              ref={input}
              type="file"
              multiple
              className="visually-hidden"
              id="upload-space-documents"
              onChange={(e) => send(e.target.files)}
            />
            <label
              htmlFor="upload-space-documents"
              className={
                busy || !projectId ? 'button button--primary is-disabled' : 'button button--primary'
              }
            >
              {busy ? 'Envoi…' : 'Choisir les fichiers'}
            </label>
          </div>
          <p className="card-panel__help">{UPLOAD_HELP}</p>
          <UploadStatus uploads={uploads} />
        </>
      )}
    </section>
  )
}

export function DocumentsPage() {
  const { space } = useOutletContext<SpaceContext>()
  const [q, setQ] = useState('')
  const [limit, setLimit] = useState(PAGE)
  const documents = useSpaceDocuments(space.id, q, limit)
  const items = documents.data?.items
  const spaceWriter = canWriteSpace(space.role)

  return (
    <div className="page-content">
      <PageHeader
        title="Documents"
        subtitle="Toutes les pièces des projets de l’espace : PDF, Word, Excel, images…"
      />
      <AddDocuments spaceId={space.id} spaceWriter={spaceWriter} />
      <div className="filters" role="search">
        <label className="filters__search">
          <span className="visually-hidden">Rechercher un document</span>
          <input
            type="search"
            placeholder="Rechercher par nom de fichier…"
            value={q}
            onChange={(e) => {
              setQ(e.target.value)
              setLimit(PAGE)
            }}
          />
        </label>
      </div>
      {documents.isError && <Alert>{errorMessage(documents.error)}</Alert>}
      <section className="card-panel card-panel--flush" aria-label="Liste des documents">
        <div className="table-scroll table-scroll--flush">
          <table className="table">
            <thead>
              <tr>
                <th scope="col">Document</th>
                <th scope="col">Projet</th>
                <th scope="col">Ajouté</th>
                <th scope="col">
                  <span className="visually-hidden">Télécharger</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {items?.length === 0 && (
                <tr>
                  <td colSpan={4}>
                    <div className="table-empty">
                      <span className="icon-tile icon-tile--info">
                        <DocumentIcon />
                      </span>
                      <span>
                        {q ? 'Aucun document ne correspond.' : 'Aucun document pour l’instant.'}
                      </span>
                    </div>
                  </td>
                </tr>
              )}
              {items?.map((d) => (
                <tr key={d.id}>
                  <td>
                    <span className="doc-cell">
                      <FileBadge filename={d.filename} />
                      <span className="doc-row__text">
                        <span className="doc-row__name">{d.filename}</span>
                        <span className="doc-row__meta">{formatSize(d.size_bytes)}</span>
                      </span>
                    </span>
                  </td>
                  <td>
                    <Link
                      className="project-cell__title"
                      to={`/espaces/${space.id}/projets/${d.project_id}`}
                    >
                      {d.project_title}
                    </Link>
                  </td>
                  <td>
                    <span className="due">
                      <span>{formatMoment(d.created_at)}</span>
                      {d.uploaded_by && <span className="due__note">{d.uploaded_by}</span>}
                    </span>
                  </td>
                  <td className="actions">
                    <a className="button button--small" href={downloadUrl(space.id, d.id)} download>
                      Télécharger
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      {documents.data?.more && (
        <div className="list-more">
          <span className="muted">{items?.length} documents affichés</span>
          <button
            type="button"
            className="button"
            disabled={documents.isFetching}
            onClick={() => setLimit((n) => Math.min(n + PAGE, MAX))}
          >
            {documents.isFetching ? 'Chargement…' : 'Afficher plus'}
          </button>
        </div>
      )}
    </div>
  )
}
