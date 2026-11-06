import { Navigate, Outlet, Route, Routes, useLocation } from 'react-router'
import type { Me } from './api/client'
import { useMe } from './api/queries'
import { Alert, AuthCard, FullPageLoader } from './components/ui'
import { ForgotPasswordPage, LoginPage, RegisterPage, ResetPasswordPage } from './pages/auth'
import { AccountPage, ConfirmEmailPage } from './pages/account'
import { AlertsPage } from './pages/alerts'
import { CreateSpacePage } from './pages/create-space'
import { DashboardPage } from './pages/dashboard'
import { InvitationPage } from './pages/invitation'
import { DocumentsPage } from './pages/documents'
import { EventsPage } from './pages/events'
import { MembersPage } from './pages/members'
import { ProjectDetailPage } from './pages/project-detail'
import { NewProjectPage, ProjectsPage } from './pages/projects'
import { SettingsPage } from './pages/settings'
import { SpaceLayout } from './pages/space-layout'
import { StatusPage } from './pages/status'
import { TasksPage } from './pages/tasks'
import { TimelinePage } from './pages/timeline'
import { WeeklyPage } from './pages/weekly'
import { UpdatesPage } from './pages/updates'

/** Affiche `children(me)` si quelqu'un est connecté, sinon renvoie vers la connexion. */
function RequireAuth({ children }: { children: (me: Me) => React.ReactNode }) {
  const me = useMe()
  const location = useLocation()

  if (me.isPending) return <FullPageLoader />
  if (me.isError) {
    return (
      <AuthCard title="Serveur indisponible">
        <Alert>{me.error.message}</Alert>
        <button className="button" type="button" onClick={() => me.refetch()}>
          Réessayer
        </button>
      </AuthCard>
    )
  }
  if (!me.data) {
    const next = location.pathname + location.search
    return <Navigate to={`/connexion?next=${encodeURIComponent(next)}`} replace />
  }
  return <>{children(me.data)}</>
}

/** Les pages de connexion n'ont pas de sens si l'on est déjà connecté. */
function GuestOnly() {
  const me = useMe()
  if (me.isPending) return <FullPageLoader />
  if (me.data) return <Navigate to="/" replace />
  return <Outlet />
}

function Home({ me }: { me: Me }) {
  const first = me.spaces[0]
  return <Navigate to={first ? `/espaces/${first.id}` : '/espaces/nouveau'} replace />
}

export default function App() {
  return (
    <Routes>
      <Route element={<GuestOnly />}>
        <Route path="/connexion" element={<LoginPage />} />
        <Route path="/inscription" element={<RegisterPage />} />
        <Route path="/mot-de-passe-oublie" element={<ForgotPasswordPage />} />
      </Route>
      <Route path="/mot-de-passe/nouveau" element={<ResetPasswordPage />} />
      <Route path="/invitation/:token" element={<InvitationPage />} />
      <Route path="/etat" element={<StatusPage />} />
      <Route
        path="/compte/confirmer-email"
        element={<RequireAuth>{() => <ConfirmEmailPage />}</RequireAuth>}
      />

      <Route path="/" element={<RequireAuth>{(me) => <Home me={me} />}</RequireAuth>} />
      <Route
        path="/espaces/nouveau"
        element={<RequireAuth>{() => <CreateSpacePage />}</RequireAuth>}
      />
      <Route
        path="/espaces/:spaceId"
        element={<RequireAuth>{(me) => <SpaceLayout me={me} />}</RequireAuth>}
      >
        <Route index element={<DashboardPage />} />
        <Route path="projets" element={<ProjectsPage />} />
        <Route path="evenements" element={<EventsPage />} />
        <Route path="taches" element={<TasksPage />} />
        <Route path="point-hebdo" element={<WeeklyPage />} />
        <Route path="timeline" element={<TimelinePage />} />
        <Route path="documents" element={<DocumentsPage />} />
        <Route path="mises-a-jour" element={<UpdatesPage />} />
        <Route path="alertes" element={<AlertsPage />} />
        <Route path="compte" element={<AccountPage />} />
        <Route path="projets/nouveau" element={<NewProjectPage />} />
        <Route path="projets/:projectId" element={<ProjectDetailPage />} />
        <Route path="membres" element={<MembersPage />} />
        <Route path="parametres" element={<SettingsPage />} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
