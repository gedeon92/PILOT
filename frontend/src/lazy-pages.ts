import { lazy } from 'react'

/** Pages chargées à la demande : l'ouverture de PILOT ne télécharge que l'essentiel
 * (connexion, mise en page, vue d'ensemble). Les autres pages sont ensuite préchargées en
 * arrière-plan (`preloadPages`), pour qu'un clic les affiche sans attendre. */

const loaders = {
  account: () => import('./pages/account'),
  agenda: () => import('./pages/agenda'),
  alerts: () => import('./pages/alerts'),
  decisions: () => import('./pages/decisions'),
  documents: () => import('./pages/documents'),
  events: () => import('./pages/events'),
  members: () => import('./pages/members'),
  projectDetail: () => import('./pages/project-detail'),
  pilotage: () => import('./pages/pilotage'),
  projects: () => import('./pages/projects'),
  relations: () => import('./pages/relations'),
  routines: () => import('./pages/routines'),
  settings: () => import('./pages/settings'),
  timeline: () => import('./pages/timeline'),
  updates: () => import('./pages/updates'),
  weekly: () => import('./pages/weekly'),
}

export const AccountPage = lazy(() => loaders.account().then((m) => ({ default: m.AccountPage })))
export const AgendaPage = lazy(() => loaders.agenda().then((m) => ({ default: m.AgendaPage })))
export const RoutinesPage = lazy(() =>
  loaders.routines().then((m) => ({ default: m.RoutinesPage })),
)
export const PilotagePage = lazy(() =>
  loaders.pilotage().then((m) => ({ default: m.PilotagePage })),
)
export const RelationsPage = lazy(() =>
  loaders.relations().then((m) => ({ default: m.RelationsPage })),
)
export const AlertsPage = lazy(() => loaders.alerts().then((m) => ({ default: m.AlertsPage })))
export const DecisionsPage = lazy(() =>
  loaders.decisions().then((m) => ({ default: m.DecisionsPage })),
)
export const DocumentsPage = lazy(() =>
  loaders.documents().then((m) => ({ default: m.DocumentsPage })),
)
export const EventsPage = lazy(() => loaders.events().then((m) => ({ default: m.EventsPage })))
export const MembersPage = lazy(() => loaders.members().then((m) => ({ default: m.MembersPage })))
export const ProjectDetailPage = lazy(() =>
  loaders.projectDetail().then((m) => ({ default: m.ProjectDetailPage })),
)
export const ProjectsPage = lazy(() =>
  loaders.projects().then((m) => ({ default: m.ProjectsPage })),
)
export const NewProjectPage = lazy(() =>
  loaders.projects().then((m) => ({ default: m.NewProjectPage })),
)
export const SettingsPage = lazy(() =>
  loaders.settings().then((m) => ({ default: m.SettingsPage })),
)
export const TimelinePage = lazy(() =>
  loaders.timeline().then((m) => ({ default: m.TimelinePage })),
)
export const UpdatesPage = lazy(() => loaders.updates().then((m) => ({ default: m.UpdatesPage })))
export const WeeklyPage = lazy(() => loaders.weekly().then((m) => ({ default: m.WeeklyPage })))

let preloaded = false

/** Précharge toutes les pages quand le navigateur est au repos (une seule fois). */
export function preloadPages() {
  if (preloaded) return
  preloaded = true
  const run = () => Object.values(loaders).forEach((load) => void load().catch(() => {}))
  if ('requestIdleCallback' in window) window.requestIdleCallback(run, { timeout: 3000 })
  else setTimeout(run, 1500)
}
