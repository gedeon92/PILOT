import { useState, type FormEvent } from 'react'
import { useOutletContext, useSearchParams } from 'react-router'
import { canWriteSpace, errorMessage, type Encounter, type Relation } from '../api/client'
import {
  useCloseEncounter,
  useEncounters,
  useMembers,
  useProjects,
  useRelations,
  useSaveEncounter,
  useSaveRelation,
} from '../api/queries'
import { PersonField, type PersonValue } from '../components/person-field'
import { Alert, PageHeader, Skeleton, StatusPill, type Tone } from '../components/ui'
import { formatDay, isClosedProject } from '../labels'
import { personValue } from '../person'
import type { SpaceContext } from './space-layout'

/** Étape F6 (cahier V2, REL01–REL04) : rencontres et relations. Une sollicitation est triée ;
 * un rendez-vous a son dossier (prêt 48 h avant) ; après la séance, il faut un compte rendu,
 * un responsable et une action suivante datée. PILOT ne touche à aucun agenda externe et le
 * CRM reste la référence du pipeline. */

const TRIAGE: Record<Encounter['triage'], string> = {
  to_triage: 'À trier',
  accept: 'Accepter',
  delegate: 'Déléguer',
  in_writing: 'Traiter par écrit',
  investigate: 'Instruire',
  refuse: 'Refuser',
}
const KIND: Record<Relation['kind'], string> = {
  partner: 'Partenaire',
  client: 'Client',
  institution: 'Institution',
  supplier: 'Fournisseur',
  other: 'Autre',
}
const POTENTIAL = { low: 'Faible', medium: 'Moyen', high: 'Fort' } as const
const DOSSIER: [string, string][] = [
  ['objective', 'Objectif en une phrase'],
  ['context', 'Contexte'],
  ['people', 'Interlocuteurs'],
  ['last_exchanges', 'Derniers échanges'],
  ['options', 'Options'],
  ['risks', 'Risques'],
  ['expected_decision', 'Décision attendue'],
  ['desired_follow_up', 'Suite souhaitée'],
]
const PARTNERSHIP: [string, string][] = [
  ['value_proposition', 'Proposition de valeur réciproque'],
  ['economic_model', 'Modèle économique'],
  ['risks', 'Risques'],
  ['legal_review', 'Instruction juridique'],
  ['financial_review', 'Instruction financière'],
  ['effort', 'Effort demandé'],
  ['our_obligations', 'Nos obligations'],
  ['their_obligations', 'Leurs obligations'],
]

function badge(e: Encounter): { label: string; tone: Tone } {
  if (e.closed_at) return { label: 'Clôturée', tone: 'neutral' }
  if (e.triage === 'to_triage') return { label: 'À trier', tone: 'info' }
  if (e.without_follow_up) return { label: 'Sans suite', tone: 'danger' }
  if (e.dossier_due) return { label: 'Dossier à préparer', tone: 'warn' }
  if (e.dossier_ready_at) return { label: 'Dossier prêt', tone: 'ok' }
  return { label: TRIAGE[e.triage], tone: 'violet' }
}

function NewEncounter({
  spaceId,
  relations,
  onDone,
}: {
  spaceId: string
  relations: Relation[]
  onDone: () => void
}) {
  const save = useSaveEncounter(spaceId)
  const projects = (useProjects(spaceId).data ?? []).filter((p) => !isClosedProject(p.status))
  const [d, setD] = useState({
    title: '',
    relation_id: '',
    project_id: '',
    starts_on: '',
    ends_on: '',
    is_trip: false,
    objective: '',
    expected_decision: '',
    priority_account: false,
    urgent: false,
    private: false,
  })
  const set = (patch: Partial<typeof d>) => setD((x) => ({ ...x, ...patch }))
  function submit(event: FormEvent) {
    event.preventDefault()
    save.mutate(
      {
        ...d,
        relation_id: d.relation_id || null,
        project_id: d.project_id || null,
        starts_on: d.starts_on || null,
        ends_on: d.ends_on || null,
        objective: d.objective.trim() || null,
        expected_decision: d.expected_decision.trim() || null,
      },
      { onSuccess: onDone },
    )
  }
  return (
    <form className="item-form" onSubmit={submit} aria-label="Nouvelle rencontre">
      <div className="field item-form__name">
        <label htmlFor="enc-title">Objet de la demande ou du rendez-vous</label>
        <input
          id="enc-title"
          required
          maxLength={200}
          value={d.title}
          onChange={(e) => set({ title: e.target.value })}
        />
      </div>
      <div className="field">
        <label htmlFor="enc-relation">Relation</label>
        <select
          id="enc-relation"
          value={d.relation_id}
          onChange={(e) => set({ relation_id: e.target.value })}
        >
          <option value="">—</option>
          {relations.map((r) => (
            <option key={r.id} value={r.id}>
              {r.name}
              {r.organization ? ` (${r.organization})` : ''}
            </option>
          ))}
        </select>
      </div>
      <div className="field">
        <label htmlFor="enc-project">Projet lié</label>
        <select
          id="enc-project"
          value={d.project_id}
          onChange={(e) => set({ project_id: e.target.value })}
        >
          <option value="">—</option>
          {projects.map((p) => (
            <option key={p.id} value={p.id}>
              {p.title}
            </option>
          ))}
        </select>
      </div>
      <div className="field">
        <label htmlFor="enc-start">Date</label>
        <input
          id="enc-start"
          type="date"
          value={d.starts_on}
          onChange={(e) => set({ starts_on: e.target.value })}
        />
      </div>
      <div className="field">
        <label htmlFor="enc-end">Fin (déplacement)</label>
        <input
          id="enc-end"
          type="date"
          value={d.ends_on}
          onChange={(e) => set({ ends_on: e.target.value })}
        />
      </div>
      <div className="field item-form__name">
        <label htmlFor="enc-objective">Objectif</label>
        <input
          id="enc-objective"
          maxLength={4000}
          value={d.objective}
          onChange={(e) => set({ objective: e.target.value })}
        />
      </div>
      <div className="field item-form__name">
        <label htmlFor="enc-decision">Décision attendue</label>
        <input
          id="enc-decision"
          maxLength={4000}
          value={d.expected_decision}
          onChange={(e) => set({ expected_decision: e.target.value })}
        />
      </div>
      <div className="enc-flags item-form__name">
        {(
          [
            ['is_trip', 'Déplacement (compte rendu sous 72 h)'],
            ['priority_account', 'Compte prioritaire'],
            ['urgent', 'Urgent'],
            ['private', 'Confidentiel'],
          ] as const
        ).map(([key, label]) => (
          <label key={key} className="checkbox">
            <input
              type="checkbox"
              checked={d[key]}
              onChange={(e) => set({ [key]: e.target.checked })}
            />
            {label}
          </label>
        ))}
      </div>
      {save.isError && <Alert>{errorMessage(save.error)}</Alert>}
      <div className="item-form__actions">
        <button className="button button--primary" disabled={save.isPending}>
          Enregistrer
        </button>
        <button type="button" className="button button--ghost" onClick={onDone}>
          Annuler
        </button>
      </div>
    </form>
  )
}

function EncounterCard({ spaceId, encounter: e }: { spaceId: string; encounter: Encounter }) {
  const save = useSaveEncounter(spaceId)
  const close = useCloseEncounter(spaceId)
  const members = useMembers(spaceId).data ?? []
  const [open, setOpen] = useState(false)
  const [triage, setTriage] = useState(e.triage)
  const [note, setNote] = useState(e.triage_note ?? '')
  const [dossier, setDossier] = useState<Record<string, string>>(
    Object.fromEntries(DOSSIER.map(([k]) => [k, String(e.dossier?.[k] ?? '')])),
  )
  const [report, setReport] = useState(e.report ?? '')
  const [owner, setOwner] = useState<PersonValue>(personValue(e.follow_owner))
  const [action, setAction] = useState(e.next_action ?? '')
  const [actionDate, setActionDate] = useState(e.next_action_date ?? '')
  const [reason, setReason] = useState('')
  const [closing, setClosing] = useState(false)
  const b = badge(e)
  const editable = e.can_write && !e.closed_at
  const id = `enc-${e.id}`
  const error = save.error ?? close.error

  return (
    <article className="occ" aria-labelledby={`${id}-title`}>
      <button
        type="button"
        className="occ__head"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="occ__time">{e.starts_on ? formatDay(e.starts_on) : '—'}</span>
        <span className="occ__main">
          <span className="occ__title" id={`${id}-title`}>
            {e.title}
          </span>
          <span className="occ__meta">
            {[
              e.relation?.name as string | undefined,
              e.project?.title as string | undefined,
              e.is_trip ? 'déplacement' : null,
              e.priority_account ? 'compte prioritaire' : null,
              e.urgent ? 'urgent' : null,
              e.private ? 'confidentiel' : null,
            ]
              .filter(Boolean)
              .join(' · ') || 'Sans relation liée'}
          </span>
        </span>
        <StatusPill tone={b.tone}>{b.label}</StatusPill>
      </button>
      {open && (
        <div className="occ__body">
          {e.objective && <p>Objectif : {e.objective}</p>}
          {e.expected_decision && <p>Décision attendue : {e.expected_decision}</p>}
          <fieldset className="enc-block" disabled={!editable}>
            <legend>1. Tri de la demande</legend>
            <div className="inline-form">
              <label htmlFor={`${id}-triage`}>Réponse</label>
              <select
                id={`${id}-triage`}
                value={triage}
                onChange={(ev) => setTriage(ev.target.value as Encounter['triage'])}
              >
                {Object.entries(TRIAGE).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
              <label htmlFor={`${id}-note`} className="visually-hidden">
                Note de tri
              </label>
              <input
                id={`${id}-note`}
                placeholder="À qui, ou pourquoi"
                value={note}
                onChange={(ev) => setNote(ev.target.value)}
              />
              <button
                type="button"
                className="button button--small"
                disabled={save.isPending}
                onClick={() =>
                  save.mutate({ encounter: e, triage, triage_note: note.trim() || null })
                }
              >
                Enregistrer
              </button>
            </div>
          </fieldset>
          {e.triage === 'accept' && (
            <fieldset className="enc-block" disabled={!editable}>
              <legend>
                2. Dossier de rendez-vous{' '}
                {e.dossier_ready_at ? '(prêt)' : '(à préparer 48 h avant)'}
              </legend>
              {DOSSIER.map(([key, label]) => (
                <div className="field" key={key}>
                  <label htmlFor={`${id}-${key}`}>{label}</label>
                  <input
                    id={`${id}-${key}`}
                    maxLength={4000}
                    value={dossier[key]}
                    onChange={(ev) => setDossier((x) => ({ ...x, [key]: ev.target.value }))}
                  />
                </div>
              ))}
              <div className="item-form__actions">
                <button
                  type="button"
                  className="button button--small"
                  disabled={save.isPending}
                  onClick={() => save.mutate({ encounter: e, dossier })}
                >
                  Enregistrer le dossier
                </button>
                <button
                  type="button"
                  className="button button--small button--primary"
                  disabled={save.isPending}
                  onClick={() =>
                    save.mutate({ encounter: e, dossier, dossier_ready: !e.dossier_ready_at })
                  }
                >
                  {e.dossier_ready_at ? 'Dossier à reprendre' : 'Marquer le dossier prêt'}
                </button>
              </div>
            </fieldset>
          )}
          {e.triage === 'accept' && (
            <fieldset className="enc-block" disabled={!editable}>
              <legend>
                3. Après la rencontre
                {e.report_due_on && ` (compte rendu attendu le ${formatDay(e.report_due_on)})`}
              </legend>
              <div className="field">
                <label htmlFor={`${id}-report`}>Compte rendu</label>
                <textarea
                  id={`${id}-report`}
                  rows={3}
                  value={report}
                  onChange={(ev) => setReport(ev.target.value)}
                />
              </div>
              <PersonField
                id={`${id}-owner`}
                label="Responsable de la suite"
                members={members}
                value={owner}
                onChange={setOwner}
              />
              <div className="field">
                <label htmlFor={`${id}-action`}>Action suivante</label>
                <input
                  id={`${id}-action`}
                  value={action}
                  onChange={(ev) => setAction(ev.target.value)}
                />
              </div>
              <div className="field">
                <label htmlFor={`${id}-action-date`}>Pour le</label>
                <input
                  id={`${id}-action-date`}
                  type="date"
                  value={actionDate}
                  onChange={(ev) => setActionDate(ev.target.value)}
                />
              </div>
              <button
                type="button"
                className="button button--small"
                disabled={save.isPending}
                onClick={() =>
                  save.mutate({
                    encounter: e,
                    report: report.trim() || null,
                    follow_owner_member_id: owner.memberId,
                    follow_owner_label: owner.memberId ? null : owner.label.trim() || null,
                    next_action: action.trim() || null,
                    next_action_date: actionDate || null,
                  })
                }
              >
                Enregistrer la suite
              </button>
            </fieldset>
          )}
          {e.close_reason && <p className="muted">Motif de clôture : {e.close_reason}</p>}
          {error && <Alert>{errorMessage(error)}</Alert>}
          {e.can_write && (
            <div className="occ__actions">
              {e.closed_at ? (
                <button
                  type="button"
                  className="button button--small button--ghost"
                  onClick={() => close.mutate({ encounter: e, reopen: true })}
                >
                  Rouvrir
                </button>
              ) : closing ? (
                <form
                  className="inline-form"
                  onSubmit={(ev) => {
                    ev.preventDefault()
                    close.mutate({ encounter: e, reason }, { onSuccess: () => setClosing(false) })
                  }}
                >
                  <label htmlFor={`${id}-reason`}>Motif (si pas de suite)</label>
                  <input
                    id={`${id}-reason`}
                    value={reason}
                    onChange={(ev) => setReason(ev.target.value)}
                  />
                  <button
                    className="button button--small button--primary"
                    disabled={close.isPending}
                  >
                    Clôturer
                  </button>
                  <button
                    type="button"
                    className="button button--small button--ghost"
                    onClick={() => setClosing(false)}
                  >
                    Annuler
                  </button>
                </form>
              ) : (
                <button
                  type="button"
                  className="button button--small"
                  onClick={() => setClosing(true)}
                >
                  Clôturer le dossier
                </button>
              )}
            </div>
          )}
        </div>
      )}
    </article>
  )
}

function RelationForm({
  spaceId,
  relation,
  onDone,
}: {
  spaceId: string
  relation?: Relation
  onDone: () => void
}) {
  const save = useSaveRelation(spaceId)
  const members = useMembers(spaceId).data ?? []
  const p = relation?.partnership ?? {}
  const [d, setD] = useState({
    name: relation?.name ?? '',
    organization: relation?.organization ?? '',
    kind: relation?.kind ?? 'partner',
    potential: relation?.potential ?? '',
    last_contact: relation?.last_contact ?? '',
    next_action: relation?.next_action ?? '',
    next_action_date: relation?.next_action_date ?? '',
    crm_ref: relation?.crm_ref ?? '',
    notes: relation?.notes ?? '',
    private: relation?.private ?? false,
    renewal_date: String(p.renewal_date ?? ''),
    ...Object.fromEntries(PARTNERSHIP.map(([k]) => [k, String(p[k] ?? '')])),
  } as Record<string, string | boolean>)
  const [owner, setOwner] = useState<PersonValue>(
    relation ? personValue(relation.owner) : { memberId: null, label: '' },
  )
  const set = (key: string, value: string | boolean) => setD((x) => ({ ...x, [key]: value }))
  const text = (key: string) => String(d[key] ?? '')

  function submit(event: FormEvent) {
    event.preventDefault()
    const partnership =
      d.kind === 'partner'
        ? {
            ...Object.fromEntries(PARTNERSHIP.map(([k]) => [k, text(k).trim() || null])),
            renewal_date: text('renewal_date') || null,
          }
        : null
    save.mutate(
      {
        relation,
        name: text('name'),
        organization: text('organization').trim() || null,
        kind: d.kind,
        potential: text('potential') || null,
        last_contact: text('last_contact') || null,
        next_action: text('next_action').trim() || null,
        next_action_date: text('next_action_date') || null,
        crm_ref: text('crm_ref').trim() || null,
        notes: text('notes').trim() || null,
        private: Boolean(d.private),
        owner_member_id: owner.memberId,
        owner_label: owner.memberId ? null : owner.label.trim() || null,
        partnership,
      },
      { onSuccess: onDone },
    )
  }
  const pid = relation ? `rel-${relation.id}` : 'rel-new'
  return (
    <form
      className="item-form"
      onSubmit={submit}
      aria-label={relation ? `Modifier ${relation.name}` : 'Nouvelle relation'}
    >
      <div className="field item-form__name">
        <label htmlFor={`${pid}-name`}>Personne ou relation</label>
        <input
          id={`${pid}-name`}
          required
          maxLength={200}
          value={text('name')}
          onChange={(e) => set('name', e.target.value)}
        />
      </div>
      <div className="field">
        <label htmlFor={`${pid}-org`}>Organisation</label>
        <input
          id={`${pid}-org`}
          maxLength={200}
          value={text('organization')}
          onChange={(e) => set('organization', e.target.value)}
        />
      </div>
      <div className="field">
        <label htmlFor={`${pid}-kind`}>Type</label>
        <select
          id={`${pid}-kind`}
          value={text('kind')}
          onChange={(e) => set('kind', e.target.value)}
        >
          {Object.entries(KIND).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </div>
      <div className="field">
        <label htmlFor={`${pid}-pot`}>Potentiel</label>
        <select
          id={`${pid}-pot`}
          value={text('potential')}
          onChange={(e) => set('potential', e.target.value)}
        >
          <option value="">—</option>
          {Object.entries(POTENTIAL).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </div>
      <div className="field">
        <label htmlFor={`${pid}-last`}>Dernier contact</label>
        <input
          id={`${pid}-last`}
          type="date"
          value={text('last_contact')}
          onChange={(e) => set('last_contact', e.target.value)}
        />
      </div>
      <div className="field">
        <label htmlFor={`${pid}-crm`}>Référence CRM</label>
        <input
          id={`${pid}-crm`}
          maxLength={200}
          value={text('crm_ref')}
          onChange={(e) => set('crm_ref', e.target.value)}
        />
      </div>
      <div className="field item-form__name">
        <label htmlFor={`${pid}-next`}>Prochaine action</label>
        <input
          id={`${pid}-next`}
          value={text('next_action')}
          onChange={(e) => set('next_action', e.target.value)}
        />
      </div>
      <div className="field">
        <label htmlFor={`${pid}-next-date`}>Pour le</label>
        <input
          id={`${pid}-next-date`}
          type="date"
          value={text('next_action_date')}
          onChange={(e) => set('next_action_date', e.target.value)}
        />
      </div>
      <div className="field item-form__name">
        <PersonField
          id={`${pid}-owner`}
          label="Responsable"
          members={members}
          value={owner}
          onChange={setOwner}
        />
      </div>
      {d.kind === 'partner' && (
        <fieldset className="enc-block item-form__name">
          <legend>Partenariat (la signature reste réservée au signataire habilité)</legend>
          {PARTNERSHIP.map(([key, label]) => (
            <div className="field" key={key}>
              <label htmlFor={`${pid}-${key}`}>{label}</label>
              <input
                id={`${pid}-${key}`}
                maxLength={4000}
                value={text(key)}
                onChange={(e) => set(key, e.target.value)}
              />
            </div>
          ))}
          <div className="field">
            <label htmlFor={`${pid}-renewal`}>Renouvellement</label>
            <input
              id={`${pid}-renewal`}
              type="date"
              value={text('renewal_date')}
              onChange={(e) => set('renewal_date', e.target.value)}
            />
          </div>
        </fieldset>
      )}
      <div className="field item-form__name">
        <label htmlFor={`${pid}-notes`}>Notes</label>
        <textarea
          id={`${pid}-notes`}
          rows={2}
          value={text('notes')}
          onChange={(e) => set('notes', e.target.value)}
        />
      </div>
      <label className="field field--check">
        <input
          type="checkbox"
          checked={Boolean(d.private)}
          onChange={(e) => set('private', e.target.checked)}
        />
        Confidentiel (visible des propriétaires, de l’auteur et du responsable)
      </label>
      {save.isError && <Alert>{errorMessage(save.error)}</Alert>}
      <div className="item-form__actions">
        <button className="button button--primary" disabled={save.isPending}>
          Enregistrer
        </button>
        <button type="button" className="button button--ghost" onClick={onDone}>
          Annuler
        </button>
      </div>
    </form>
  )
}

export function RelationsPage() {
  const { space } = useOutletContext<SpaceContext>()
  const [params, setParams] = useSearchParams()
  const view = params.get('vue') === 'relations' ? 'relations' : 'encounters'
  const encounters = useEncounters(space.id)
  const relations = useRelations(space.id)
  const canWrite = canWriteSpace(space.role)
  const [adding, setAdding] = useState(false)
  const [editing, setEditing] = useState<string | null>(null)
  const [showClosed, setShowClosed] = useState(false)
  const relationList = relations.data ?? []

  const tabs = (
    <div className="segmented" role="group" aria-label="Vue">
      {(
        [
          ['encounters', 'Rencontres'],
          ['relations', 'Relations'],
        ] as const
      ).map(([key, label]) => (
        <button
          key={key}
          type="button"
          className={view === key ? 'segmented__item segmented__item--on' : 'segmented__item'}
          aria-pressed={view === key}
          onClick={() => {
            setAdding(false)
            setParams(key === 'relations' ? { vue: 'relations' } : {}, { replace: true })
          }}
        >
          {label}
        </button>
      ))}
    </div>
  )
  const list = (encounters.data ?? []).filter((e) => showClosed || !e.closed_at)

  return (
    <div className="page-content">
      <PageHeader
        title={view === 'relations' ? 'Relations et partenariats' : 'Rencontres'}
        subtitle={
          view === 'relations'
            ? 'Personnes et organisations suivies : dernier contact, potentiel, prochaine action. Le CRM reste la référence.'
            : 'Sollicitations à trier, dossiers à préparer 48 h avant, comptes rendus et suites datées.'
        }
        actions={
          <>
            {tabs}
            {canWrite && !adding && (
              <button
                type="button"
                className="button button--primary"
                onClick={() => setAdding(true)}
              >
                {view === 'relations' ? 'Nouvelle relation' : 'Nouvelle rencontre'}
              </button>
            )}
          </>
        }
      />
      {adding && (
        <section className="card-panel">
          {view === 'relations' ? (
            <RelationForm spaceId={space.id} onDone={() => setAdding(false)} />
          ) : (
            <NewEncounter
              spaceId={space.id}
              relations={relationList}
              onDone={() => setAdding(false)}
            />
          )}
        </section>
      )}
      {view === 'encounters' ? (
        <section className="card-panel" aria-label="Rencontres">
          {encounters.isError && <Alert>{errorMessage(encounters.error)}</Alert>}
          {encounters.isPending ? (
            <Skeleton lines={4} />
          ) : list.length === 0 ? (
            <p className="muted">Aucune rencontre en cours.</p>
          ) : (
            <div className="occ-list">
              {list.map((e) => (
                <EncounterCard key={e.id} spaceId={space.id} encounter={e} />
              ))}
            </div>
          )}
          {(encounters.data ?? []).some((e) => e.closed_at) && (
            <label className="checkbox">
              <input
                type="checkbox"
                checked={showClosed}
                onChange={(e) => setShowClosed(e.target.checked)}
              />
              Afficher les rencontres clôturées
            </label>
          )}
        </section>
      ) : (
        <section className="card-panel" aria-label="Relations">
          {relations.isError && <Alert>{errorMessage(relations.error)}</Alert>}
          {relations.isPending ? (
            <Skeleton lines={4} />
          ) : relationList.length === 0 ? (
            <p className="muted">Aucune relation suivie pour l’instant.</p>
          ) : (
            <ul className="item-list">
              {relationList.map((r) =>
                editing === r.id ? (
                  <li key={r.id} className="item-row item-row--editing">
                    <RelationForm spaceId={space.id} relation={r} onDone={() => setEditing(null)} />
                  </li>
                ) : (
                  <li key={r.id} className="item-row">
                    <span className="item-row__text">
                      <span className="item-row__name">
                        {r.name} {r.private && <StatusPill tone="neutral">Confidentiel</StatusPill>}{' '}
                        {r.action_late && <StatusPill tone="danger">Action en retard</StatusPill>}
                      </span>
                      <span className="item-row__details">
                        {[
                          KIND[r.kind],
                          r.organization,
                          r.potential
                            ? `potentiel ${POTENTIAL[r.potential as keyof typeof POTENTIAL].toLowerCase()}`
                            : null,
                          r.last_contact
                            ? `dernier contact le ${formatDay(r.last_contact)}`
                            : 'aucun contact noté',
                          r.next_action
                            ? `prochaine action : ${r.next_action}${r.next_action_date ? ` (${formatDay(r.next_action_date)})` : ''}`
                            : null,
                          r.crm_ref ? `CRM ${r.crm_ref}` : null,
                          `${r.encounters} rencontre(s)`,
                        ]
                          .filter(Boolean)
                          .join(' · ')}
                      </span>
                    </span>
                    {r.can_write && (
                      <span className="item-row__actions">
                        <button
                          type="button"
                          className="button button--small"
                          onClick={() => setEditing(r.id)}
                        >
                          Modifier
                        </button>
                      </span>
                    )}
                  </li>
                ),
              )}
            </ul>
          )}
        </section>
      )}
    </div>
  )
}
