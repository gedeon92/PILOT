import { useMemo, useState, type FormEvent } from 'react'
import {
  errorMessage,
  type CustomField,
  type CustomFieldType,
  type Member,
  type Project,
  type ProjectFields,
  type TypePreview,
} from '../api/client'
import {
  previewFieldType,
  useArchiveField,
  useCreateField,
  useCustomFields,
  useHideFields,
  useMembers,
  useProjects,
  useReorderFields,
  useSaveCustomValues,
  useUpdateField,
  type FieldDraft,
} from '../api/queries'
import { formatDay } from '../labels'
import { Alert, StatusPill } from './ui'

/** Étape F4 (cahier V2, CHP01–CHP04) : champs personnalisés des projets et des tâches.
 * Les propriétaires gèrent le catalogue ; chacun remplit les valeurs qu'il a le droit de
 * modifier. Rien n'est effacé en silence : renommer garde l'identifiant, une option retirée
 * reste lisible, un champ est archivé, un changement de type montre d'abord ses effets. */

export const FIELD_TYPES: Record<CustomFieldType, string> = {
  text: 'Texte court',
  long_text: 'Texte long',
  number: 'Nombre',
  percent: 'Pourcentage',
  amount: 'Montant',
  date: 'Date',
  choice: 'Choix unique',
  multi_choice: 'Choix multiple',
  person: 'Personne',
  boolean: 'Oui / non',
  url: 'Lien',
  computed: 'Calculé',
}

const NUMERIC: CustomFieldType[] = ['number', 'percent', 'amount']
const OPS = { difference: 'A − B', sum: 'A + B', ratio: 'A ÷ B (en %)' } as const

type Values = Record<string, unknown>

function memberName(members: Member[] | undefined, id: unknown) {
  const m = members?.find((x) => x.id === id)
  return m ? m.display_name || m.email : 'membre retiré'
}

/** Valeur lisible d'un champ (vide = chaîne vide, jamais « non » ni 0). */
export function formatValue(field: CustomField, value: unknown, members?: Member[]): string {
  if (value === null || value === undefined) return ''
  const label = (id: unknown) => field.options.find((o) => o.id === id)?.label ?? String(id)
  switch (field.type) {
    case 'choice':
      return label(value)
    case 'multi_choice':
      return (value as unknown[]).map(label).join(', ')
    case 'boolean':
      return value ? 'Oui' : 'Non'
    case 'date':
      return formatDay(String(value))
    case 'person':
      return memberName(members, value)
    case 'percent':
      return `${String(value)} %`
    case 'amount':
      return `${Number(value).toLocaleString('fr-FR')} ${String(field.config.currency ?? '')}`.trim()
    case 'number':
    case 'computed': {
      const unit = field.config.unit ? ` ${String(field.config.unit)}` : ''
      const isRatio =
        field.type === 'computed' &&
        (field.config.formula as { op?: string } | undefined)?.op === 'ratio'
      return `${Number(value).toLocaleString('fr-FR')}${isRatio ? ' %' : unit}`
    }
    default:
      return String(value)
  }
}

/** Filtre de la liste des projets (CHP04) : « clé technique:valeur », jamais le libellé. */
export function fieldFilterChoices(fields: CustomField[], members: Member[]) {
  return fields
    .filter(
      (f) =>
        !f.archived &&
        f.target === 'project' &&
        ['choice', 'multi_choice', 'boolean', 'person'].includes(f.type),
    )
    .map((f) => {
      const values: { value: string; label: string }[] =
        f.type === 'boolean'
          ? [
              { value: 'true', label: 'Oui' },
              { value: 'false', label: 'Non' },
            ]
          : f.type === 'person'
            ? members
                .filter((m) => m.status === 'active')
                .map((m) => ({ value: m.id, label: m.display_name || m.email }))
            : f.options.map((o) => ({ value: o.id, label: o.label }))
      return {
        label: f.label,
        options: [...values, { value: '__vide', label: 'Non renseigné' }].map((v) => ({
          value: `${f.key}:${v.value}`,
          label: `${f.label} : ${v.label}`,
        })),
      }
    })
}

export function matchesFieldFilter(fields: CustomField[], values: Values, filter: string) {
  const [key, wanted] = filter.split(':')
  const field = fields.find((f) => f.key === key)
  if (!field) return true
  const value = values[field.id]
  if (wanted === '__vide') return value === undefined || value === null
  if (field.type === 'boolean') return value === (wanted === 'true')
  if (field.type === 'multi_choice') return Array.isArray(value) && value.includes(wanted)
  return value === wanted
}

function FieldInput({
  field,
  value,
  onChange,
  members,
  id,
}: {
  field: CustomField
  value: unknown
  onChange: (v: unknown) => void
  members: Member[]
  id: string
}) {
  const options = field.options.filter(
    (o) =>
      o.active || o.id === value || (Array.isArray(value) && (value as string[]).includes(o.id)),
  )
  switch (field.type) {
    case 'long_text':
      return (
        <textarea
          id={id}
          rows={3}
          maxLength={Number(field.config.max_length ?? 5000)}
          value={(value as string) ?? ''}
          onChange={(e) => onChange(e.target.value)}
        />
      )
    case 'number':
    case 'percent':
    case 'amount':
      return (
        <input
          id={id}
          type="number"
          step="any"
          min={field.config.min as number | undefined}
          max={field.config.max as number | undefined}
          value={value === null || value === undefined ? '' : String(value)}
          onChange={(e) => onChange(e.target.value === '' ? null : Number(e.target.value))}
        />
      )
    case 'date':
      return (
        <input
          id={id}
          type="date"
          value={(value as string) ?? ''}
          onChange={(e) => onChange(e.target.value || null)}
        />
      )
    case 'boolean':
      return (
        <select
          id={id}
          value={value === true ? 'yes' : value === false ? 'no' : ''}
          onChange={(e) => onChange(e.target.value === '' ? null : e.target.value === 'yes')}
        >
          <option value="">— Non renseigné —</option>
          <option value="yes">Oui</option>
          <option value="no">Non</option>
        </select>
      )
    case 'choice':
      return (
        <select
          id={id}
          value={(value as string) ?? ''}
          onChange={(e) => onChange(e.target.value || null)}
        >
          <option value="">— Non renseigné —</option>
          {options.map((o) => (
            <option key={o.id} value={o.id}>
              {o.label}
              {o.active ? '' : ' (retirée)'}
            </option>
          ))}
        </select>
      )
    case 'multi_choice': {
      const chosen = (value as string[] | null) ?? []
      return (
        <fieldset id={id} className="cf-multi">
          <legend className="visually-hidden">{field.label}</legend>
          {options.map((o) => (
            <label key={o.id} className="checkbox">
              <input
                type="checkbox"
                checked={chosen.includes(o.id)}
                onChange={(e) =>
                  onChange(e.target.checked ? [...chosen, o.id] : chosen.filter((x) => x !== o.id))
                }
              />
              {o.label}
              {o.active ? '' : ' (retirée)'}
            </label>
          ))}
        </fieldset>
      )
    }
    case 'person':
      return (
        <select
          id={id}
          value={(value as string) ?? ''}
          onChange={(e) => onChange(e.target.value || null)}
        >
          <option value="">— Personne —</option>
          {members
            .filter((m) => m.status === 'active')
            .map((m) => (
              <option key={m.id} value={m.id}>
                {m.display_name || m.email}
              </option>
            ))}
        </select>
      )
    case 'url':
      return (
        <input
          id={id}
          type="url"
          placeholder="https://"
          value={(value as string) ?? ''}
          onChange={(e) => onChange(e.target.value)}
        />
      )
    default:
      return (
        <input
          id={id}
          maxLength={Number(field.config.max_length ?? 200)}
          value={(value as string) ?? ''}
          onChange={(e) => onChange(e.target.value)}
        />
      )
  }
}

/** Formulaire des valeurs : projet (taskId absent) ou tâche. */
function ValuesEditor({
  spaceId,
  projectId,
  taskId,
  fields,
  values,
  canEdit,
  hidden,
}: {
  spaceId: string
  projectId: string
  taskId?: string
  fields: CustomField[]
  values: Values
  canEdit: boolean
  hidden: string[]
}) {
  const members = useMembers(spaceId).data ?? []
  const save = useSaveCustomValues(spaceId, projectId)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState<Values>({})
  const shown = fields.filter((f) => !f.archived && !hidden.includes(f.id))
  const archivedWithValue = fields.filter((f) => f.archived && values[f.id] !== undefined)
  const missing = shown.filter((f) => f.required && values[f.id] === undefined)
  const prefix = taskId ? `cf-task-${taskId}` : `cf-${projectId}`

  function start() {
    setDraft(Object.fromEntries(shown.map((f) => [f.id, values[f.id] ?? null])))
    setEditing(true)
  }

  function submit(event: FormEvent) {
    event.preventDefault()
    const changed = Object.fromEntries(
      Object.entries(draft)
        .filter(([id, v]) => {
          const field = shown.find((f) => f.id === id)
          if (!field || field.type === 'computed') return false
          const empty = v === '' || v === null || (Array.isArray(v) && v.length === 0)
          const before = values[id] ?? null
          return JSON.stringify(empty ? null : v) !== JSON.stringify(before)
        })
        .map(([id, v]) => [id, v === '' ? null : v]),
    )
    save.mutate({ taskId, values: changed }, { onSuccess: () => setEditing(false) })
  }

  if (shown.length === 0 && archivedWithValue.length === 0) return null

  if (editing) {
    return (
      <form className="cf-form" onSubmit={submit}>
        {shown.map((f) => (
          <div className="field" key={f.id}>
            <label htmlFor={`${prefix}-${f.id}`}>
              {f.label}
              {f.required && <span aria-hidden="true"> *</span>}
            </label>
            {f.type === 'computed' ? (
              <p className="field__hint" id={`${prefix}-${f.id}`}>
                {formatValue(f, values[f.id], members) || 'Non calculable'} · calculé
                automatiquement
              </p>
            ) : (
              <FieldInput
                id={`${prefix}-${f.id}`}
                field={f}
                value={draft[f.id]}
                members={members}
                onChange={(v) => setDraft((d) => ({ ...d, [f.id]: v }))}
              />
            )}
            {f.description && <p className="field__hint">{f.description}</p>}
          </div>
        ))}
        {save.isError && <Alert>{errorMessage(save.error)}</Alert>}
        <div className="item-form__actions">
          <button className="button button--primary" disabled={save.isPending}>
            Enregistrer
          </button>
          <button type="button" className="button button--ghost" onClick={() => setEditing(false)}>
            Annuler
          </button>
        </div>
      </form>
    )
  }

  return (
    <div className="cf-view">
      {missing.length > 0 && (
        <p className="cf-missing">À compléter : {missing.map((f) => f.label).join(', ')}</p>
      )}
      <dl className="cf-list">
        {[...shown, ...archivedWithValue].map((f) => {
          const text = formatValue(f, values[f.id], members)
          return (
            <div key={f.id} className="cf-list__row">
              <dt>
                {f.label}
                {f.archived && <span className="muted"> (archivé)</span>}
              </dt>
              <dd className={text ? undefined : 'muted'}>
                {text || (f.type === 'computed' ? 'Non calculable' : '—')}
              </dd>
            </div>
          )
        })}
      </dl>
      {canEdit && shown.some((f) => f.type !== 'computed') && (
        <button type="button" className="button button--small" onClick={start}>
          Modifier les champs
        </button>
      )}
    </div>
  )
}

/** Carte « Champs personnalisés » de la fiche projet (mode complet). */
export function ProjectCustomFields({
  spaceId,
  project,
  data,
  canEdit,
}: {
  spaceId: string
  project: Project
  data: ProjectFields | undefined
  canEdit: boolean
}) {
  const hide = useHideFields(spaceId, project.id)
  const [choosing, setChoosing] = useState(false)
  if (!data) return null
  const fields = data.fields.filter((f) => f.target === 'project')
  const active = fields.filter((f) => !f.archived)
  const hidden = data.hidden_ids
  if (active.length === 0 && !fields.some((f) => data.values[f.id] !== undefined)) return null

  function toggle(id: string, show: boolean) {
    const next = show ? hidden.filter((h) => h !== id) : [...hidden, id]
    hide.mutate(next)
  }

  const allActive = data.fields.filter((f) => !f.archived)
  return (
    <section className="card-panel" aria-labelledby="title-cf">
      <div className="card-panel__head">
        <div>
          <h2 id="title-cf">Champs personnalisés</h2>
          <p className="card-panel__help">
            Informations propres à votre organisation. Les champs viennent du catalogue de l’espace
            (Paramètres) ; vous pouvez masquer ceux qui ne concernent pas ce projet.
          </p>
        </div>
        {canEdit && allActive.length > 0 && (
          <button
            type="button"
            className="button button--small button--ghost"
            onClick={() => setChoosing((c) => !c)}
          >
            {choosing ? 'Fermer' : 'Champs affichés'}
          </button>
        )}
      </div>
      {choosing && (
        <fieldset className="cf-choose">
          <legend>Champs affichés dans ce projet (projet et tâches)</legend>
          {allActive.map((f) => (
            <label key={f.id} className="checkbox">
              <input
                type="checkbox"
                checked={!hidden.includes(f.id)}
                disabled={hide.isPending}
                onChange={(e) => toggle(f.id, e.target.checked)}
              />
              {f.label}
              <span className="muted">
                {' '}
                · {f.target === 'task' ? 'tâches' : 'projet'}
                {f.project_id ? ' · propre à ce projet' : ''}
              </span>
            </label>
          ))}
          <p className="field__hint">Masquer un champ ne supprime aucune valeur.</p>
        </fieldset>
      )}
      <ValuesEditor
        spaceId={spaceId}
        projectId={project.id}
        fields={fields}
        values={data.values}
        canEdit={canEdit}
        hidden={hidden}
      />
    </section>
  )
}

/** Champs personnalisés d'une tâche, dans la fenêtre de la tâche (mode complet). */
export function TaskCustomFields({
  spaceId,
  projectId,
  taskId,
  data,
  canEdit,
}: {
  spaceId: string
  projectId: string
  taskId: string
  data: ProjectFields | undefined
  canEdit: boolean
}) {
  if (!data) return null
  const fields = data.fields.filter((f) => f.target === 'task')
  if (fields.length === 0) return null
  return (
    <section className="task-drawer__section cf-task" aria-label="Champs personnalisés">
      <h3>Champs personnalisés</h3>
      <ValuesEditor
        spaceId={spaceId}
        projectId={projectId}
        taskId={taskId}
        fields={fields}
        values={data.task_values[taskId] ?? {}}
        canEdit={canEdit}
        hidden={data.hidden_ids}
      />
    </section>
  )
}

// ---------- Catalogue (Paramètres) ----------

function FieldForm({
  spaceId,
  fields,
  projects,
  onDone,
}: {
  spaceId: string
  fields: CustomField[]
  projects: Project[]
  onDone: () => void
}) {
  const create = useCreateField(spaceId)
  const [draft, setDraft] = useState({
    label: '',
    target: 'project' as 'project' | 'task',
    type: 'text' as CustomFieldType,
    description: '',
    required: false,
    project_id: '',
    options: '',
    unit: '',
    currency: 'EUR',
    min: '',
    max: '',
    op: 'difference' as keyof typeof OPS,
    a: '',
    b: '',
  })
  const set = (patch: Partial<typeof draft>) => setDraft((d) => ({ ...d, ...patch }))
  const numericFields = fields.filter(
    (f) =>
      !f.archived &&
      NUMERIC.includes(f.type) &&
      f.target === draft.target &&
      (f.project_id === null || f.project_id === (draft.project_id || null)),
  )

  function submit(event: FormEvent) {
    event.preventDefault()
    const config: Record<string, unknown> = {}
    if (NUMERIC.includes(draft.type)) {
      if (draft.min !== '') config.min = Number(draft.min)
      if (draft.max !== '') config.max = Number(draft.max)
    }
    if (draft.type === 'number' && draft.unit.trim()) config.unit = draft.unit.trim()
    if (draft.type === 'amount') config.currency = draft.currency.trim()
    if (draft.type === 'computed') config.formula = { op: draft.op, a: draft.a, b: draft.b }
    const body: FieldDraft = {
      label: draft.label,
      target: draft.target,
      type: draft.type,
      description: draft.description.trim() || null,
      required: draft.required,
      project_id: draft.project_id || null,
      options:
        draft.type === 'choice' || draft.type === 'multi_choice'
          ? draft.options
              .split('\n')
              .map((o) => o.trim())
              .filter(Boolean)
          : [],
      config,
    }
    create.mutate(body, { onSuccess: onDone })
  }

  return (
    <form className="item-form cf-create" onSubmit={submit}>
      <div className="field item-form__name">
        <label htmlFor="cf-label">Nom du champ</label>
        <input
          id="cf-label"
          required
          maxLength={120}
          autoFocus
          placeholder="ex. Budget autorisé, Type de risque"
          value={draft.label}
          onChange={(e) => set({ label: e.target.value })}
        />
      </div>
      <div className="field">
        <label htmlFor="cf-target">Sur quelle fiche ?</label>
        <select
          id="cf-target"
          value={draft.target}
          onChange={(e) => set({ target: e.target.value as 'project' | 'task' })}
        >
          <option value="project">Projet</option>
          <option value="task">Tâche</option>
        </select>
      </div>
      <div className="field">
        <label htmlFor="cf-type">Type</label>
        <select
          id="cf-type"
          value={draft.type}
          onChange={(e) => set({ type: e.target.value as CustomFieldType })}
        >
          {Object.entries(FIELD_TYPES).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </div>
      <div className="field">
        <label htmlFor="cf-scope">Portée</label>
        <select
          id="cf-scope"
          value={draft.project_id}
          onChange={(e) => set({ project_id: e.target.value })}
        >
          <option value="">Tous les projets</option>
          {projects.map((p) => (
            <option key={p.id} value={p.id}>
              Seulement : {p.title}
            </option>
          ))}
        </select>
      </div>
      {(draft.type === 'choice' || draft.type === 'multi_choice') && (
        <div className="field item-form__name">
          <label htmlFor="cf-options">Choix proposés (un par ligne)</label>
          <textarea
            id="cf-options"
            rows={4}
            required
            value={draft.options}
            onChange={(e) => set({ options: e.target.value })}
          />
        </div>
      )}
      {draft.type === 'amount' && (
        <div className="field">
          <label htmlFor="cf-currency">Devise</label>
          <input
            id="cf-currency"
            required
            maxLength={10}
            value={draft.currency}
            onChange={(e) => set({ currency: e.target.value })}
          />
        </div>
      )}
      {draft.type === 'number' && (
        <div className="field">
          <label htmlFor="cf-unit">Unité (facultatif)</label>
          <input
            id="cf-unit"
            maxLength={20}
            placeholder="jours, personnes…"
            value={draft.unit}
            onChange={(e) => set({ unit: e.target.value })}
          />
        </div>
      )}
      {NUMERIC.includes(draft.type) && (
        <>
          <div className="field">
            <label htmlFor="cf-min">Minimum</label>
            <input
              id="cf-min"
              type="number"
              step="any"
              value={draft.min}
              onChange={(e) => set({ min: e.target.value })}
            />
          </div>
          <div className="field">
            <label htmlFor="cf-max">Maximum</label>
            <input
              id="cf-max"
              type="number"
              step="any"
              value={draft.max}
              onChange={(e) => set({ max: e.target.value })}
            />
          </div>
        </>
      )}
      {draft.type === 'computed' && (
        <>
          {numericFields.length < 2 && (
            <Alert tone="info">
              Créez d’abord au moins deux champs numériques sur la même fiche (par exemple « Budget
              autorisé » et « Dépensé »).
            </Alert>
          )}
          <div className="field">
            <label htmlFor="cf-a">Champ A</label>
            <select id="cf-a" required value={draft.a} onChange={(e) => set({ a: e.target.value })}>
              <option value="">—</option>
              {numericFields.map((f) => (
                <option key={f.id} value={f.id}>
                  {f.label}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="cf-op">Calcul</label>
            <select
              id="cf-op"
              value={draft.op}
              onChange={(e) => set({ op: e.target.value as keyof typeof OPS })}
            >
              {Object.entries(OPS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="cf-b">Champ B</label>
            <select id="cf-b" required value={draft.b} onChange={(e) => set({ b: e.target.value })}>
              <option value="">—</option>
              {numericFields.map((f) => (
                <option key={f.id} value={f.id}>
                  {f.label}
                </option>
              ))}
            </select>
          </div>
        </>
      )}
      <div className="field item-form__name">
        <label htmlFor="cf-description">Description (facultatif)</label>
        <input
          id="cf-description"
          maxLength={1000}
          value={draft.description}
          onChange={(e) => set({ description: e.target.value })}
        />
      </div>
      {draft.type !== 'computed' && (
        <label className="field field--check" htmlFor="cf-required">
          <input
            id="cf-required"
            type="checkbox"
            checked={draft.required}
            onChange={(e) => set({ required: e.target.checked })}
          />
          À compléter obligatoirement (signalé tant qu’il est vide)
        </label>
      )}
      {create.isError && <Alert>{errorMessage(create.error)}</Alert>}
      <div className="item-form__actions">
        <button className="button button--primary" disabled={create.isPending}>
          Ajouter le champ
        </button>
        <button type="button" className="button button--ghost" onClick={onDone}>
          Annuler
        </button>
      </div>
    </form>
  )
}

function FieldEditor({
  spaceId,
  field,
  onDone,
}: {
  spaceId: string
  field: CustomField
  onDone: () => void
}) {
  const update = useUpdateField(spaceId)
  const [label, setLabel] = useState(field.label)
  const [description, setDescription] = useState(field.description ?? '')
  const [required, setRequired] = useState(field.required)
  const [options, setOptions] = useState(field.options.map((o) => ({ ...o })))
  const [newOption, setNewOption] = useState('')
  const [type, setType] = useState<CustomFieldType>(field.type)
  const [preview, setPreview] = useState<TypePreview | null>(null)
  const [previewError, setPreviewError] = useState<string | null>(null)
  const hasChoices = field.type === 'choice' || field.type === 'multi_choice'

  async function checkType(next: CustomFieldType) {
    setType(next)
    setPreview(null)
    setPreviewError(null)
    if (next === field.type) return
    try {
      setPreview(await previewFieldType(spaceId, field.id, next))
    } catch (error) {
      setPreviewError(errorMessage(error))
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault()
    const body: Record<string, unknown> = {
      label,
      description: description.trim() || null,
      required,
    }
    if (hasChoices) {
      body.options = [
        ...options.map((o) => ({ id: o.id, label: o.label, active: o.active })),
        ...(newOption.trim() ? [{ label: newOption.trim() }] : []),
      ]
    }
    if (type !== field.type) body.type = type
    update.mutate({ field, ...body }, { onSuccess: onDone })
  }

  return (
    <form className="item-form cf-edit" onSubmit={submit}>
      <div className="field item-form__name">
        <label htmlFor={`cf-edit-${field.id}`}>Nom du champ</label>
        <input
          id={`cf-edit-${field.id}`}
          required
          maxLength={120}
          value={label}
          onChange={(e) => setLabel(e.target.value)}
        />
        <p className="field__hint">
          Identifiant technique : <code>{field.key}</code> (il ne change jamais, les valeurs sont
          gardées).
        </p>
      </div>
      {field.type !== 'computed' && (
        <div className="field">
          <label htmlFor={`cf-type-${field.id}`}>Type</label>
          <select
            id={`cf-type-${field.id}`}
            value={type}
            onChange={(e) => void checkType(e.target.value as CustomFieldType)}
          >
            {Object.entries(FIELD_TYPES)
              .filter(([value]) => value !== 'computed')
              .map(([value, text]) => (
                <option key={value} value={value}>
                  {text}
                </option>
              ))}
          </select>
        </div>
      )}
      {preview && (
        <Alert tone={preview.blocked ? 'danger' : 'info'}>
          {preview.total === 0
            ? 'Aucune valeur enregistrée : le changement est sans effet sur les données.'
            : `${preview.convertible} valeur(s) sur ${preview.total} seront converties.`}
          {preview.blocked > 0 &&
            ` ${preview.blocked} ne peuvent pas l’être : le changement sera refusé tant qu’elles ne sont pas corrigées (rien n’est effacé).`}
          {preview.examples.length > 0 && (
            <ul className="cf-examples">
              {preview.examples.map((ex, i) => (
                <li key={i}>
                  « {ex.before} » → {ex.after ? `« ${ex.after} »` : 'non convertible'}
                </li>
              ))}
            </ul>
          )}
        </Alert>
      )}
      {previewError && <Alert>{previewError}</Alert>}
      {hasChoices && (
        <fieldset className="cf-options">
          <legend>Choix proposés</legend>
          {options.map((o, i) => (
            <div key={o.id} className="cf-options__row">
              <label className="visually-hidden" htmlFor={`opt-${o.id}`}>
                Libellé du choix
              </label>
              <input
                id={`opt-${o.id}`}
                required
                maxLength={120}
                value={o.label}
                onChange={(e) =>
                  setOptions((all) =>
                    all.map((x, j) => (j === i ? { ...x, label: e.target.value } : x)),
                  )
                }
              />
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={o.active}
                  onChange={(e) =>
                    setOptions((all) =>
                      all.map((x, j) => (j === i ? { ...x, active: e.target.checked } : x)),
                    )
                  }
                />
                Proposé
              </label>
            </div>
          ))}
          <label className="visually-hidden" htmlFor={`opt-new-${field.id}`}>
            Nouveau choix
          </label>
          <input
            id={`opt-new-${field.id}`}
            maxLength={120}
            placeholder="+ Nouveau choix"
            value={newOption}
            onChange={(e) => setNewOption(e.target.value)}
          />
          <p className="field__hint">
            Un choix décoché n’est plus proposé, mais reste affiché là où il était choisi.
          </p>
        </fieldset>
      )}
      <div className="field item-form__name">
        <label htmlFor={`cf-desc-${field.id}`}>Description</label>
        <input
          id={`cf-desc-${field.id}`}
          maxLength={1000}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
      </div>
      {field.type !== 'computed' && (
        <label className="field field--check">
          <input
            type="checkbox"
            checked={required}
            onChange={(e) => setRequired(e.target.checked)}
          />
          À compléter obligatoirement
        </label>
      )}
      {update.isError && <Alert>{errorMessage(update.error)}</Alert>}
      <div className="item-form__actions">
        <button
          className="button button--primary"
          disabled={update.isPending || Boolean(preview?.blocked)}
        >
          Enregistrer
        </button>
        <button type="button" className="button button--ghost" onClick={onDone}>
          Annuler
        </button>
      </div>
    </form>
  )
}

function describe(field: CustomField, fields: CustomField[], projects: Project[]) {
  const parts = [FIELD_TYPES[field.type], field.target === 'task' ? 'tâches' : 'projets']
  if (field.project_id) {
    parts.push(
      `seulement « ${projects.find((p) => p.id === field.project_id)?.title ?? 'projet'} »`,
    )
  }
  if (field.type === 'amount') parts.push(String(field.config.currency ?? ''))
  if (field.type === 'computed') {
    const f = field.config.formula as { op: keyof typeof OPS; a: string; b: string } | undefined
    const name = (id?: string) => fields.find((x) => x.id === id)?.label ?? '?'
    if (f) parts.push(OPS[f.op].replace('A', name(f.a)).replace('B', name(f.b)))
  }
  if (field.required) parts.push('obligatoire')
  parts.push(`${field.values_count} valeur(s)`)
  return parts.join(' · ')
}

/** Paramètres → Champs personnalisés (propriétaires, mode complet). */
export function CustomFieldsSettings({ spaceId }: { spaceId: string }) {
  const fieldsQuery = useCustomFields(spaceId)
  const projects = useProjects(spaceId).data ?? []
  const archive = useArchiveField(spaceId)
  const reorder = useReorderFields(spaceId)
  const [adding, setAdding] = useState(false)
  const [editing, setEditing] = useState<string | null>(null)
  const [showArchived, setShowArchived] = useState(false)
  const fields = useMemo(() => fieldsQuery.data ?? [], [fieldsQuery.data])
  const shown = fields.filter((f) => showArchived || !f.archived)

  function move(index: number, delta: number) {
    const ids = fields.map((f) => f.id)
    const [item] = ids.splice(index, 1)
    ids.splice(index + delta, 0, item)
    reorder.mutate(ids)
  }

  return (
    <section className="card-panel" aria-labelledby="title-custom-fields">
      <div className="card-panel__head">
        <div>
          <h2 id="title-custom-fields">Champs personnalisés</h2>
          <p className="card-panel__help">
            Ajoutez aux projets et aux tâches les informations propres à votre organisation :
            budget, type de risque, capacité vérifiée… Renommer un champ ou un choix garde les
            valeurs ; un champ n’est jamais supprimé, il est archivé.
          </p>
        </div>
        {!adding && (
          <button type="button" className="button button--small" onClick={() => setAdding(true)}>
            + Champ
          </button>
        )}
      </div>
      {adding && (
        <FieldForm
          spaceId={spaceId}
          fields={fields}
          projects={projects}
          onDone={() => setAdding(false)}
        />
      )}
      {fieldsQuery.isError && <Alert>{errorMessage(fieldsQuery.error)}</Alert>}
      {archive.isError && <Alert>{errorMessage(archive.error)}</Alert>}
      {shown.length === 0 && !adding ? (
        <p className="muted">Aucun champ personnalisé pour l’instant.</p>
      ) : (
        <ul className="item-list">
          {shown.map((f) => {
            const index = fields.indexOf(f)
            if (editing === f.id) {
              return (
                <li key={f.id} className="item-row item-row--editing">
                  <FieldEditor spaceId={spaceId} field={f} onDone={() => setEditing(null)} />
                </li>
              )
            }
            return (
              <li key={f.id} className="item-row">
                <span className="item-row__text">
                  <span className="item-row__name">
                    {f.label} {f.archived && <StatusPill tone="neutral">Archivé</StatusPill>}
                  </span>
                  <span className="item-row__details">{describe(f, fields, projects)}</span>
                </span>
                <span className="item-row__actions">
                  {!f.archived && (
                    <>
                      <button
                        type="button"
                        className="button button--small button--ghost"
                        aria-label={`Monter ${f.label}`}
                        disabled={index === 0 || reorder.isPending}
                        onClick={() => move(index, -1)}
                      >
                        ↑
                      </button>
                      <button
                        type="button"
                        className="button button--small button--ghost"
                        aria-label={`Descendre ${f.label}`}
                        disabled={index === fields.length - 1 || reorder.isPending}
                        onClick={() => move(index, 1)}
                      >
                        ↓
                      </button>
                      <button
                        type="button"
                        className="button button--small"
                        onClick={() => setEditing(f.id)}
                      >
                        Modifier
                      </button>
                    </>
                  )}
                  <button
                    type="button"
                    className="button button--small"
                    disabled={archive.isPending}
                    onClick={() => archive.mutate({ id: f.id, restore: f.archived })}
                  >
                    {f.archived ? 'Restaurer' : 'Archiver'}
                  </button>
                </span>
              </li>
            )
          })}
        </ul>
      )}
      {fields.some((f) => f.archived) && (
        <label className="checkbox">
          <input
            type="checkbox"
            checked={showArchived}
            onChange={(e) => setShowArchived(e.target.checked)}
          />
          Afficher les champs archivés
        </label>
      )}
    </section>
  )
}
