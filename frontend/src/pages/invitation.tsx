import { Link, useNavigate, useParams } from 'react-router'
import { errorMessage, ROLE_LABELS } from '../api/client'
import { useAcceptInvitation, useInvitationInfo, useLogout, useMe } from '../api/queries'
import { Alert, AuthCard, FullPageLoader } from '../components/ui'

export function InvitationPage() {
  const { token = '' } = useParams()
  const me = useMe()
  const info = useInvitationInfo(token, Boolean(me.data))
  const accept = useAcceptInvitation()
  const logout = useLogout()
  const navigate = useNavigate()
  const here = `/invitation/${token}`

  if (me.isPending) return <FullPageLoader />

  if (!me.data) {
    return (
      <AuthCard
        title="Invitation à rejoindre un espace"
        subtitle="Connectez-vous ou créez un compte avec l’adresse e-mail qui a reçu l’invitation."
      >
        <div className="stack">
          <Link
            className="button button--primary"
            to={`/inscription?next=${encodeURIComponent(here)}`}
          >
            Créer un compte
          </Link>
          <Link className="button" to={`/connexion?next=${encodeURIComponent(here)}`}>
            J’ai déjà un compte
          </Link>
        </div>
      </AuthCard>
    )
  }

  if (info.isPending) return <FullPageLoader />

  if (info.isError) {
    return (
      <AuthCard title="Invitation indisponible">
        <Alert>{errorMessage(info.error)}</Alert>
        <Link className="button" to="/">
          Aller à mes espaces
        </Link>
      </AuthCard>
    )
  }

  const invitation = info.data
  return (
    <AuthCard
      title={`Rejoindre « ${invitation.space_name} »`}
      subtitle={
        <>
          {invitation.invited_by
            ? `${invitation.invited_by} vous invite`
            : 'Vous avez reçu une invitation'}{' '}
          avec le rôle <strong>{ROLE_LABELS[invitation.role]}</strong>.
        </>
      }
    >
      {invitation.expired ? (
        <Alert tone="warn">
          Cette invitation a expiré. Demandez un nouveau lien à l’auteur de l’invitation.
        </Alert>
      ) : !invitation.email_matches ? (
        <div className="stack">
          <Alert tone="warn">
            Cette invitation est destinée à <strong>{invitation.email}</strong>, mais vous êtes
            connecté·e avec <strong>{me.data.user.email}</strong>.
          </Alert>
          <button
            className="button"
            type="button"
            onClick={() =>
              logout.mutate(undefined, {
                onSuccess: () => navigate(`/connexion?next=${encodeURIComponent(here)}`),
              })
            }
          >
            Changer de compte
          </button>
        </div>
      ) : (
        <div className="stack">
          {accept.isError && <Alert>{errorMessage(accept.error)}</Alert>}
          <button
            className="button button--primary"
            type="button"
            disabled={accept.isPending}
            onClick={() =>
              accept.mutate(token, {
                onSuccess: (space) => navigate(`/espaces/${space.id}`, { replace: true }),
              })
            }
          >
            {accept.isPending ? 'Un instant…' : 'Rejoindre l’espace'}
          </button>
        </div>
      )}
    </AuthCard>
  )
}
