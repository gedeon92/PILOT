import { useState, type FormEvent } from 'react'
import { Link, useNavigate, useOutletContext } from 'react-router'
import { errorMessage } from '../api/client'
import { useCatalog, useCreateProject, useMembers, useProjects } from '../api/queries'
import { FolderIcon, PlusIcon } from '../components/icons'
import { PersonField, type PersonValue } from '../components/person-field'
import { ProjectTable } from '../components/project-table'
import { Alert, PageHeader } from '../components/ui'
import {
  CERTAINTY,
  OPEN_PROJECT_STATUSES,
  PROJECT_STATUS,
  todayIso,
  type ProjectStatus,
} from '../labels'
import { personPayload } from '../person'
import type { SpaceContext } from './space-layout'

export function ProjectsPage() {
  const { space } = useOutletContext<SpaceContext>()
  const [q, setQ] = useState('')
  const [portfolio, setPortfolio] = useState('')
  const [status, setStatus] = useState('')
  const portfolios = useCatalog(space.id, 'portfolios')
  const projects = useProjects(space.id, { q, portfolio_id: portfolio, status })
  const canWrite = space.role !== 'reader'
  const filtered = Boolean(q || portfolio || status)

  return (
    <div className="page-content">
      <PageHeader
        title="Projets"
        subtitle="Tous les projets de l’espace, avec leur responsable et leur prochaine étape."
        actions={
          canWrite && (
            <Link className="button button--primary" to={`/espaces/${space.id}/projets/nouveau`}>
              Nouveau projet <PlusIcon />
            </Link>
          )
        }
      />

      <div className="filters" role="search">
        <label className="filters__search">
          <span className="visually-hidden">Rechercher un projet</span>
          <input
            type="search"
            placeholder="Rechercher un projet…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </label>
        <label>
          <span className="visually-hidden">Portefeuille</span>
          <select value={portfolio} onChange={(e) => setPortfolio(e.target.value)}>
            <option value="">Tous les portefeuilles</option>
            {portfolios.data?.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span className="visually-hidden">Statut</span>
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">Tous les statuts</option>
            {(Object.keys(PROJECT_STATUS) as ProjectStatus[]).map((s) => (
              <option key={s} value={s}>
                {PROJECT_STATUS[s].label}
              </option>
            ))}
          </select>
        </label>
      </div>

      <section className="card-panel card-panel--flush" aria-label="Liste des projets">
        {projects.isError && <Alert>{errorMessage(projects.error)}</Alert>}
        {projects.isPending ? (
          <p className="muted table-loading">Chargement…</p>
        ) : (
          <ProjectTable
            projects={projects.data ?? []}
            spaceId={space.id}
            today={todayIso(space.timezone)}
            empty={
              <div className="table-empty">
                <span className="icon-tile icon-tile--action">
                  <FolderIcon />
                </span>
                <span>
                  {filtered ? (
                    'Aucun projet ne correspond à ces filtres.'
                  ) : (
                    <>
                      <strong>Aucun projet pour l’instant.</strong>{' '}
                      {canWrite && 'Créez le premier avec « Nouveau projet ».'}
                    </>
                  )}
                </span>
              </div>
            }
          />
        )}
      </section>
    </div>
  )
}

export function NewProjectPage() {
  const { space } = useOutletContext<SpaceContext>()
  const navigate = useNavigate()
  const portfolios = useCatalog(space.id, 'portfolios')
  const entities = useCatalog(space.id, 'entities')
  const types = useCatalog(space.id, 'project-types')
  const members = useMembers(space.id)
  const create = useCreateProject(space.id)
  // Même identifiant à chaque envoi de ce formulaire : « Réessayer » ne crée pas de doublon.
  const [requestId] = useState(() => crypto.randomUUID())
  const [form, setForm] = useState({
    title: '',
    portfolio_id: '',
    entity_id: '',
    project_type_id: '',
    status: 'to_frame',
    next_step: '',
    due_date: '',
    date_certainty: '',
  })
  const [owner, setOwner] = useState<PersonValue>({ memberId: null, label: '' })
  const set = (key: keyof typeof form) => (value: string) => setForm({ ...form, [key]: value })

  if (space.role === 'reader') {
    return <Alert>Votre rôle Lecteur permet de consulter les projets, pas d’en créer.</Alert>
  }
  if (portfolios.data && portfolios.data.length === 0) {
    return (
      <div className="page-content">
        <PageHeader title="Nouveau projet" />
        <Alert tone="warn">
          Un projet appartient à un portefeuille, et l’espace n’en a pas encore.{' '}
          {space.role === 'owner' ? (
            <Link to={`/espaces/${space.id}/parametres`}>Créer un portefeuille</Link>
          ) : (
            'Demandez au rôle Propriétaire d’en créer un.'
          )}
        </Alert>
      </div>
    )
  }

  function submit(event: FormEvent) {
    event.preventDefault()
    create.mutate(
      {
        client_request_id: requestId,
        title: form.title,
        portfolio_id: form.portfolio_id,
        status: form.status,
        entity_id: form.entity_id || null,
        project_type_id: form.project_type_id || null,
        next_step: form.next_step || null,
        due_date: form.due_date || null,
        date_certainty: form.due_date && form.date_certainty ? form.date_certainty : null,
        ...personPayload(owner, 'owner'),
      },
      {
        onSuccess: (project) =>
          navigate(`/espaces/${space.id}/projets/${project.id}`, { replace: true }),
      },
    )
  }

  return (
    <div className="page-content page-content--narrow">
      <PageHeader
        title="Nouveau projet"
        subtitle="L’essentiel suffit pour commencer : vous compléterez la fiche ensuite."
      />
      <form className="card-panel form-grid" onSubmit={submit}>
        <div className="field form-grid__full">
          <label htmlFor="p-title">Titre du projet *</label>
          <input
            id="p-title"
            required
            maxLength={200}
            placeholder="Ex. : Salon Dakar Tech 2026"
            value={form.title}
            onChange={(e) => set('title')(e.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor="p-portfolio">Portefeuille *</label>
          <select
            id="p-portfolio"
            required
            value={form.portfolio_id}
            onChange={(e) => set('portfolio_id')(e.target.value)}
          >
            <option value="">Choisir…</option>
            {portfolios.data?.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="p-entity">Filiale</label>
          <select
            id="p-entity"
            value={form.entity_id}
            onChange={(e) => set('entity_id')(e.target.value)}
          >
            <option value="">Non précisée</option>
            {entities.data?.map((e) => (
              <option key={e.id} value={e.id}>
                {e.name}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="p-type">Type de projet</label>
          <select
            id="p-type"
            value={form.project_type_id}
            onChange={(e) => set('project_type_id')(e.target.value)}
          >
            <option value="">Non précisé</option>
            {types.data?.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="p-status">Statut</label>
          <select id="p-status" value={form.status} onChange={(e) => set('status')(e.target.value)}>
            {OPEN_PROJECT_STATUSES.map((s) => (
              <option key={s} value={s}>
                {PROJECT_STATUS[s].label}
              </option>
            ))}
          </select>
        </div>
        <PersonField
          id="p-owner"
          label="Responsable du suivi"
          members={members.data ?? []}
          value={owner}
          onChange={setOwner}
        />
        <div className="field form-grid__full">
          <label htmlFor="p-next">Prochaine étape</label>
          <input
            id="p-next"
            maxLength={5000}
            placeholder="Ce qui doit se passer ensuite"
            value={form.next_step}
            onChange={(e) => set('next_step')(e.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor="p-due">Échéance</label>
          <input
            id="p-due"
            type="date"
            value={form.due_date}
            onChange={(e) => set('due_date')(e.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor="p-certainty">Certitude de l’échéance</label>
          <select
            id="p-certainty"
            disabled={!form.due_date}
            value={form.date_certainty}
            onChange={(e) => set('date_certainty')(e.target.value)}
          >
            <option value="">Non précisée</option>
            {Object.entries(CERTAINTY).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>
        {create.isError && (
          <div className="form-grid__full">
            <Alert>{errorMessage(create.error)}</Alert>
          </div>
        )}
        <div className="form-grid__full form-actions">
          <button className="button button--primary" type="submit" disabled={create.isPending}>
            {create.isPending ? 'Création…' : create.isError ? 'Réessayer' : 'Créer le projet'}
          </button>
          <Link className="button button--ghost" to={`/espaces/${space.id}/projets`}>
            Annuler
          </Link>
        </div>
      </form>
    </div>
  )
}
