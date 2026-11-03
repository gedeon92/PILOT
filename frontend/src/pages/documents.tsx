import { useState } from 'react'
import { Link, useOutletContext } from 'react-router'
import { errorMessage } from '../api/client'
import { downloadUrl, useSpaceDocuments } from '../api/queries'
import { FileBadge } from '../components/documents'
import { DocumentIcon } from '../components/icons'
import { Alert, PageHeader } from '../components/ui'
import { formatSize } from '../files'
import { formatMoment } from '../labels'
import type { SpaceContext } from './space-layout'

export function DocumentsPage() {
  const { space } = useOutletContext<SpaceContext>()
  const [q, setQ] = useState('')
  const documents = useSpaceDocuments(space.id, q)

  return (
    <div className="page-content">
      <PageHeader
        title="Documents"
        subtitle="Toutes les pièces des projets de l’espace. Pour en ajouter, ouvrez la fiche du projet."
      />
      <div className="filters" role="search">
        <label className="filters__search">
          <span className="visually-hidden">Rechercher un document</span>
          <input
            type="search"
            placeholder="Rechercher par nom de fichier…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
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
              {documents.data?.length === 0 && (
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
              {documents.data?.map((d) => (
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
    </div>
  )
}
