import { useRef } from 'react'
import { Link } from 'react-router'
import { errorMessage } from '../api/client'
import { exportUrl, useImportSpace } from '../api/queries'
import { Alert } from './ui'

const COUNT_LABELS: Record<string, string> = {
  projects: 'projet(s)',
  tasks: 'tâche(s)',
  documents: 'pièce(s) vérifiée(s)',
  portfolios: 'portefeuille(s)',
  entities: 'filiale(s)',
  programs: 'programme(s)',
  project_types: 'type(s) ajouté(s)',
}

/** Export complet de l'espace (propriétaire) et import d'un export dans un nouvel espace. */
export function BackupSection({ spaceId, canExport }: { spaceId: string; canExport: boolean }) {
  const importSpace = useImportSpace()
  const input = useRef<HTMLInputElement>(null)
  const result = importSpace.data

  return (
    <section className="card-panel" aria-labelledby="backup-title">
      <div className="card-panel__head">
        <div>
          <h2 id="backup-title">Sauvegarde et export</h2>
          <p className="card-panel__help">
            L’export est une photographie de l’espace à un instant donné : structure, projets,
            tâches, événements et pièces, chacune vérifiable par son empreinte. Gardez-le en lieu
            sûr. Mots de passe et demandes de mise à jour privées n’y figurent jamais.
          </p>
        </div>
      </div>

      {canExport && (
        <div className="backup__actions">
          <a className="button button--primary" href={exportUrl(spaceId, true)} download>
            Télécharger l’export complet
          </a>
          <a className="button" href={exportUrl(spaceId, false)} download>
            Données seules (sans les fichiers)
          </a>
        </div>
      )}

      <div className="backup__import">
        <div>
          <strong>Importer un export</strong>
          <p className="field__hint">
            Crée toujours un <strong>nouvel espace</strong> dont vous êtes propriétaire : aucun
            espace existant n’est modifié. Idéal pour vérifier une sauvegarde.
          </p>
          <p className="field__hint">
            Seul le fichier <strong>ZIP téléchargé depuis PILOT</strong> est accepté ici. Pour un
            PDF ou un Word : <strong>Documents</strong> (pour le ranger dans un projet) ou{' '}
            <strong>Mises à jour</strong> (pour que PILOT le lise).
          </p>
        </div>
        <input
          ref={input}
          id="import-file"
          className="visually-hidden"
          type="file"
          accept=".zip,.json"
          onChange={(e) => {
            const file = e.target.files?.[0]
            if (file) importSpace.mutate(file)
            e.target.value = ''
          }}
        />
        <label
          htmlFor="import-file"
          className="button"
          aria-disabled={importSpace.isPending}
          onClick={(e) => importSpace.isPending && e.preventDefault()}
        >
          {importSpace.isPending ? 'Import en cours…' : 'Choisir un fichier d’export'}
        </label>
      </div>

      {importSpace.isError && <Alert>{errorMessage(importSpace.error)}</Alert>}
      {result && (
        <Alert tone={result.warnings.length ? 'warn' : 'ok'}>
          {result.already_imported ? (
            <>Cet export a déjà été importé : aucun doublon n’a été créé. </>
          ) : (
            <>
              Espace « {result.space_name} » créé :{' '}
              {Object.entries(result.counts)
                .filter(([key, n]) => n > 0 && COUNT_LABELS[key])
                .map(([key, n]) => `${n} ${COUNT_LABELS[key]}`)
                .join(', ') || 'aucun élément'}
              .{' '}
            </>
          )}
          <Link to={`/espaces/${result.space_id}`}>Ouvrir l’espace importé</Link>
          {result.warnings.length > 0 && (
            <ul className="backup__warnings">
              {result.warnings.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          )}
        </Alert>
      )}
    </section>
  )
}
