import { useState, type FormEvent } from 'react'
import { Link, useNavigate, useOutletContext, useSearchParams } from 'react-router'
import { canWriteSpace, errorMessage } from '../api/client'
import {
  useAdvanced,
  useCatalog,
  useCreateProject,
  useCustomFields,
  useCustomValues,
  useMembers,
  useProjects,
  useTemplates,
} from '../api/queries'
import { fieldFilterChoices, matchesFieldFilter } from '../components/custom-fields'
import { FolderIcon, PlusIcon } from '../components/icons'
import { PersonField, type PersonValue } from '../components/person-field'
import { ProjectTable } from '../components/project-table'
import { Alert, PageHeader, Skeleton } from '../components/ui'
import {
  CERTAINTY,
  OPEN_PROJECT_STATUSES,
  PROJECT_STATUS,
  todayIso,
  type ProjectStatus,
} from '../labels'
import { ATTENTION, inPeriod, matchesAttention, type Attention } from '../attention'
import { personPayload } from '../person'
import type { SpaceContext } from './space-layout'
import { countryFlag } from '../countries'

/** Filtres gardés dans l'adresse : une vue filtrée peut être partagée ou mise en favori. */
const FILTER_KEYS = [
  'q',
  'portefeuille',
  'filiale',
  'pays',
  'statut',
  'attention',
  'du',
  'au',
  'champ',
] as const
type FilterKey = (typeof FILTER_KEYS)[number]

export function ProjectsPage() {
  const { space } = useOutletContext<SpaceContext>()
  const [params, setParams] = useSearchParams()
  const get = (key: FilterKey) => params.get(key) ?? ''
  const set = (key: FilterKey, value: string) =>
    setParams(
      (current) => {
        const next = new URLSearchParams(current)
        if (value) next.set(key, value)
        else next.delete(key)
        return next
      },
      { replace: true },
    )
  const portfolios = useCatalog(space.id, 'portfolios')
  const entities = useCatalog(space.id, 'entities')
  const projects = useProjects(space.id)
  const canWrite = canWriteSpace(space.role)
  const today = todayIso(space.timezone)

  const advanced = useAdvanced(space.id)
  const customFields = useCustomFields(space.id, advanced).data ?? []
  const customValues = useCustomValues(space.id, advanced && Boolean(get('champ'))).data ?? {}
  const members = useMembers(space.id).data ?? []
  const fieldChoices = advanced ? fieldFilterChoices(customFields, members) : []
  const all = projects.data ?? []
  const countries = [
    ...new Set(all.map((p) => p.country).filter((c): c is string => Boolean(c))),
  ].sort()
  const q = get('q').trim().toLowerCase()
  const attention = get('attention') as Attention | ''
  const filtered = all.filter(
    (p) =>
      (!q ||
        p.title.toLowerCase().includes(q) ||
        (p.next_step ?? '').toLowerCase().includes(q) ||
        (p.owner.name ?? '').toLowerCase().includes(q)) &&
      (!get('portefeuille') || p.portfolio.id === get('portefeuille')) &&
      (!get('filiale') || p.entity?.id === get('filiale')) &&
      (!get('pays') || p.country === get('pays')) &&
      (!get('statut') || p.status === get('statut')) &&
      (!attention || matchesAttention(p, attention, today)) &&
      (!(get('du') || get('au')) || inPeriod(p, get('du'), get('au'))) &&
      (!get('champ') ||
        !advanced ||
        matchesFieldFilter(customFields, customValues[p.id] ?? {}, get('champ'))),
  )
  const active = FILTER_KEYS.filter((k) => get(k))

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

      <div className="filters" role="search" aria-label="Filtrer les projets">
        <label className="filters__search">
          <span className="visually-hidden">Rechercher un projet</span>
          <input
            type="search"
            placeholder="Rechercher : titre, prochaine étape, responsable…"
            value={get('q')}
            onChange={(e) => set('q', e.target.value)}
          />
        </label>
        <select
          aria-label="Attention"
          value={attention}
          onChange={(e) => set('attention', e.target.value)}
        >
          <option value="">Tous les signaux</option>
          {(Object.keys(ATTENTION) as Attention[]).map((a) => (
            <option key={a} value={a}>
              {ATTENTION[a].label}
            </option>
          ))}
        </select>
        <select
          aria-label="Portefeuille"
          value={get('portefeuille')}
          onChange={(e) => set('portefeuille', e.target.value)}
        >
          <option value="">Tous les portefeuilles</option>
          {portfolios.data?.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
        <select
          aria-label="Filiale"
          value={get('filiale')}
          onChange={(e) => set('filiale', e.target.value)}
        >
          <option value="">Toutes les filiales</option>
          {entities.data?.map((e) => (
            <option key={e.id} value={e.id}>
              {e.name}
            </option>
          ))}
        </select>
        <select aria-label="Pays" value={get('pays')} onChange={(e) => set('pays', e.target.value)}>
          <option value="">Tous les pays</option>
          {countries.map((c) => (
            <option key={c} value={c}>
              {`${countryFlag(c)} ${c}`.trim()}
            </option>
          ))}
        </select>
        <select
          aria-label="Statut"
          value={get('statut')}
          onChange={(e) => set('statut', e.target.value)}
        >
          <option value="">Tous les statuts</option>
          {(Object.keys(PROJECT_STATUS) as ProjectStatus[]).map((s) => (
            <option key={s} value={s}>
              {PROJECT_STATUS[s].label}
            </option>
          ))}
        </select>
        {fieldChoices.length > 0 && (
          <select
            aria-label="Champ personnalisé"
            value={get('champ')}
            onChange={(e) => set('champ', e.target.value)}
          >
            <option value="">Tous les champs personnalisés</option>
            {fieldChoices.map((group) => (
              <optgroup key={group.label} label={group.label}>
                {group.options.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>
        )}
        <label className="filters__date">
          Du
          <input type="date" value={get('du')} onChange={(e) => set('du', e.target.value)} />
        </label>
        <label className="filters__date">
          au
          <input type="date" value={get('au')} onChange={(e) => set('au', e.target.value)} />
        </label>
      </div>

      <div className="filters__summary" aria-live="polite">
        <strong>{filtered.length}</strong>&nbsp;projet(s)
        {attention && ` · ${ATTENTION[attention].label} : ${ATTENTION[attention].rule}`}
        {active.length > 0 && (
          <button
            type="button"
            className="button button--small button--ghost"
            onClick={() => setParams({}, { replace: true })}
          >
            Effacer les filtres
          </button>
        )}
      </div>

      <section className="card-panel card-panel--flush" aria-label="Liste des projets">
        {projects.isError && <Alert>{errorMessage(projects.error)}</Alert>}
        {projects.isPending ? (
          <Skeleton lines={5} />
        ) : (
          <ProjectTable
            projects={filtered}
            spaceId={space.id}
            today={today}
            empty={
              <div className="table-empty">
                <span className="icon-tile icon-tile--action">
                  <FolderIcon />
                </span>
                <span>
                  {active.length ? (
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
  const templates = useTemplates(space.id, canWriteSpace(space.role))
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
    origin: '',
    template_id: '',
    start_date: '',
  })
  const [owner, setOwner] = useState<PersonValue>({ memberId: null, label: '' })
  const set = (key: keyof typeof form) => (value: string) => setForm({ ...form, [key]: value })

  if (!canWriteSpace(space.role)) {
    return <Alert>Votre rôle permet de consulter les projets, pas d’en créer.</Alert>
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
        origin: form.origin.trim() || null,
        due_date: form.due_date || null,
        date_certainty: form.due_date && form.date_certainty ? form.date_certainty : null,
        template_id: form.template_id || null,
        start_date: form.start_date || null,
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
        {templates.data && templates.data.length > 0 && (
          <div className="field form-grid__full template-pick">
            <label htmlFor="p-template">Partir d’un modèle</label>
            <select
              id="p-template"
              value={form.template_id}
              onChange={(e) => set('template_id')(e.target.value)}
            >
              <option value="">Aucun : projet vide</option>
              {templates.data.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name} · {t.tasks_count} tâche(s)
                </option>
              ))}
            </select>
            <span className="field__hint">
              Les tâches du modèle sont ajoutées au projet, prêtes à être confiées.
            </span>
          </div>
        )}
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
          <label htmlFor="p-start">Date de début</label>
          <input
            id="p-start"
            type="date"
            value={form.start_date}
            onChange={(e) => set('start_date')(e.target.value)}
          />
          {form.template_id && (
            <span className="field__hint">
              {form.start_date
                ? 'Les échéances des tâches du modèle sont calculées à partir de cette date.'
                : 'Sans date de début, les tâches du modèle arrivent sans échéance.'}
            </span>
          )}
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
        <div className="field form-grid__full">
          <label htmlFor="p-origin">Origine du besoin</label>
          <textarea
            id="p-origin"
            rows={2}
            maxLength={5000}
            placeholder="Ex. : demandé par la direction générale, réunion du 3 novembre"
            value={form.origin}
            onChange={(e) => set('origin')(e.target.value)}
          />
          <span className="field__hint">
            Qui a exprimé ce besoin, et où. Un projet « À cadrer » reste une idée tant que son
            lancement n’est pas validé.
          </span>
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
