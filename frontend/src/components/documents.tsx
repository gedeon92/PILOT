import { useRef, useState } from 'react'
import { errorMessage, type DocumentItem } from '../api/client'
import {
  downloadUrl,
  useArchiveDocument,
  useProjectDocuments,
  useUploadDocument,
} from '../api/queries'
import { extensionOf, formatSize, MAX_FILES_PER_UPLOAD, MAX_UPLOAD_BYTES } from '../files'
import { formatMoment } from '../labels'
import { Alert } from './ui'

type UploadState = { name: string; status: 'pending' | 'done' | 'error'; message?: string }

export function FileBadge({ filename }: { filename: string }) {
  return (
    <span className="file-badge" aria-hidden="true">
      {extensionOf(filename)}
    </span>
  )
}

function DocumentRow({
  document,
  spaceId,
  canWrite,
}: {
  document: DocumentItem
  spaceId: string
  canWrite: boolean
}) {
  const archive = useArchiveDocument(spaceId)
  const [confirming, setConfirming] = useState(false)
  return (
    <li className="doc-row">
      <FileBadge filename={document.filename} />
      <span className="doc-row__text">
        <span className="doc-row__name">{document.filename}</span>
        <span className="doc-row__meta">
          {formatSize(document.size_bytes)} · ajouté le {formatMoment(document.created_at)}
          {document.uploaded_by && ` par ${document.uploaded_by}`}
        </span>
      </span>
      <a className="button button--small" href={downloadUrl(spaceId, document.id)} download>
        Télécharger
      </a>
      {canWrite &&
        (confirming ? (
          <>
            <button
              type="button"
              className="button button--small button--danger"
              disabled={archive.isPending}
              onClick={() => archive.mutate(document.id)}
            >
              Confirmer le retrait
            </button>
            <button
              type="button"
              className="button button--small"
              onClick={() => setConfirming(false)}
            >
              Garder
            </button>
          </>
        ) : (
          <button
            type="button"
            className="button button--small"
            onClick={() => setConfirming(true)}
          >
            Retirer
          </button>
        ))}
      {archive.isError && <Alert>{errorMessage(archive.error)}</Alert>}
    </li>
  )
}

export function DocumentsSection({
  spaceId,
  projectId,
  canWrite,
}: {
  spaceId: string
  projectId: string
  canWrite: boolean
}) {
  const documents = useProjectDocuments(spaceId, projectId)
  const upload = useUploadDocument(spaceId, projectId)
  const input = useRef<HTMLInputElement>(null)
  const [uploads, setUploads] = useState<UploadState[]>([])
  const busy = uploads.some((u) => u.status === 'pending')

  async function send(files: FileList | null) {
    if (!files || files.length === 0) return
    const selected = Array.from(files).slice(0, MAX_FILES_PER_UPLOAD)
    const states: UploadState[] = selected.map((f) => ({ name: f.name, status: 'pending' }))
    if (files.length > MAX_FILES_PER_UPLOAD) {
      states.push({
        name: `${files.length - MAX_FILES_PER_UPLOAD} autre(s) fichier(s)`,
        status: 'error',
        message: `${MAX_FILES_PER_UPLOAD} fichiers au maximum par envoi.`,
      })
    }
    setUploads(states)
    // Un fichier à la fois : chaque résultat est affiché, un échec n'empêche pas les autres.
    for (const [i, file] of selected.entries()) {
      let result: UploadState
      if (file.size > MAX_UPLOAD_BYTES) {
        result = {
          name: file.name,
          status: 'error',
          message: `Trop volumineux (${formatSize(file.size)}, 4 Mo au maximum).`,
        }
      } else {
        try {
          await upload.mutateAsync(file)
          result = { name: file.name, status: 'done' }
        } catch (error) {
          result = { name: file.name, status: 'error', message: errorMessage(error) }
        }
      }
      setUploads((current) => current.map((u, j) => (j === i ? result : u)))
    }
    if (input.current) input.current.value = ''
  }

  return (
    <section className="card-panel" aria-labelledby="documents-title">
      <div className="card-panel__head">
        <h2 id="documents-title">
          Documents du projet <span className="count">{documents.data?.length ?? 0}</span>
        </h2>
        {canWrite && (
          <>
            <input
              ref={input}
              type="file"
              multiple
              className="visually-hidden"
              id={`upload-${projectId}`}
              onChange={(e) => send(e.target.files)}
            />
            <label
              htmlFor={`upload-${projectId}`}
              className={busy ? 'button button--small is-disabled' : 'button button--small'}
            >
              Ajouter des documents
            </label>
          </>
        )}
      </div>
      {canWrite && (
        <p className="card-panel__help">
          {MAX_FILES_PER_UPLOAD} fichiers à la fois, 4 Mo chacun au maximum (phase de test). Tous
          les formats sont acceptés ; ils sont toujours proposés en téléchargement.
        </p>
      )}
      {uploads.length > 0 && (
        <ul className="upload-status" aria-live="polite">
          {uploads.map((u, i) => (
            <li key={i} className={`upload-status__item upload-status__item--${u.status}`}>
              <span>{u.name}</span>
              <span>
                {u.status === 'pending'
                  ? 'Envoi…'
                  : u.status === 'done'
                    ? 'Enregistré'
                    : `Non enregistré : ${u.message}`}
              </span>
            </li>
          ))}
        </ul>
      )}
      {documents.isPending && <p className="muted">Chargement…</p>}
      {documents.isError && <Alert>{errorMessage(documents.error)}</Alert>}
      {documents.data?.length === 0 && <p className="muted">Aucun document pour l’instant.</p>}
      {documents.data && documents.data.length > 0 && (
        <ul className="doc-list">
          {documents.data.map((d) => (
            <DocumentRow key={d.id} document={d} spaceId={spaceId} canWrite={canWrite} />
          ))}
        </ul>
      )}
    </section>
  )
}
