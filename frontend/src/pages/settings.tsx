import { useMemo, useState, type FormEvent } from 'react'
import { useOutletContext } from 'react-router'
import { errorMessage } from '../api/client'
import {
  useCatalog,
  useCreateCatalogItem,
  useUpdateCatalogItem,
  useUpdateSpace,
  type CatalogItem,
  type CatalogResource,
} from '../api/queries'
import { BackupSection } from '../components/backup-section'
import { TemplatesSection } from '../components/templates'
import { AiSettingsSection } from '../components/assistant'
import { PlusIcon } from '../components/icons'
import { Alert, PageHeader, StatusPill, Skeleton } from '../components/ui'
import { allTimezones } from '../timezones'
import { COLORS, PORTFOLIO_EMOJIS } from '../colors'
import type { SpaceContext } from './space-layout'
import { PortfolioMark } from '../components/portfolio-mark'

type Field = {
  key: 'description' | 'country' | 'color' | 'kind' | 'emoji'
  label: string
  maxLength?: number
}

type Config = {
  resource: CatalogResource
  title: string
  help: string
  addLabel: string
  emptyLabel: string
  placeholder: string
  fields: Field[]
}

const SECTIONS: Config[] = [
  {
    resource: 'portfolios',
    title: 'Portefeuilles',
    help: 'Regroupent les projets pour le suivi (ex. : Événements, Projets groupe).',
    addLabel: 'Ajouter le portefeuille',
    emptyLabel: 'Aucun portefeuille pour l’instant.',
    placeholder: 'Ex. : Événements',
    fields: [
      { key: 'color', label: 'Couleur' },
      { key: 'emoji', label: 'Repère (emoji)' },
      { key: 'description', label: 'Description', maxLength: 500 },
    ],
  },
  {
    resource: 'entities',
    title: 'Filiales et entités',
    help: 'L’entité responsable ou bénéficiaire d’un projet. Distincte du portefeuille.',
    addLabel: 'Ajouter la filiale',
    emptyLabel: 'Aucune filiale pour l’instant.',
    placeholder: 'Ex. : Horizon Events',
    fields: [{ key: 'country', label: 'Pays', maxLength: 80 }],
  },
  {
    resource: 'project-types',
    title: 'Types de projets',
    help: 'Classent la nature d’un projet : événement, produit, mission…',
    addLabel: 'Ajouter le type',
    emptyLabel: 'Aucun type de projet pour l’instant.',
    placeholder: 'Ex. : Campagne',
    fields: [{ key: 'kind', label: 'Nature' }],
  },
  {
    resource: 'programs',
    title: 'Programmes d’événements',
    help: 'Un événement qui revient (ex. salon annuel). Chaque édition est un projet rattaché au programme.',
    addLabel: 'Ajouter le programme',
    emptyLabel: 'Aucun programme pour l’instant.',
    placeholder: 'Ex. : Salon Dakar Tech',
    fields: [{ key: 'description', label: 'Description', maxLength: 500 }],
  },
]

const KINDS: { value: string; label: string }[] = [
  { value: 'standard', label: 'Projet standard' },
  { value: 'event', label: 'Événement' },
]

function FieldInput({
  field,
  value,
  onChange,
  id,
}: {
  field: Field
  value: string
  onChange: (value: string) => void
  id: string
}) {
  if (field.key === 'kind') {
    return (
      <select id={id} value={value} onChange={(e) => onChange(e.target.value)}>
        {KINDS.map((k) => (
          <option key={k.value} value={k.value}>
            {k.label}
          </option>
        ))}
      </select>
    )
  }
  if (field.key === 'emoji') {
    return (
      <select id={id} value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">Aucun (pastille de couleur)</option>
        {PORTFOLIO_EMOJIS.map((e) => (
          <option key={e.value} value={e.value}>
            {e.value} {e.label}
          </option>
        ))}
      </select>
    )
  }
  if (field.key === 'color') {
    return (
      <select id={id} value={value} onChange={(e) => onChange(e.target.value)}>
        {COLORS.map((c) => (
          <option key={c.value} value={c.value}>
            {c.label}
          </option>
        ))}
      </select>
    )
  }
  return (
    <input
      id={id}
      maxLength={field.maxLength}
      value={value}
      onChange={(e) => onChange(e.target.value)}
    />
  )
}

function emptyValues(config: Config, item?: CatalogItem): Record<string, string> {
  const values: Record<string, string> = { name: item?.name ?? '' }
  for (const field of config.fields) {
    values[field.key] =
      (item?.[field.key] as string | null | undefined) ??
      (field.key === 'color' ? 'orange' : field.key === 'kind' ? 'standard' : '')
  }
  return values
}

function ItemForm({
  config,
  initial,
  submitLabel,
  pending,
  onSubmit,
  onCancel,
  idPrefix,
}: {
  config: Config
  initial: Record<string, string>
  submitLabel: string
  pending: boolean
  onSubmit: (values: Record<string, string>) => void
  onCancel?: () => void
  idPrefix: string
}) {
  const [values, setValues] = useState(initial)

  function submit(event: FormEvent) {
    event.preventDefault()
    onSubmit(values)
  }

  return (
    <form className="item-form" onSubmit={submit}>
      <div className="field item-form__name">
        <label htmlFor={`${idPrefix}-name`}>Nom</label>
        <input
          id={`${idPrefix}-name`}
          required
          maxLength={120}
          placeholder={config.placeholder}
          value={values.name}
          onChange={(e) => setValues({ ...values, name: e.target.value })}
        />
      </div>
      {config.fields.map((field) => (
        <div
          key={field.key}
          className={field.key === 'description' ? 'field item-form__wide' : 'field'}
        >
          <label htmlFor={`${idPrefix}-${field.key}`}>{field.label}</label>
          <FieldInput
            id={`${idPrefix}-${field.key}`}
            field={field}
            value={values[field.key]}
            onChange={(value) => setValues({ ...values, [field.key]: value })}
          />
        </div>
      ))}
      <div className="item-form__actions">
        <button className="button button--primary" type="submit" disabled={pending}>
          {submitLabel}
        </button>
        {onCancel && (
          <button className="button button--ghost" type="button" onClick={onCancel}>
            Annuler
          </button>
        )}
      </div>
    </form>
  )
}

function ItemRow({
  config,
  item,
  spaceId,
  canManage,
}: {
  config: Config
  item: CatalogItem
  spaceId: string
  canManage: boolean
}) {
  const update = useUpdateCatalogItem(spaceId, config.resource)
  const [editing, setEditing] = useState(false)
  const details = config.fields
    .filter((f) => f.key !== 'color' && f.key !== 'kind' && f.key !== 'emoji')
    .map((f) => item[f.key])
    .filter(Boolean)
    .join(' · ')

  if (editing) {
    return (
      <li className="item-row item-row--editing">
        <ItemForm
          config={config}
          initial={emptyValues(config, item)}
          submitLabel="Enregistrer"
          pending={update.isPending}
          idPrefix={`edit-${item.id}`}
          onCancel={() => setEditing(false)}
          onSubmit={(values) =>
            update.mutate({ item, changes: values }, { onSuccess: () => setEditing(false) })
          }
        />
        {update.isError && <Alert>{errorMessage(update.error)}</Alert>}
      </li>
    )
  }

  return (
    <li className={item.archived ? 'item-row item-row--archived' : 'item-row'}>
      <PortfolioMark color={item.color} emoji={item.emoji} />
      <span className="item-row__text">
        <span className="item-row__name">{item.name}</span>
        {details && <span className="item-row__details">{details}</span>}
      </span>
      {item.kind === 'event' && <StatusPill tone="info">Événement</StatusPill>}
      {item.archived && <StatusPill tone="neutral">Archivé</StatusPill>}
      {canManage && (
        <span className="item-row__actions">
          {!item.archived && (
            <button type="button" className="button button--small" onClick={() => setEditing(true)}>
              Modifier
            </button>
          )}
          <button
            type="button"
            className="button button--small"
            disabled={update.isPending}
            onClick={() => update.mutate({ item, changes: { archived: !item.archived } })}
          >
            {item.archived ? 'Restaurer' : 'Archiver'}
          </button>
        </span>
      )}
      {update.isError && <Alert>{errorMessage(update.error)}</Alert>}
    </li>
  )
}

function CatalogSection({
  config,
  spaceId,
  canManage,
}: {
  config: Config
  spaceId: string
  canManage: boolean
}) {
  const [showArchived, setShowArchived] = useState(false)
  const [adding, setAdding] = useState(false)
  const [formKey, setFormKey] = useState(0)
  const items = useCatalog(spaceId, config.resource, showArchived)
  const create = useCreateCatalogItem(spaceId, config.resource)
  const toggleId = `archived-${config.resource}`

  return (
    <section className="card-panel" aria-labelledby={`title-${config.resource}`}>
      <div className="card-panel__head">
        <div>
          <h2 id={`title-${config.resource}`}>{config.title}</h2>
          <p className="card-panel__help">{config.help}</p>
        </div>
        {canManage && !adding && (
          <button type="button" className="button button--small" onClick={() => setAdding(true)}>
            <PlusIcon /> Ajouter
          </button>
        )}
      </div>

      {adding && (
        <div className="item-add">
          <ItemForm
            key={formKey}
            config={config}
            initial={emptyValues(config)}
            submitLabel={config.addLabel}
            pending={create.isPending}
            idPrefix={`new-${config.resource}`}
            onCancel={() => setAdding(false)}
            onSubmit={(values) =>
              create.mutate(values, {
                onSuccess: () => {
                  setFormKey((k) => k + 1)
                  setAdding(false)
                },
              })
            }
          />
          {create.isError && <Alert>{errorMessage(create.error)}</Alert>}
        </div>
      )}

      {items.isPending && <Skeleton />}
      {items.isError && <Alert>{errorMessage(items.error)}</Alert>}
      {items.data && items.data.length === 0 && (
        <p className="muted">{showArchived ? 'Aucun élément.' : config.emptyLabel}</p>
      )}
      {items.data && items.data.length > 0 && (
        <ul className="item-list">
          {items.data.map((item) => (
            <ItemRow
              key={item.id}
              config={config}
              item={item}
              spaceId={spaceId}
              canManage={canManage}
            />
          ))}
        </ul>
      )}

      <label className="checkbox" htmlFor={toggleId}>
        <input
          id={toggleId}
          type="checkbox"
          checked={showArchived}
          onChange={(e) => setShowArchived(e.target.checked)}
        />
        Afficher les éléments archivés
      </label>
    </section>
  )
}

/** Mode simple / mode complet (décision du 10 nov. 2026) : seul l'affichage change. */
function ModeSettings() {
  const { space } = useOutletContext<SpaceContext>()
  const update = useUpdateSpace(space.id)
  const canManage = space.role === 'owner'
  const advanced = space.advanced_mode
  return (
    <section className="card-panel" aria-labelledby="title-mode">
      <div className="card-panel__head">
        <div>
          <h2 id="title-mode">Mode d’affichage</h2>
          <p className="card-panel__help">
            Le <strong>mode simple</strong> garde PILOT léger pour démarrer. Le{' '}
            <strong>mode complet</strong> ajoute les jalons, le registre des décisions et des
            réunions, les sections de projet, les statuts « À qualifier », « Bloquée » et « En
            attente de validation », la priorité, la date de début et le motif des reports. Changer
            de mode ne supprime rien : seules les fonctions affichées changent.
          </p>
        </div>
      </div>
      <div className="ai-toggle">
        <StatusPill tone={advanced ? 'violet' : 'neutral'}>
          {advanced ? 'Mode complet' : 'Mode simple'}
        </StatusPill>
        {canManage ? (
          <button
            type="button"
            className={advanced ? 'button button--small' : 'button button--small button--primary'}
            disabled={update.isPending}
            onClick={() => update.mutate({ advanced_mode: !advanced, version: space.version })}
          >
            {advanced ? 'Revenir au mode simple' : 'Passer au mode complet'}
          </button>
        ) : (
          <span className="muted">Seul un propriétaire de l’espace peut changer de mode.</span>
        )}
      </div>
      {update.isError && <Alert>{errorMessage(update.error)}</Alert>}
    </section>
  )
}

function SpaceSettings() {
  const { space } = useOutletContext<SpaceContext>()
  const update = useUpdateSpace(space.id)
  const [name, setName] = useState(space.name)
  const [timezone, setTimezone] = useState(space.timezone)
  const zones = useMemo(() => allTimezones(space.timezone), [space.timezone])
  const changed = name.trim() !== space.name || timezone !== space.timezone
  const canManage = space.role === 'owner'

  function submit(event: FormEvent) {
    event.preventDefault()
    update.mutate({ name, timezone, version: space.version })
  }

  return (
    <section className="card-panel" aria-labelledby="title-space">
      <div className="card-panel__head">
        <div>
          <h2 id="title-space">Espace</h2>
          <p className="card-panel__help">Le fuseau horaire sert aux échéances et aux rappels.</p>
        </div>
      </div>
      <form className="item-form" onSubmit={submit}>
        <div className="field item-form__name">
          <label htmlFor="space-name">Nom de l’espace</label>
          <input
            id="space-name"
            required
            maxLength={120}
            disabled={!canManage}
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor="space-timezone">Fuseau horaire</label>
          <select
            id="space-timezone"
            disabled={!canManage}
            value={timezone}
            onChange={(e) => setTimezone(e.target.value)}
          >
            {zones.map((zone) => (
              <option key={zone} value={zone}>
                {zone}
              </option>
            ))}
          </select>
        </div>
        {canManage && (
          <div className="item-form__actions">
            <button
              className="button button--primary"
              type="submit"
              disabled={!changed || update.isPending}
            >
              Enregistrer
            </button>
          </div>
        )}
      </form>
      {update.isSuccess && !changed && <Alert tone="ok">Modifications enregistrées.</Alert>}
      {update.isError && <Alert>{errorMessage(update.error)}</Alert>}
    </section>
  )
}

export function SettingsPage() {
  const { space } = useOutletContext<SpaceContext>()
  const canManage = space.role === 'owner'

  return (
    <div className="page-content">
      <PageHeader
        title="Paramètres et structure"
        subtitle={
          canManage
            ? 'Organisez votre espace. Un élément archivé n’est plus proposé, mais ses projets sont conservés.'
            : 'Consultation seule : seul le rôle Propriétaire modifie la structure de l’espace.'
        }
      />
      <SpaceSettings />
      <ModeSettings />
      {canManage && <AiSettingsSection spaceId={space.id} />}
      {SECTIONS.map((config) => (
        <CatalogSection
          key={config.resource}
          config={config}
          spaceId={space.id}
          canManage={canManage}
        />
      ))}
      {space.role !== 'reader' && space.role !== 'guest' && (
        <TemplatesSection spaceId={space.id} canManage={canManage} />
      )}
      <BackupSection spaceId={space.id} canExport={canManage} />
    </div>
  )
}
