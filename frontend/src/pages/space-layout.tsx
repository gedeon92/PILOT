import { Suspense, useEffect, useState } from 'react'
import { NavLink, Outlet, useLocation, useNavigate, useParams } from 'react-router'
import { canWriteSpace, ROLE_LABELS, type Me, type Space } from '../api/client'
import { useAlerts, useCatalog, useLogout, useMembers, useSpace } from '../api/queries'
import {
  BellIcon,
  BuildingIcon,
  CalendarIcon,
  ClipboardIcon,
  ChevronsIcon,
  DashboardIcon,
  DocumentIcon,
  FolderIcon,
  ScaleIcon,
  Logo,
  LogoutIcon,
  MembersIcon,
  PlusIcon,
  SearchIcon,
  SettingsIcon,
  TimelineIcon,
} from '../components/icons'
import { CommandPalette } from '../components/command-palette'
import { Alert, FullPageLoader, Skeleton } from '../components/ui'
import { PortfolioMark } from '../components/portfolio-mark'
import { Avatar } from '../components/avatar'
import { AiAvatar } from '../components/ai-avatar'
import { ThemeToggle } from '../components/theme-toggle'
import { TaskDialogHost } from '../components/task-dialog'
import { preloadPages } from '../lazy-pages'

export type SpaceContext = { space: Space; me: Me }

const linkClass = ({ isActive }: { isActive: boolean }) =>
  isActive ? 'nav__link nav__link--active' : 'nav__link'

const COLLAPSE_KEY = 'pilot-sidebar-collapsed'

function readCollapsed() {
  try {
    return localStorage.getItem(COLLAPSE_KEY) === '1'
  } catch {
    return false
  }
}

function Sidebar({ me, space, onSearch }: SpaceContext & { onSearch: () => void }) {
  const navigate = useNavigate()
  const logout = useLogout()
  const members = useMembers(space.id)
  const portfolios = useCatalog(space.id, 'portfolios')
  const alerts = useAlerts(space.id)
  const base = `/espaces/${space.id}`
  const pending = members.data?.filter((m) => m.status === 'invited').length ?? 0
  // Sur téléphone, le menu est replié derrière un bouton ; il se referme à chaque changement de page.
  const location = useLocation()
  const [openOn, setOpenOn] = useState<string | null>(null)
  const open = openOn === location.pathname
  // Sur ordinateur, le menu se replie en une colonne d'icônes (choix gardé sur l'appareil),
  // pour laisser la place au contenu, par exemple à l'assistant IA.
  const [collapsed, setCollapsed] = useState(readCollapsed)
  function toggleCollapsed() {
    setCollapsed((value) => {
      try {
        localStorage.setItem(COLLAPSE_KEY, value ? '0' : '1')
      } catch {
        // Stockage indisponible (navigation privée) : le choix vaut pour cette visite.
      }
      return !value
    })
  }

  return (
    <nav
      className={['sidebar', open && 'sidebar--open', collapsed && 'sidebar--collapsed']
        .filter(Boolean)
        .join(' ')}
      aria-label="Navigation principale"
    >
      <div className="sidebar__top">
        <div className="brand">
          <Logo />
          <span className="brand__name">PILOT</span>
        </div>
        <button
          type="button"
          className="sidebar__collapse"
          aria-label={collapsed ? 'Déplier le menu' : 'Replier le menu'}
          title={collapsed ? 'Déplier le menu' : 'Replier le menu'}
          aria-pressed={collapsed}
          onClick={toggleCollapsed}
        >
          <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
            <rect
              x="3.5"
              y="4.5"
              width="17"
              height="15"
              rx="3"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
            />
            <path d="M9.5 4.5v15" stroke="currentColor" strokeWidth="1.8" />
            <path
              d={collapsed ? 'M13.5 10l2 2-2 2' : 'M16 10l-2 2 2 2'}
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </button>
        <button
          type="button"
          className="button button--small sidebar__toggle"
          aria-expanded={open}
          aria-controls="sidebar-content"
          onClick={() => setOpenOn(open ? null : location.pathname)}
        >
          {open ? 'Fermer' : 'Menu'}
        </button>
      </div>

      <div className="sidebar__content" id="sidebar-content">
        <button type="button" className="search-button" onClick={onSearch} title="Rechercher">
          <SearchIcon />
          <span className="search-button__label">Rechercher</span>
          <kbd>{navigator.platform.toLowerCase().includes('mac') ? '⌘K' : 'Ctrl K'}</kbd>
        </button>

        <label className="space-switcher">
          <BuildingIcon />
          <span className="visually-hidden">Changer d’espace</span>
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
          <ChevronsIcon />
        </label>

        <div className="sidebar__divider" />

        <div className="nav">
          <NavLink to={base} end className={linkClass} title="Vue d’ensemble">
            <DashboardIcon />
            <span className="nav__label">Vue d’ensemble</span>
          </NavLink>
          <NavLink to={`${base}/point-hebdo`} className={linkClass} title="Point hebdo">
            <ClipboardIcon />
            <span className="nav__label">Point hebdo</span>
          </NavLink>
          <NavLink to={`${base}/projets`} className={linkClass} title="Projets">
            <FolderIcon />
            <span className="nav__label">Projets</span>
          </NavLink>
          <NavLink to={`${base}/evenements`} className={linkClass} title="Événements">
            <CalendarIcon />
            <span className="nav__label">Événements</span>
          </NavLink>
          {space.advanced_mode && (
            <NavLink to={`${base}/decisions`} className={linkClass} title="Décisions">
              <ScaleIcon />
              <span className="nav__label">Décisions</span>
            </NavLink>
          )}
          <NavLink to={`${base}/timeline`} className={linkClass} title="Timeline">
            <TimelineIcon />
            <span className="nav__label">Timeline</span>
          </NavLink>
          <NavLink to={`${base}/documents`} className={linkClass} title="Documents">
            <DocumentIcon />
            <span className="nav__label">Documents</span>
          </NavLink>
          {space.role !== 'guest' && (
            <NavLink to={`${base}/mises-a-jour`} className={linkClass} title="Assistant IA">
              <AiAvatar size={22} still />
              <span className="nav__label">Assistant IA</span>
            </NavLink>
          )}
          <NavLink to={`${base}/alertes`} className={linkClass} title="Alertes">
            <BellIcon />
            <span className="nav__label">Alertes</span>
            {(alerts.data?.unread ?? 0) > 0 && (
              <span
                key={alerts.data?.unread /* nouveau nombre : le compteur « saute » */}
                className="badge badge--count"
                aria-label={`${alerts.data?.unread} alerte(s) non lue(s)`}
              >
                {alerts.data?.unread}
              </span>
            )}
          </NavLink>
        </div>

        <div className="sidebar__divider" />

        <div className="nav">
          <span className="nav__section nav__section--with-action">
            Portefeuilles
            {space.role === 'owner' && (
              <NavLink
                to={`${base}/parametres`}
                className="icon-button"
                aria-label="Ajouter ou modifier les portefeuilles"
              >
                <PlusIcon />
              </NavLink>
            )}
          </span>
          {portfolios.data?.length === 0 && <span className="nav__empty">Aucun portefeuille</span>}
          {portfolios.data?.map((portfolio) => (
            <span key={portfolio.id} className="nav__link nav__link--static">
              <PortfolioMark color={portfolio.color} emoji={portfolio.emoji} />
              <span className="nav__label">{portfolio.name}</span>
            </span>
          ))}
        </div>

        <div className="sidebar__divider" />

        <div className="nav">
          <span className="nav__section">Espace</span>
          <NavLink to={`${base}/membres`} className={linkClass} title="Accès et membres">
            <MembersIcon />
            <span className="nav__label">Accès et membres</span>
            {pending > 0 && (
              <span className="badge badge--count" title={`${pending} invitation(s) en attente`}>
                {pending}
              </span>
            )}
          </NavLink>
          <NavLink to={`${base}/parametres`} className={linkClass} title="Paramètres et structure">
            <SettingsIcon />
            <span className="nav__label">Paramètres et structure</span>
          </NavLink>
        </div>

        <div className="sidebar__spacer" />

        <div className="user-card">
          <div className="user-card__who">
            <Avatar name={me.user.display_name} />
            <span className="user-card__text">
              <span className="user-card__name">{me.user.display_name}</span>
              <span className="user-card__role">
                {ROLE_LABELS[space.role]} · {me.user.email}
              </span>
            </span>
          </div>
          <div className="user-card__actions">
            <NavLink to={`${base}/compte`} className={linkClass} title="Mon compte">
              <SettingsIcon />
              <span className="nav__label">Mon compte</span>
            </NavLink>
            <ThemeToggle />
            <button
              type="button"
              className="nav__link"
              title="Déconnexion"
              onClick={() => logout.mutate(undefined, { onSuccess: () => navigate('/connexion') })}
            >
              <LogoutIcon />
              <span className="nav__label">Déconnexion</span>
            </button>
          </div>
        </div>
      </div>
    </nav>
  )
}

export function SpaceLayout({ me }: { me: Me }) {
  const { spaceId = '' } = useParams()
  const space = useSpace(spaceId)
  const [searching, setSearching] = useState(false)
  useEffect(() => preloadPages(), [])

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
      {/* Accès direct au contenu pour la navigation au clavier ou au lecteur d'écran. */}
      <a className="skip-link" href="#contenu">
        Aller au contenu
      </a>
      <Sidebar {...context} onSearch={() => setSearching(true)} />
      <main className="app__main" id="contenu" tabIndex={-1}>
        {/* Page en cours de chargement (première visite seulement : elles sont préchargées). */}
        <Suspense fallback={<Skeleton lines={4} />}>
          <Outlet context={context} />
        </Suspense>
      </main>
      <CommandPalette
        spaceId={space.data.id}
        canWrite={canWriteSpace(space.data.role)}
        open={searching}
        setOpen={setSearching}
      />
      <TaskDialogHost spaceId={space.data.id} canWrite={space.data.role !== 'reader'} />
    </div>
  )
}
