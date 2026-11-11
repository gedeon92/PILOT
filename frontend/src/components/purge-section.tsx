import { useState } from 'react'
import { errorMessage } from '../api/client'
import { exportUrl, useProjects, usePurgeProjects } from '../api/queries'
import { PROJECT_STATUS } from '../labels'
import { Alert, Skeleton } from './ui'

const WORD = 'SUPPRIMER'

/** Zone sensible (propriétaire) : suppression définitive de projets, par exemple des projets
 * d'essai. Seule exception à « rien ne se supprime » : sauvegarde conseillée, et le mot
 * SUPPRIMER à taper pour confirmer. */
export function PurgeSection({ spaceId }: { spaceId: string }) {
  const projects = useProjects(spaceId)
  const purge = usePurgeProjects(spaceId)
  const [open, setOpen] = useState(false)
  const [selected, setSelected] = useState<string[]>([])
  const [word, setWord] = useState('')
  const all = projects.data ?? []
  const allSelected = all.length > 0 && selected.length === all.length

  function toggle(id: string, on: boolean) {
    setSelected((s) => (on ? [...s, id] : s.filter((x) => x !== id)))
  }

  return (
    <section className="card-panel purge" aria-labelledby="title-purge">
      <div className="card-panel__head">
        <div>
          <h2 id="title-purge">Zone sensible</h2>
          <p className="card-panel__help">
            Supprimer définitivement des projets, par exemple vos projets d’essai, avec tout ce
            qu’ils contiennent : tâches, sections, jalons, décisions, documents et historique.{' '}
            <strong>Cette action ne peut pas être annulée.</strong> Pour simplement arrêter un
            projet, préférez « Changer le statut → Annulé ».
          </p>
        </div>
      </div>
      {!open ? (
        <button type="button" className="button button--danger" onClick={() => setOpen(true)}>
          Supprimer définitivement des projets…
        </button>
      ) : (
        <div className="purge__body">
          <ol className="purge__steps">
            <li>
              Par prudence, téléchargez d’abord une sauvegarde :{' '}
              <a className="button button--small" href={exportUrl(spaceId, true)} download>
                Télécharger l’export complet
              </a>
            </li>
            <li>Cochez les projets à supprimer.</li>
            <li>Tapez {WORD} pour confirmer.</li>
          </ol>
          {projects.isPending && <Skeleton lines={2} />}
          {projects.isError && <Alert>{errorMessage(projects.error)}</Alert>}
          {all.length === 0 && projects.isSuccess && (
            <p className="muted">Aucun projet dans cet espace.</p>
          )}
          {all.length > 0 && (
            <fieldset className="milestone-picker purge__list">
              <legend>Projets ({all.length})</legend>
              <label className="milestone-picker__item purge__all">
                <input
                  type="checkbox"
                  checked={allSelected}
                  onChange={(e) => setSelected(e.target.checked ? all.map((p) => p.id) : [])}
                />
                <strong>Tout sélectionner</strong>
              </label>
              {all.map((p) => (
                <label key={p.id} className="milestone-picker__item">
                  <input
                    type="checkbox"
                    checked={selected.includes(p.id)}
                    onChange={(e) => toggle(p.id, e.target.checked)}
                  />
                  <span>
                    {p.title} <span className="muted">· {PROJECT_STATUS[p.status].label}</span>
                  </span>
                </label>
              ))}
            </fieldset>
          )}
          <div className="field purge__confirm">
            <label htmlFor="purge-word">Pour confirmer, tapez {WORD}</label>
            <input
              id="purge-word"
              autoComplete="off"
              value={word}
              onChange={(e) => setWord(e.target.value)}
            />
          </div>
          {purge.isError && <Alert>{errorMessage(purge.error)}</Alert>}
          {purge.isSuccess && (
            <Alert tone="ok">
              {purge.data.deleted} projet(s) supprimé(s) définitivement :{' '}
              {purge.data.titles.join(', ')}.
            </Alert>
          )}
          <div className="form-actions">
            <button
              type="button"
              className="button button--danger"
              disabled={selected.length === 0 || word.trim() !== WORD || purge.isPending}
              onClick={() =>
                purge.mutate(selected, {
                  onSuccess: () => {
                    setSelected([])
                    setWord('')
                  },
                })
              }
            >
              {purge.isPending
                ? 'Suppression…'
                : `Supprimer définitivement ${selected.length} projet(s)`}
            </button>
            <button
              type="button"
              className="button button--ghost"
              onClick={() => {
                setOpen(false)
                setSelected([])
                setWord('')
              }}
            >
              Fermer
            </button>
          </div>
        </div>
      )}
    </section>
  )
}
