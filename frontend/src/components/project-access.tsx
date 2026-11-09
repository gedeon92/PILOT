import { useRef, useState } from 'react'
import { useModalPanel } from '../drawer'
import { errorMessage, ROLE_LABELS, type Member, type ProjectAccess } from '../api/client'
import { useMembers, useProjectAccess, useSetProjectAccess } from '../api/queries'
import { Avatar } from './avatar'
import { Alert, Skeleton } from './ui'

/** Panneau « Accès au projet » (lot C) : qui voit ce projet, avec quel rôle, et s'il est privé.
 * Les propriétaires de l'espace le modifient ; les autres le consultent. */

type ProjectRole = 'contributor' | 'reader'
type Draft = { private: boolean; members: { member_id: string; role: ProjectRole }[] }

const PROJECT_ROLES: Record<ProjectRole, string> = {
  contributor: 'Contributeur sur ce projet',
  reader: 'Lecteur sur ce projet',
}

function toDraft(access: ProjectAccess): Draft {
  return {
    private: access.private,
    members: access.members.map((m) => ({ member_id: m.member_id, role: m.role })),
  }
}

export function ProjectAccessDrawer({
  spaceId,
  projectId,
  isOwner,
  onClose,
}: {
  spaceId: string
  projectId: string
  isOwner: boolean
  onClose: () => void
}) {
  const access = useProjectAccess(spaceId, projectId)
  const members = useMembers(spaceId)
  // Gardé ici : l'éditeur se recrée après chaque enregistrement (nouvelles données du serveur).
  const [saved, setSaved] = useState(false)
  const panel = useRef<HTMLElement>(null)

  useModalPanel(panel)

  return (
    <div
      className="task-drawer-backdrop"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <aside
        ref={panel}
        className="task-drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="access-title"
        tabIndex={-1}
        onKeyDown={(e) => e.key === 'Escape' && onClose()}
      >
        <button
          type="button"
          className="icon-button task-drawer__close"
          aria-label="Fermer les accès"
          onClick={onClose}
        >
          ×
        </button>
        <h2 id="access-title" className="task-drawer__title">
          Accès au projet
        </h2>
        {(access.isPending || members.isPending) && <Skeleton />}
        {access.isError && <Alert>{errorMessage(access.error)}</Alert>}
        {access.data && members.data && (
          <AccessEditor
            key={JSON.stringify(toDraft(access.data))}
            spaceId={spaceId}
            projectId={projectId}
            access={access.data}
            members={members.data}
            isOwner={isOwner}
            saved={saved}
            onSaved={setSaved}
          />
        )}
      </aside>
    </div>
  )
}

function AccessEditor({
  spaceId,
  projectId,
  access,
  members,
  isOwner,
  saved,
  onSaved,
}: {
  spaceId: string
  projectId: string
  access: ProjectAccess
  members: Member[]
  isOwner: boolean
  saved: boolean
  onSaved: (saved: boolean) => void
}) {
  const save = useSetProjectAccess(spaceId, projectId)
  const [draft, setDraftState] = useState<Draft>(() => toDraft(access))
  const setDraft = (next: Draft) => {
    onSaved(false)
    setDraftState(next)
  }
  const [adding, setAdding] = useState('')
  const byId = new Map(members.map((m) => [m.id, m]))
  const owners = members.filter((m) => m.role === 'owner')
  const candidates = members.filter(
    (m) => m.role !== 'owner' && !draft.members.some((d) => d.member_id === m.id),
  )
  const changed = JSON.stringify(draft) !== JSON.stringify(toDraft(access))
  const name = (m: Member | undefined) => m?.display_name ?? m?.email ?? 'Membre'

  return (
    <div className="access">
      <section className="task-drawer__section">
        <h3>Qui voit ce projet ?</h3>
        <label className="access__choice">
          <input
            type="radio"
            name="visibility"
            checked={!draft.private}
            disabled={!isOwner}
            onChange={() => setDraft({ ...draft, private: false })}
          />
          <span>
            <strong>Tout l’espace</strong>
            <span className="task-drawer__hint">
              Chaque membre le voit avec son rôle dans l’espace (les invités extérieurs, seulement
              s’ils sont ajoutés ci-dessous).
            </span>
          </span>
        </label>
        <label className="access__choice">
          <input
            type="radio"
            name="visibility"
            checked={draft.private}
            disabled={!isOwner}
            onChange={() => setDraft({ ...draft, private: true })}
          />
          <span>
            <strong>🔒 Privé</strong>
            <span className="task-drawer__hint">
              Seulement les propriétaires de l’espace et les personnes ajoutées ci-dessous. Il
              n’apparaît nulle part ailleurs pour les autres (tableau de bord, timeline, recherche,
              alertes, documents).
            </span>
          </span>
        </label>
      </section>

      <section className="task-drawer__section">
        <h3>Personnes ajoutées à ce projet</h3>
        <p className="task-drawer__hint">
          Un rôle de projet remplace, pour ce projet seulement, le rôle dans l’espace. Les
          propriétaires ({owners.map((o) => name(o)).join(', ')}) ont toujours tous les droits.
        </p>
        {draft.members.length === 0 && <p className="muted">Personne pour l’instant.</p>}
        <ul className="access__list">
          {draft.members.map((entry) => {
            const member = byId.get(entry.member_id)
            return (
              <li key={entry.member_id} className="access__row">
                <Avatar name={name(member)} size="small" />
                <span className="access__who">
                  <strong>{name(member)}</strong>
                  <span className="task-drawer__hint">
                    {member ? `${ROLE_LABELS[member.role]} dans l’espace` : ''}
                    {member?.status === 'invited' ? ' · invitation en attente' : ''}
                  </span>
                </span>
                {isOwner ? (
                  <>
                    <select
                      aria-label={`Rôle de ${name(member)} sur ce projet`}
                      value={entry.role}
                      onChange={(e) =>
                        setDraft({
                          ...draft,
                          members: draft.members.map((d) =>
                            d.member_id === entry.member_id
                              ? { ...d, role: e.target.value as ProjectRole }
                              : d,
                          ),
                        })
                      }
                    >
                      <option value="contributor">{PROJECT_ROLES.contributor}</option>
                      <option value="reader">{PROJECT_ROLES.reader}</option>
                    </select>
                    <button
                      type="button"
                      className="icon-button"
                      aria-label={`Retirer ${name(member)} de ce projet`}
                      onClick={() =>
                        setDraft({
                          ...draft,
                          members: draft.members.filter((d) => d.member_id !== entry.member_id),
                        })
                      }
                    >
                      ×
                    </button>
                  </>
                ) : (
                  <span className="task-badge">{PROJECT_ROLES[entry.role]}</span>
                )}
              </li>
            )
          })}
        </ul>
        {isOwner && candidates.length > 0 && (
          <div className="inline-form">
            <label htmlFor="access-add" className="visually-hidden">
              Ajouter une personne
            </label>
            <select id="access-add" value={adding} onChange={(e) => setAdding(e.target.value)}>
              <option value="">Ajouter une personne de l’espace…</option>
              {candidates.map((m) => (
                <option key={m.id} value={m.id}>
                  {name(m)} · {ROLE_LABELS[m.role]}
                </option>
              ))}
            </select>
            <button
              type="button"
              className="button button--small"
              disabled={!adding}
              onClick={() => {
                const member = byId.get(adding)
                setDraft({
                  ...draft,
                  members: [
                    ...draft.members,
                    {
                      member_id: adding,
                      role: member?.role === 'reader' ? 'reader' : 'contributor',
                    },
                  ],
                })
                setAdding('')
              }}
            >
              Ajouter
            </button>
          </div>
        )}
        {isOwner && (
          <p className="task-drawer__hint">
            Pour une personne extérieure, invitez-la d’abord avec le rôle « Invité » dans Accès et
            membres, puis ajoutez-la ici.
          </p>
        )}
      </section>

      {save.isError && <Alert>{errorMessage(save.error)}</Alert>}
      {isOwner ? (
        <div className="form-actions">
          <button
            type="button"
            className="button button--primary"
            disabled={!changed || save.isPending}
            onClick={() => save.mutate(draft, { onSuccess: () => onSaved(true) })}
          >
            {save.isPending ? 'Enregistrement…' : 'Enregistrer les accès'}
          </button>
          {saved && !changed && (
            <span className="task-drawer__hint" role="status">
              ✓ Accès enregistrés.
            </span>
          )}
        </div>
      ) : (
        <p className="task-drawer__hint">
          Seuls les propriétaires de l’espace modifient les accès.
        </p>
      )}
    </div>
  )
}
