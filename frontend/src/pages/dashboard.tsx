import { Link, useOutletContext } from 'react-router'
import { ROLE_LABELS } from '../api/client'
import { useMembers } from '../api/queries'
import { DashboardIcon, MembersIcon } from '../components/icons'
import type { SpaceContext } from './space-layout'

export function DashboardPage() {
  const { space, me } = useOutletContext<SpaceContext>()
  const members = useMembers(space.id)
  const active = members.data?.filter((m) => m.status === 'active').length
  const invited = members.data?.filter((m) => m.status === 'invited').length

  return (
    <div className="page-content">
      <header className="page-header">
        <h1>Bonjour, {me.user.display_name}</h1>
        <p>
          {space.name} · fuseau {space.timezone}
        </p>
      </header>

      <section className="cards" aria-label="Résumé de l’espace">
        <div className="card">
          <span className="card__label">Votre rôle</span>
          <span className="card__value">{ROLE_LABELS[space.role]}</span>
        </div>
        <Link className="card card--link" to={`/espaces/${space.id}/membres`}>
          <span className="card__label">
            <MembersIcon size={18} /> Membres actifs
          </span>
          <span className="card__value">{active ?? '…'}</span>
          {Boolean(invited) && (
            <span className="card__note">{invited} invitation(s) en attente</span>
          )}
        </Link>
      </section>

      <section className="empty-state">
        <span className="empty-state__icon">
          <DashboardIcon />
        </span>
        <h2>Aucun projet pour l’instant</h2>
        <p>
          La gestion des projets et des tâches arrive dans une prochaine version. En attendant, vous
          pouvez inviter les personnes qui suivront les projets avec vous.
        </p>
        {space.role === 'owner' && (
          <Link className="button button--primary" to={`/espaces/${space.id}/membres`}>
            Inviter des membres
          </Link>
        )}
      </section>
    </div>
  )
}
