import { useRef, useState, type FormEvent } from 'react'
import { Link, useOutletContext } from 'react-router'
import {
  errorMessage,
  type Project,
  type Proposal,
  type UpdateRequest,
  type UpdateSource,
  canWriteSpace,
} from '../api/client'
import {
  sourceDownloadUrl,
  useApplyProposal,
  useChooseProposalTarget,
  useDiscardProposal,
  useProjects,
  useRefreshProposal,
  useSendUpdate,
  useSetUpdateVisibility,
  useShareSource,
  useUpdates,
} from '../api/queries'
import { FileBadge } from '../components/documents'
import { InboxIcon } from '../components/icons'
import { Alert, PageHeader, StatusPill, type Tone, Skeleton } from '../components/ui'
import { formatSize, MAX_FILES_PER_UPLOAD, MAX_UPLOAD_BYTES } from '../files'
import { formatMoment } from '../labels'
import type { SpaceContext } from './space-layout'

const ACCEPT = '.pdf,.docx,.xlsx,.pptx,.txt,.csv,.md,image/*'

const STATE: Record<string, { label: string; tone: Tone }> = {
  to_clarify: { label: 'À préciser', tone: 'warn' },
  to_validate: { label: 'À valider', tone: 'info' },
  conflict: { label: 'En conflit', tone: 'danger' },
  applied: { label: 'Appliquée', tone: 'ok' },
  discarded: { label: 'Écartée', tone: 'neutral' },
}
const OPEN = new Set(['to_clarify', 'to_validate', 'conflict'])

const EXTRACTION: Record<string, { label: string; tone: Tone }> = {
  read: { label: 'Lu', tone: 'ok' },
  empty: { label: 'Sans texte', tone: 'warn' },
  unsupported: { label: 'Non lu', tone: 'warn' },
  too_large: { label: 'Trop lourd', tone: 'warn' },
  too_long: { label: 'Trop long', tone: 'warn' },
  failed: { label: 'Illisible', tone: 'danger' },
}

function newRequestId() {
  return crypto.randomUUID()
}

function plural(n: number, word: string) {
  return `${n} ${word}${n > 1 ? 's' : ''}`
}

// ---------- Saisie ----------

function Composer({ spaceId, onSent }: { spaceId: string; onSent: (r: UpdateRequest) => void }) {
  const send = useSendUpdate(spaceId)
  const [message, setMessage] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const [visibility, setVisibility] = useState<'private' | 'shared'>('private')
  const [requestId, setRequestId] = useState(newRequestId)
  const [fileError, setFileError] = useState<string | null>(null)
  const input = useRef<HTMLInputElement>(null)

  function addFiles(list: FileList | null) {
    const picked = [...files, ...Array.from(list ?? [])]
    const tooBig = picked.find((f) => f.size > MAX_UPLOAD_BYTES)
    if (picked.length > MAX_FILES_PER_UPLOAD) {
      setFileError(`${MAX_FILES_PER_UPLOAD} fichiers au maximum par demande.`)
    } else if (tooBig) {
      setFileError(`« ${tooBig.name} » dépasse ${formatSize(MAX_UPLOAD_BYTES)}.`)
    } else {
      setFileError(null)
      setFiles(picked)
    }
    if (input.current) input.current.value = ''
  }

  function submit(e: FormEvent) {
    e.preventDefault()
    send.mutate(
      { message, files, visibility, clientRequestId: requestId },
      {
        onSuccess: (request) => {
          setMessage('')
          setFiles([])
          setRequestId(newRequestId())
          onSent(request)
        },
      },
    )
  }

  const empty = !message.trim() && files.length === 0
  return (
    <form className="card-panel upd-composer" onSubmit={submit} aria-labelledby="composer-title">
      <div className="card-panel__head">
        <div>
          <h2 id="composer-title">Nouvelle mise à jour</h2>
          <p className="card-panel__help">
            Écrivez ou collez un compte rendu, ou déposez un document. Inutile de choisir le projet
            : PILOT le reconnaît. Rien ne change avant votre validation.
          </p>
        </div>
      </div>

      <div className="field">
        <label htmlFor="upd-message">Message</label>
        <textarea
          id="upd-message"
          rows={6}
          maxLength={30000}
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder={
            'Exemple :\nProjet Atlas — Statut : en cours. Prochaine étape : valider le budget.\nProjet Orion — Blocage : devis fournisseur manquant.'
          }
        />
      </div>

      <div className="upd-composer__row">
        <div className="upd-files">
          <input
            ref={input}
            id="upd-files"
            className="visually-hidden"
            type="file"
            multiple
            accept={ACCEPT}
            onChange={(e) => addFiles(e.target.files)}
          />
          <label htmlFor="upd-files" className="button button--small">
            Joindre des fichiers
          </label>
          <span className="field__hint">
            PDF, Word, Excel, PowerPoint, TXT, CSV · {MAX_FILES_PER_UPLOAD} fichiers de{' '}
            {formatSize(MAX_UPLOAD_BYTES)} au plus
          </span>
        </div>
        <fieldset className="upd-visibility">
          <legend className="visually-hidden">Visibilité</legend>
          <div className="segmented" role="radiogroup" aria-label="Visibilité de la demande">
            {(['private', 'shared'] as const).map((value) => (
              <button
                key={value}
                type="button"
                role="radio"
                aria-checked={visibility === value}
                className={
                  visibility === value ? 'segmented__item segmented__item--on' : 'segmented__item'
                }
                onClick={() => setVisibility(value)}
              >
                {value === 'private' ? 'Privée' : 'Partagée'}
              </button>
            ))}
          </div>
          <span className="field__hint">
            {visibility === 'private'
              ? 'Visible de vous seul.'
              : 'Visible des contributeurs et de la propriétaire.'}
          </span>
        </fieldset>
      </div>

      {files.length > 0 && (
        <ul className="upd-file-list">
          {files.map((file, i) => (
            <li key={`${file.name}-${i}`}>
              <FileBadge filename={file.name} />
              <span className="upd-file-list__name">{file.name}</span>
              <span className="muted">{formatSize(file.size)}</span>
              <button
                type="button"
                className="button button--small"
                aria-label={`Retirer ${file.name}`}
                onClick={() => setFiles(files.filter((_, j) => j !== i))}
              >
                Retirer
              </button>
            </li>
          ))}
        </ul>
      )}
      {fileError && <Alert tone="warn">{fileError}</Alert>}
      {send.isError && <Alert>{errorMessage(send.error)}</Alert>}

      <div className="form-actions upd-composer__actions">
        <details className="rules">
          <summary>Ce que PILOT sait lire</summary>
          <div className="rules__body">
            <ul>
              <li>
                Un <strong>nom de projet</strong> en début de ligne : « Atlas — … », « Projet Atlas
                : … », ou le nom du fichier.
              </li>
              <li>
                <strong>Statut</strong>, <strong>Avancement</strong> (en %),{' '}
                <strong>Échéance</strong> (date complète), <strong>Responsable</strong>,{' '}
                <strong>Situation</strong>, <strong>Prochaine étape</strong>,{' '}
                <strong>Décision</strong>, <strong>Blocage</strong>, <strong>Vigilance</strong>.
              </li>
              <li>Un tableau Excel ou CSV avec une colonne « Projet ».</li>
              <li>
                Par prudence : pas de date relative (« vendredi »), pas de « % de l’objectif » comme
                avancement, jamais « Terminé » sans bilan. En cas de doute, PILOT demande.
              </li>
            </ul>
          </div>
        </details>
        <button className="button button--primary" type="submit" disabled={empty || send.isPending}>
          {send.isPending ? 'Analyse…' : 'Analyser'}
        </button>
      </div>
    </form>
  )
}

// ---------- Résumé de fin de parcours (CDC §22) ----------

function Summary({ request }: { request: UpdateRequest }) {
  const proposals = request.proposals
  const toClarify = proposals.filter((p) => p.state === 'to_clarify').length
  const toValidate = proposals.filter((p) => p.state === 'to_validate').length
  const applied = proposals.filter((p) => p.state === 'applied').length
  const unread = request.sources.filter((s) => s.extraction !== 'read').length
  const received = [
    request.message ? 'votre message' : null,
    request.sources.length ? plural(request.sources.length, 'fichier') : null,
  ]
    .filter(Boolean)
    .join(' et ')
  const uncertain = toClarify + request.notes.length + unread
  return (
    <section className="card-panel upd-summary" aria-labelledby="summary-title">
      <h2 id="summary-title" className="visually-hidden">
        Résultat de l’analyse
      </h2>
      <dl className="upd-summary__grid">
        <div>
          <dt>Reçu</dt>
          <dd>{received.charAt(0).toUpperCase() + received.slice(1)}.</dd>
        </div>
        <div>
          <dt>Compris</dt>
          <dd>
            {proposals.length
              ? `${plural(proposals.length, 'proposition')} : ${toValidate} à valider${toClarify ? `, ${toClarify} à préciser` : ''}.`
              : 'Aucune modification reconnue.'}
          </dd>
        </div>
        <div>
          <dt>Incertain</dt>
          <dd>
            {uncertain
              ? `${plural(uncertain, 'point')} à vérifier, détaillé${uncertain > 1 ? 's' : ''} ci-dessous.`
              : 'Rien.'}
          </dd>
        </div>
        <div>
          <dt>Changé</dt>
          <dd>
            {applied
              ? `${plural(applied, 'proposition')} appliquée${applied > 1 ? 's' : ''}.`
              : 'Rien pour l’instant : aucune modification n’est appliquée avant votre validation.'}
          </dd>
        </div>
      </dl>
    </section>
  )
}

// ---------- Proposition ----------

function TargetPicker({
  proposal,
  spaceId,
  projects,
}: {
  proposal: Proposal
  spaceId: string
  projects: Project[]
}) {
  const choose = useChooseProposalTarget(spaceId)
  const [other, setOther] = useState('')
  return (
    <div className="upd-target">
      {proposal.candidates.length > 0 && (
        <div className="upd-target__candidates">
          <span className="muted">Projets possibles :</span>
          {proposal.candidates.map((c) => (
            <button
              key={c.id}
              type="button"
              className="button button--small"
              disabled={choose.isPending}
              onClick={() => choose.mutate({ id: proposal.id, projectId: c.id })}
            >
              {c.title}
              {c.detail && <span className="muted"> · {c.detail}</span>}
            </button>
          ))}
        </div>
      )}
      <div className="upd-target__other">
        <label className="visually-hidden" htmlFor={`target-${proposal.id}`}>
          Choisir un autre projet
        </label>
        <select
          id={`target-${proposal.id}`}
          value={other}
          onChange={(e) => setOther(e.target.value)}
        >
          <option value="">
            {proposal.candidates.length ? 'Autre projet…' : 'Choisir le projet…'}
          </option>
          {projects.map((p) => (
            <option key={p.id} value={p.id}>
              {p.title}
            </option>
          ))}
        </select>
        <button
          type="button"
          className="button button--small"
          disabled={!other || choose.isPending}
          onClick={() => choose.mutate({ id: proposal.id, projectId: other })}
        >
          Choisir
        </button>
      </div>
      {choose.isError && <Alert>{errorMessage(choose.error)}</Alert>}
    </div>
  )
}

function ProposalCard({
  proposal,
  spaceId,
  projects,
}: {
  proposal: Proposal
  spaceId: string
  projects: Project[]
}) {
  const apply = useApplyProposal(spaceId)
  const discard = useDiscardProposal(spaceId)
  const refresh = useRefreshProposal(spaceId)
  const editable = proposal.state === 'to_validate'
  const selectable = proposal.changes.filter((c) => !c.unchanged).map((c) => c.field)
  const [unchecked, setUnchecked] = useState<string[]>([])
  const [discarding, setDiscarding] = useState(false)
  const [reason, setReason] = useState('')
  const selected = selectable.filter((f) => !unchecked.includes(f))
  const state = STATE[proposal.state] ?? STATE.to_validate
  const labels = Object.fromEntries(proposal.changes.map((c) => [c.field, c.label]))
  const error = apply.error ?? discard.error ?? refresh.error

  return (
    <article className={`proposal proposal--${proposal.state}`}>
      <header className="proposal__head">
        <div className="proposal__title">
          {proposal.project ? (
            <Link to={`/espaces/${spaceId}/projets/${proposal.project.id}`}>
              {proposal.project.title}
            </Link>
          ) : (
            <span>Projet à préciser</span>
          )}
          <span className="proposal__source">Source : {proposal.source_label}</span>
        </div>
        <StatusPill tone={state.tone}>{state.label}</StatusPill>
      </header>

      {proposal.state === 'to_clarify' && (
        <TargetPicker proposal={proposal} spaceId={spaceId} projects={projects} />
      )}

      {proposal.state === 'conflict' && (
        <Alert tone="warn">
          Le projet a été modifié depuis la préparation de cette proposition. Votre texte est
          conservé : recalculez-la sur la version actuelle avant de valider.{' '}
          <button
            type="button"
            className="button button--small"
            disabled={refresh.isPending}
            onClick={() => refresh.mutate(proposal.id)}
          >
            Recalculer
          </button>
        </Alert>
      )}

      <div className="table-scroll">
        <table className="table upd-changes">
          <thead>
            <tr>
              {editable && (
                <th scope="col" className="upd-changes__check">
                  <span className="visually-hidden">Appliquer</span>
                </th>
              )}
              <th scope="col">Champ</th>
              <th scope="col">{proposal.state === 'applied' ? 'Avant' : 'Actuellement'}</th>
              <th scope="col">Proposé</th>
            </tr>
          </thead>
          <tbody>
            {proposal.changes.map((change) => {
              const id = `chg-${proposal.id}-${change.field}`
              const done = proposal.applied_fields.includes(change.field)
              return (
                <tr key={change.field} className={change.unchanged ? 'upd-changes__same' : ''}>
                  {editable && (
                    <td className="upd-changes__check">
                      <input
                        id={id}
                        type="checkbox"
                        disabled={change.unchanged}
                        checked={!change.unchanged && !unchecked.includes(change.field)}
                        onChange={(e) =>
                          setUnchecked(
                            e.target.checked
                              ? unchecked.filter((f) => f !== change.field)
                              : [...unchecked, change.field],
                          )
                        }
                      />
                    </td>
                  )}
                  <th scope="row">
                    <label htmlFor={editable ? id : undefined}>{change.label}</label>
                  </th>
                  <td className="upd-changes__current">
                    {change.current ?? (proposal.project ? <em>vide</em> : '—')}
                  </td>
                  <td className="upd-changes__proposed">
                    {change.proposed}
                    {change.unchanged && <span className="muted"> · déjà à jour</span>}
                    {proposal.state === 'applied' && !done && (
                      <span className="muted"> · non appliqué</span>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {proposal.issues.length > 0 && (
        <ul className="upd-issues">
          {proposal.issues.map((issue) => (
            <li key={issue}>{issue}</li>
          ))}
        </ul>
      )}

      <details className="upd-excerpt">
        <summary>Passage source</summary>
        <blockquote>{proposal.excerpt}</blockquote>
      </details>

      {proposal.state === 'applied' && (
        <p className="proposal__outcome">
          Appliquée{proposal.decided_at && ` le ${formatMoment(proposal.decided_at)}`}
          {proposal.decided_by && ` par ${proposal.decided_by}`} :{' '}
          {proposal.applied_fields.length
            ? proposal.applied_fields.map((f) => labels[f] ?? f).join(', ')
            : 'le projet était déjà à jour, rien n’a changé'}
          .
        </p>
      )}
      {proposal.state === 'discarded' && (
        <p className="proposal__outcome">
          Écartée{proposal.decided_at && ` le ${formatMoment(proposal.decided_at)}`}
          {proposal.decided_by && ` par ${proposal.decided_by}`}
          {proposal.discard_reason ? ` : ${proposal.discard_reason}` : ''}. Le projet n’a pas
          changé.
        </p>
      )}

      {OPEN.has(proposal.state) && (
        <div className="proposal__actions">
          {discarding ? (
            <>
              <label className="visually-hidden" htmlFor={`reason-${proposal.id}`}>
                Motif (facultatif)
              </label>
              <input
                id={`reason-${proposal.id}`}
                className="proposal__reason"
                placeholder="Motif (facultatif)"
                maxLength={300}
                value={reason}
                onChange={(e) => setReason(e.target.value)}
              />
              <button
                type="button"
                className="button button--small button--danger"
                disabled={discard.isPending}
                onClick={() => discard.mutate({ id: proposal.id, reason })}
              >
                Confirmer
              </button>
              <button
                type="button"
                className="button button--small"
                onClick={() => setDiscarding(false)}
              >
                Annuler
              </button>
            </>
          ) : (
            <button type="button" className="button" onClick={() => setDiscarding(true)}>
              Écarter
            </button>
          )}
          {editable && (
            <button
              type="button"
              className="button button--primary"
              disabled={selected.length === 0 || apply.isPending || discarding}
              onClick={() =>
                apply.mutate({
                  id: proposal.id,
                  fields: selected,
                  baseVersion: proposal.base_version ?? 0,
                })
              }
            >
              {apply.isPending
                ? 'Application…'
                : selected.length
                  ? `Appliquer ${plural(selected.length, 'modification')}`
                  : 'Rien à appliquer'}
            </button>
          )}
        </div>
      )}
      {error && <Alert>{errorMessage(error)}</Alert>}
    </article>
  )
}

// ---------- Demande ----------

function SourceRow({
  source,
  spaceId,
  projects,
}: {
  source: UpdateSource
  spaceId: string
  projects: Project[]
}) {
  const share = useShareSource(spaceId)
  const [sharing, setSharing] = useState(false)
  const [projectId, setProjectId] = useState('')
  const status = EXTRACTION[source.extraction] ?? EXTRACTION.failed
  return (
    <li className="doc-row upd-source">
      <FileBadge filename={source.filename} />
      <span className="doc-row__text">
        <span className="doc-row__name">{source.filename}</span>
        <span className="doc-row__meta">
          {formatSize(source.size_bytes)}
          {source.extraction === 'read'
            ? ` · ${source.chars.toLocaleString('fr-FR')} caractères lus`
            : source.note && ` · ${source.note}`}
        </span>
      </span>
      <StatusPill tone={status.tone}>{status.label}</StatusPill>
      <a className="button button--small" href={sourceDownloadUrl(spaceId, source.id)} download>
        Télécharger
      </a>
      {sharing ? (
        <span className="upd-source__share">
          <label className="visually-hidden" htmlFor={`share-${source.id}`}>
            Projet
          </label>
          <select
            id={`share-${source.id}`}
            value={projectId}
            onChange={(e) => setProjectId(e.target.value)}
          >
            <option value="">Projet…</option>
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.title}
              </option>
            ))}
          </select>
          <button
            type="button"
            className="button button--small button--primary"
            disabled={!projectId || share.isPending}
            onClick={() =>
              share.mutate(
                { sourceId: source.id, projectId },
                { onSuccess: () => setSharing(false) },
              )
            }
          >
            Ajouter
          </button>
        </span>
      ) : (
        <button type="button" className="button button--small" onClick={() => setSharing(true)}>
          Ajouter au dossier d’un projet
        </button>
      )}
      {share.isSuccess && !sharing && (
        <Alert tone="ok">Copié dans le dossier de « {share.data.project_title} ».</Alert>
      )}
      {share.isError && <Alert>{errorMessage(share.error)}</Alert>}
    </li>
  )
}

function RequestCard({
  request,
  spaceId,
  projects,
}: {
  request: UpdateRequest
  spaceId: string
  projects: Project[]
}) {
  const setVisibility = useSetUpdateVisibility(spaceId)
  const shared = request.visibility === 'shared'
  return (
    <section
      className="card-panel upd-request"
      aria-label={`Demande du ${formatMoment(request.created_at)}`}
    >
      <div className="upd-request__head">
        <div>
          <h2 className="upd-request__title">
            {formatMoment(request.created_at)}
            {!request.mine && request.author_name && (
              <span className="muted"> · {request.author_name}</span>
            )}
          </h2>
          <span className="muted upd-request__meta">
            {plural(request.proposals.length, 'proposition')}
            {request.sources.length > 0 && ` · ${plural(request.sources.length, 'fichier')}`}
          </span>
        </div>
        <div className="upd-request__tools">
          <StatusPill tone={shared ? 'violet' : 'neutral'}>
            {shared ? 'Partagée' : 'Privée'}
          </StatusPill>
          {request.mine && (
            <button
              type="button"
              className="button button--small"
              disabled={setVisibility.isPending}
              onClick={() =>
                setVisibility.mutate({ id: request.id, visibility: shared ? 'private' : 'shared' })
              }
            >
              {shared ? 'Rendre privée' : 'Partager'}
            </button>
          )}
        </div>
      </div>

      {request.message && (
        <details className="upd-excerpt">
          <summary>Message déposé</summary>
          <blockquote>{request.message}</blockquote>
        </details>
      )}
      {request.sources.length > 0 && (
        <ul className="doc-list">
          {request.sources.map((s) => (
            <SourceRow key={s.id} source={s} spaceId={spaceId} projects={projects} />
          ))}
        </ul>
      )}
      {request.notes.length > 0 && (
        <div className="upd-notes">
          <strong>À noter</strong>
          <ul>
            {request.notes.map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
        </div>
      )}
      {request.proposals.map((p) => (
        <ProposalCard key={p.id} proposal={p} spaceId={spaceId} projects={projects} />
      ))}
      {setVisibility.isError && <Alert>{errorMessage(setVisibility.error)}</Alert>}
    </section>
  )
}

// ---------- Page ----------

export function UpdatesPage() {
  const { space } = useOutletContext<SpaceContext>()
  const canWrite = canWriteSpace(space.role)
  const updates = useUpdates(space.id, canWrite)
  const projects = useProjects(space.id)
  const [filter, setFilter] = useState<'todo' | 'all'>('todo')
  const [lastId, setLastId] = useState<string | null>(null)

  if (!canWrite) {
    return (
      <div className="page-content page-content--narrow">
        <PageHeader title="Mises à jour" />
        <Alert tone="info">
          Votre rôle de lecteur ne permet pas de proposer des mises à jour. Demandez à la
          propriétaire de l’espace de vous passer contributeur.
        </Alert>
      </div>
    )
  }

  const all = updates.data ?? []
  const last = all.find((r) => r.id === lastId)
  const pending = all.filter((r) => r.proposals.some((p) => OPEN.has(p.state)))
  const shown = filter === 'todo' ? all.filter((r) => r.id === lastId || pending.includes(r)) : all
  const projectList = (projects.data ?? []).filter(
    (p) => p.status !== 'cancelled' && p.status !== 'done',
  )

  return (
    <div className="page-content">
      <PageHeader
        title="Mises à jour"
        subtitle="Collez un compte rendu ou déposez un document : PILOT prépare les changements, vous les validez."
      />
      <Composer spaceId={space.id} onSent={(request) => setLastId(request.id)} />
      {last && <Summary request={last} />}

      <div className="upd-list__head">
        <h2>Demandes</h2>
        <div className="segmented" role="group" aria-label="Filtrer les demandes">
          <button
            type="button"
            aria-pressed={filter === 'todo'}
            className={
              filter === 'todo' ? 'segmented__item segmented__item--on' : 'segmented__item'
            }
            onClick={() => setFilter('todo')}
          >
            À traiter · {pending.length}
          </button>
          <button
            type="button"
            aria-pressed={filter === 'all'}
            className={filter === 'all' ? 'segmented__item segmented__item--on' : 'segmented__item'}
            onClick={() => setFilter('all')}
          >
            Toutes · {all.length}
          </button>
        </div>
      </div>

      {updates.isPending && <Skeleton />}
      {updates.isError && <Alert>{errorMessage(updates.error)}</Alert>}
      {!updates.isPending && shown.length === 0 && (
        <div className="card-panel">
          <div className="mini-empty">
            <span className="icon-tile icon-tile--neutral">
              <InboxIcon />
            </span>
            <p>
              <strong>
                {filter === 'todo' ? 'Rien à traiter.' : 'Aucune demande pour l’instant.'}
              </strong>{' '}
              Les propositions préparées à partir de vos messages et documents apparaîtront ici.
            </p>
          </div>
        </div>
      )}
      {shown.map((request) => (
        <RequestCard key={request.id} request={request} spaceId={space.id} projects={projectList} />
      ))}
    </div>
  )
}
