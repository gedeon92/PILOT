import { useState, type FormEvent } from 'react'
import { useOutletContext } from 'react-router'
import {
  errorMessage,
  ROLE_LABELS,
  type InvitationLink,
  type Member,
  type Role,
} from '../api/client'
import {
  useChangeRole,
  useInvite,
  useMembers,
  useRemoveMember,
  useRenewInvitation,
} from '../api/queries'
import { LinkIcon, PlusIcon } from '../components/icons'
import { Alert, PageHeader, StatusPill } from '../components/ui'
import type { SpaceContext } from './space-layout'

type InvitableRole = Exclude<Role, 'owner'>

const ROLE_HELP: Record<InvitableRole, string> = {
  reader: 'consulte les projets et les documents',
  contributor: 'consulte, ajoute et modifie les projets',
  guest:
    'personne extérieure (prestataire, partenaire) : ne voit que les projets auxquels vous l’ajoutez, depuis le bouton « Accès » de chaque projet',
}

const dateFormat = new Intl.DateTimeFormat('fr-FR', {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
})

function invitationUrl(token: string) {
  return `${window.location.origin}/invitation/${token}`
}

function LinkPanel({ link, onClose }: { link: InvitationLink; onClose: () => void }) {
  const url = invitationUrl(link.token)
  const [copied, setCopied] = useState(false)

  async function copy() {
    try {
      await navigator.clipboard.writeText(url)
      setCopied(true)
    } catch {
      setCopied(false)
    }
  }

  return (
    <section className="link-panel" aria-live="polite">
      <h2>
        <LinkIcon /> Invitation pour {link.member.email}
      </h2>
      {link.emailed ? (
        <p>
          ✉️ <strong>Invitation envoyée par e-mail à {link.member.email}.</strong> La personne n’a
          qu’à cliquer sur le bouton reçu. Si elle ne trouve pas l’e-mail (pensez aux courriers
          indésirables), vous pouvez aussi lui envoyer ce lien vous-même.
        </p>
      ) : (
        <p>
          {link.email_note && <strong>{link.email_note} </strong>}
          Envoyez ce lien à la personne.
        </p>
      )}
      <p className="field__hint">
        Le lien ne fonctionne qu’une fois, pendant 14 jours, et seulement avec un compte créé avec
        cette adresse. Il ne sera plus affiché ici ensuite.
      </p>
      <div className="link-panel__row">
        <input
          readOnly
          value={url}
          aria-label="Lien d’invitation"
          onFocus={(e) => e.target.select()}
        />
        <button type="button" className="button button--primary" onClick={copy}>
          {copied ? 'Copié ✓' : 'Copier'}
        </button>
      </div>
      <button type="button" className="button button--ghost" onClick={onClose}>
        Fermer
      </button>
    </section>
  )
}

function InviteForm({
  spaceId,
  onInvited,
}: {
  spaceId: string
  onInvited: (l: InvitationLink) => void
}) {
  const invite = useInvite(spaceId)
  const [email, setEmail] = useState('')
  const [role, setRole] = useState<InvitableRole>('contributor')

  function submit(event: FormEvent) {
    event.preventDefault()
    invite.mutate(
      { email, role },
      {
        onSuccess: (link) => {
          setEmail('')
          onInvited(link)
        },
      },
    )
  }

  return (
    <form className="invite-form" onSubmit={submit}>
      <div className="field invite-form__email">
        <label htmlFor="invite-email">Adresse e-mail</label>
        <input
          id="invite-email"
          type="email"
          required
          placeholder="nom@organisation.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
      </div>
      <div className="field">
        <label htmlFor="invite-role">Rôle</label>
        <select
          id="invite-role"
          value={role}
          onChange={(e) => setRole(e.target.value as InvitableRole)}
        >
          <option value="contributor">Contributeur</option>
          <option value="reader">Lecteur</option>
          <option value="guest">Invité (extérieur)</option>
        </select>
      </div>
      <button className="button button--primary" type="submit" disabled={invite.isPending}>
        <PlusIcon /> {invite.isPending ? 'Invitation…' : 'Inviter'}
      </button>
      <p className="field__hint invite-form__help">
        {ROLE_LABELS[role]} : {ROLE_HELP[role]}.
      </p>
      {invite.isError && <Alert>{errorMessage(invite.error)}</Alert>}
    </form>
  )
}

function MemberRow({
  member,
  spaceId,
  canManage,
  onLink,
}: {
  member: Member
  spaceId: string
  canManage: boolean
  onLink: (l: InvitationLink) => void
}) {
  const changeRole = useChangeRole(spaceId)
  const remove = useRemoveMember(spaceId)
  const renew = useRenewInvitation(spaceId)
  const [confirming, setConfirming] = useState(false)
  const editable = canManage && member.role !== 'owner'
  const error = changeRole.error ?? remove.error ?? renew.error
  const invited = member.status === 'invited'

  return (
    <tr>
      <td>
        <span className="member">
          <span className="member__name">
            {member.display_name ?? member.email}
            {member.is_me && <span className="member__me"> (vous)</span>}
          </span>
          {member.display_name && <span className="member__email">{member.email}</span>}
        </span>
        {error && <Alert>{errorMessage(error)}</Alert>}
      </td>
      <td>
        {editable ? (
          <select
            aria-label={`Rôle de ${member.email}`}
            value={member.role}
            disabled={changeRole.isPending}
            onChange={(e) => changeRole.mutate({ member, role: e.target.value as InvitableRole })}
          >
            <option value="contributor">Contributeur</option>
            <option value="reader">Lecteur</option>
          </select>
        ) : (
          ROLE_LABELS[member.role]
        )}
      </td>
      <td>
        {invited ? (
          <StatusPill tone="warn">
            Invitation envoyée
            {member.invite_expires_at &&
              ` · jusqu’au ${dateFormat.format(new Date(member.invite_expires_at))}`}
          </StatusPill>
        ) : (
          <StatusPill tone="ok">Actif</StatusPill>
        )}
      </td>
      {canManage && (
        <td className="actions">
          {editable && invited && (
            <button
              type="button"
              className="button button--small"
              disabled={renew.isPending}
              onClick={() => renew.mutate(member.id, { onSuccess: onLink })}
            >
              Nouveau lien
            </button>
          )}
          {editable &&
            (confirming ? (
              <>
                <button
                  type="button"
                  className="button button--small button--danger"
                  disabled={remove.isPending}
                  onClick={() => remove.mutate(member.id)}
                >
                  {invited ? 'Annuler l’invitation' : 'Confirmer le retrait'}
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
                Retirer
              </button>
            ))}
        </td>
      )}
    </tr>
  )
}

export function MembersPage() {
  const { space } = useOutletContext<SpaceContext>()
  const members = useMembers(space.id)
  const [link, setLink] = useState<InvitationLink | null>(null)
  const isOwner = space.role === 'owner'

  return (
    <div className="page-content">
      <PageHeader
        title="Accès et membres"
        subtitle={
          <>
            Les <strong>lecteurs</strong> consultent ; les <strong>contributeurs</strong> ajoutent
            et modifient. Seul le rôle Propriétaire gère les accès.
          </>
        }
      />

      {isOwner && (
        <section className="section">
          <h2>Inviter une personne</h2>
          <InviteForm spaceId={space.id} onInvited={setLink} />
        </section>
      )}

      {link && <LinkPanel link={link} onClose={() => setLink(null)} />}

      <section className="section">
        <h2>Membres de l’espace</h2>
        {members.isPending && <p className="muted">Chargement…</p>}
        {members.isError && <Alert>{errorMessage(members.error)}</Alert>}
        {members.data && (
          <div className="table-scroll">
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">Personne</th>
                  <th scope="col">Rôle</th>
                  <th scope="col">Statut</th>
                  {isOwner && (
                    <th scope="col">
                      <span className="visually-hidden">Actions</span>
                    </th>
                  )}
                </tr>
              </thead>
              <tbody>
                {members.data.map((member) => (
                  <MemberRow
                    key={member.id}
                    member={member}
                    spaceId={space.id}
                    canManage={isOwner}
                    onLink={setLink}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}
