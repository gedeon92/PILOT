import { NavLink, Outlet, useNavigate, useParams } from 'react-router'
import { ROLE_LABELS, type Me, type Space } from '../api/client'
import { useLogout, useSpace } from '../api/queries'
import { BuildingIcon, DashboardIcon, Logo, LogoutIcon, MembersIcon } from '../components/icons'
import { Alert, FullPageLoader } from '../components/ui'

export type SpaceContext = { space: Space; me: Me }

function initials(name: string) {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join('')
}

function Sidebar({ me, space }: SpaceContext) {
  const navigate = useNavigate()
  const logout = useLogout()
  const base = `/espaces/${space.id}`
  const linkClass = ({ isActive }: { isActive: boolean }) =>
    isActive ? 'nav__link nav__link--active' : 'nav__link'

  return (
    <nav className="sidebar" aria-label="Navigation principale">
      <div className="brand">
        <Logo />
        <span className="brand__name">PILOT</span>
      </div>

      <label className="space-switcher">
        <BuildingIcon />
        <span className="visually-hidden">Espace</span>
        <select
          value={space.id}
          onChange={(e) =>
            navigate(e.target.value === 'new' ? '/espaces/nouveau' : `/espaces/${e.target.value}`)
          }
        >
          {me.spaces.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
          <option value="new">+ Créer un espace</option>
        </select>
      </label>

      <div className="nav">
        <NavLink to={base} end className={linkClass}>
          <DashboardIcon />
          Vue d’ensemble
        </NavLink>
        <NavLink to={`${base}/membres`} className={linkClass}>
          <MembersIcon />
          Accès et membres
        </NavLink>
      </div>

      <div className="sidebar__spacer" />

      <div className="user-card">
        <div className="user-card__who">
          <span className="avatar" aria-hidden="true">
            {initials(me.user.display_name)}
          </span>
          <span className="user-card__text">
            <span className="user-card__name">{me.user.display_name}</span>
            <span className="user-card__role">{ROLE_LABELS[space.role]}</span>
          </span>
        </div>
        <button
          type="button"
          className="nav__link"
          onClick={() => logout.mutate(undefined, { onSuccess: () => navigate('/connexion') })}
        >
          <LogoutIcon />
          Déconnexion
        </button>
      </div>
    </nav>
  )
}

export function SpaceLayout({ me }: { me: Me }) {
  const { spaceId = '' } = useParams()
  const space = useSpace(spaceId)

  if (space.isPending) return <FullPageLoader />
  if (space.isError) {
    return (
      <main className="centered">
        <div className="panel auth-card">
          <Alert>{space.error.message}</Alert>
          <a className="button" href="/">
            Revenir à mes espaces
          </a>
        </div>
      </main>
    )
  }

  const context: SpaceContext = { space: space.data, me }
  return (
    <div className="app">
      <Sidebar {...context} />
      <main className="app__main">
        <div className="panel app__panel">
          <Outlet context={context} />
        </div>
      </main>
    </div>
  )
}
