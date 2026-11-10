import { useState, type FormEvent } from 'react'
import { errorMessage, type Project, type ProjectTemplate } from '../api/client'
import {
  useCreateTemplate,
  useDeleteTemplate,
  useTemplates,
  useUpdateTemplate,
} from '../api/queries'
import { Alert, Skeleton } from './ui'

/** « Enregistrer comme modèle » (fiche projet, rôle Propriétaire). */
export function SaveTemplateForm({
  spaceId,
  project,
  onDone,
}: {
  spaceId: string
  project: Project
  onDone: () => void
}) {
  const create = useCreateTemplate(spaceId)
  const [name, setName] = useState(project.title)
  const [description, setDescription] = useState('')
  const [saved, setSaved] = useState<ProjectTemplate | null>(null)

  function submit(event: FormEvent) {
    event.preventDefault()
    create.mutate(
      { project_id: project.id, name: name.trim(), description: description.trim() || null },
      { onSuccess: setSaved },
    )
  }

  if (saved) {
    return (
      <div className="template-saved">
        <Alert tone="ok">
          Modèle « {saved.name} » enregistré avec {saved.tasks_count} tâche(s). Choisissez-le dans «
          Partir d’un modèle » à la création d’un projet.
        </Alert>
        <div className="form-actions">
          <button type="button" className="button" onClick={onDone}>
            Fermer
          </button>
        </div>
      </div>
    )
  }

  return (
    <form className="form-grid" onSubmit={submit}>
      <div className="form-grid__full">
        <h2>Enregistrer comme modèle</h2>
        <p className="card-panel__help">
          Les tâches de ce projet (avec leurs sous-tâches, responsables, répétitions et dépendances)
          pourront être reprises dans un nouveau projet. Les échéances sont gardées en jours avant
          ou après la date de début, puis recalculées. Les tâches annulées, les commentaires et les
          fichiers ne sont pas repris.
        </p>
      </div>
      <div className="field form-grid__full">
        <label htmlFor="template-name">Nom du modèle *</label>
        <input
          id="template-name"
          required
          maxLength={120}
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
      </div>
      <div className="field form-grid__full">
        <label htmlFor="template-description">Description</label>
        <input
          id="template-description"
          maxLength={500}
          placeholder="Ex. : préparation type d’un salon, de J-60 à J+7"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
      </div>
      {create.isError && (
        <div className="form-grid__full">
          <Alert>{errorMessage(create.error)}</Alert>
        </div>
      )}
      <div className="form-grid__full form-actions">
        <button className="button button--primary" type="submit" disabled={create.isPending}>
          {create.isPending ? 'Enregistrement…' : 'Enregistrer le modèle'}
        </button>
        <button className="button button--ghost" type="button" onClick={onDone}>
          Annuler
        </button>
      </div>
    </form>
  )
}

function offsetLabel(days: number | null | undefined) {
  if (days === null || days === undefined) return 'sans échéance'
  if (days === 0) return 'le jour du début'
  return days < 0 ? `${-days} j avant le début` : `${days} j après le début`
}

function TemplateRow({
  spaceId,
  template,
  canManage,
}: {
  spaceId: string
  template: ProjectTemplate
  canManage: boolean
}) {
  const update = useUpdateTemplate(spaceId)
  const remove = useDeleteTemplate(spaceId)
  const [editing, setEditing] = useState(false)
  const [name, setName] = useState(template.name)
  const [confirming, setConfirming] = useState(false)
  const [open, setOpen] = useState(false)

  if (editing) {
    return (
      <li className="item-row item-row--editing">
        <form
          className="inline-form"
          onSubmit={(e) => {
            e.preventDefault()
            update.mutate(
              { id: template.id, version: template.version, name: name.trim() },
              { onSuccess: () => setEditing(false) },
            )
          }}
        >
          <label className="visually-hidden" htmlFor={`template-${template.id}`}>
            Nom du modèle
          </label>
          <input
            id={`template-${template.id}`}
            required
            maxLength={120}
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <button className="button button--small button--primary" disabled={update.isPending}>
            Enregistrer
          </button>
          <button type="button" className="button button--small" onClick={() => setEditing(false)}>
            Annuler
          </button>
        </form>
        {update.isError && <Alert>{errorMessage(update.error)}</Alert>}
      </li>
    )
  }

  return (
    <li className="item-row template-row">
      <span className="item-row__text">
        <span className="item-row__name">{template.name}</span>
        <span className="item-row__details">
          {template.tasks_count} tâche(s)
          {template.description && ` · ${template.description}`} ·{' '}
          <button
            type="button"
            className="link-button"
            aria-expanded={open}
            onClick={() => setOpen((v) => !v)}
          >
            {open ? 'Masquer les tâches' : 'Voir les tâches'}
          </button>
        </span>
        {open && (
          <ul className="template-row__tasks">
            {template.tasks.map((t, i) => (
              <li key={i} className={t.is_subtask ? 'template-row__sub' : undefined}>
                {t.title} <span className="muted">· {offsetLabel(t.offset_days)}</span>
              </li>
            ))}
          </ul>
        )}
      </span>
      {canManage && (
        <span className="item-row__actions">
          <button type="button" className="button button--small" onClick={() => setEditing(true)}>
            Renommer
          </button>
          {confirming ? (
            <>
              <button
                type="button"
                className="button button--small button--danger"
                disabled={remove.isPending}
                onClick={() => remove.mutate(template.id)}
              >
                Confirmer la suppression
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
              Supprimer
            </button>
          )}
        </span>
      )}
      {remove.isError && <Alert>{errorMessage(remove.error)}</Alert>}
    </li>
  )
}

/** Paramètres : liste des modèles de projet. */
export function TemplatesSection({ spaceId, canManage }: { spaceId: string; canManage: boolean }) {
  const templates = useTemplates(spaceId)
  return (
    <section className="card-panel" aria-labelledby="title-templates">
      <div className="card-panel__head">
        <div>
          <h2 id="title-templates">Modèles de projet</h2>
          <p className="card-panel__help">
            Des listes de tâches prêtes à l’emploi. Pour en créer un, ouvrez un projet et cliquez
            sur « Enregistrer comme modèle ». Supprimer un modèle ne touche pas aux projets créés
            avec lui.
          </p>
        </div>
      </div>
      {templates.isPending && <Skeleton />}
      {templates.isError && <Alert>{errorMessage(templates.error)}</Alert>}
      {templates.data?.length === 0 && <p className="muted">Aucun modèle pour l’instant.</p>}
      {templates.data && templates.data.length > 0 && (
        <ul className="item-list">
          {templates.data.map((t) => (
            <TemplateRow key={t.id} spaceId={spaceId} template={t} canManage={canManage} />
          ))}
        </ul>
      )}
    </section>
  )
}
