import { QueryClientProvider } from '@tanstack/react-query'
import { createQueryClient } from './api/query-client'
import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { vi } from 'vitest'
import App from './App'

type Handler = (body: unknown) => { status: number; json?: unknown }
/** Réponses simulées de l'API, indexées par « MÉTHODE /chemin ». */
export type Routes = Record<string, Handler>

export function mockApi(routes: Routes) {
  const calls: { key: string; body: unknown; headers: Record<string, string> }[] = []
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), 'http://localhost')
    const key = `${init?.method ?? 'GET'} ${url.pathname}`
    const body =
      init?.body instanceof FormData
        ? init.body
        : init?.body
          ? JSON.parse(String(init.body))
          : undefined
    calls.push({ key, body, headers: (init?.headers ?? {}) as Record<string, string> })
    const handler = routes[key]
    if (!handler)
      return new Response(JSON.stringify({ detail: `Non simulé : ${key}` }), { status: 500 })
    const { status, json } = handler(body)
    return new Response(status === 204 ? null : JSON.stringify(json ?? {}), { status })
  })
  vi.stubGlobal('fetch', fetchMock)
  return calls
}

export function renderApp(path: string) {
  const queryClient = createQueryClient({ retry: false })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

export const SPACE_ID = '11111111-1111-1111-1111-111111111111'

export function meWith(role: 'owner' | 'contributor' | 'reader') {
  return {
    user: { id: 'u1', email: 'aicha@exemple.com', display_name: 'Aïcha Ndiaye' },
    spaces: [{ id: SPACE_ID, name: 'Groupe Horizon', role }],
  }
}

export function spaceWith(role: 'owner' | 'contributor' | 'reader') {
  return { id: SPACE_ID, name: 'Groupe Horizon', timezone: 'Africa/Dakar', version: 1, role }
}

export const OWNER_MEMBER = {
  id: 'm1',
  email: 'aicha@exemple.com',
  display_name: 'Aïcha Ndiaye',
  role: 'owner',
  status: 'active',
  is_me: true,
  joined_at: '2026-11-03T10:00:00Z',
  invite_expires_at: null,
  version: 1,
}

/** Projet complet pour les tests de la fiche projet. */
export function projectFixture(extra: Record<string, unknown> = {}) {
  return {
    id: 'pr1',
    title: 'Salon Agri',
    status: 'in_progress',
    portfolio: { id: 'p1', name: 'Événements', color: 'orange', emoji: '🎪' },
    entity: null,
    project_type: null,
    owner: { member_id: null, name: 'Mon assistante', has_account: false },
    contributors: [{ member_id: null, name: 'Agence Lumière', has_account: false }],
    event: null,
    origin: 'Demandé en comité de direction',
    situation: 'Devis signé',
    situation_updated_at: '2026-11-05T09:00:00Z',
    situation_source: 'update',
    situation_source_label: 'point.docx',
    situation_updated_by: 'Aïcha Ndiaye',
    next_step: 'Réserver la salle',
    decision_needed: 'Choisir le lieu',
    decision_maker: 'Directrice générale',
    decision_options: [
      { label: 'CICAD', consequence: 'Plus cher, plus grand' },
      { label: 'Hôtel', consequence: null },
    ],
    objective: null,
    deliverables: null,
    progress: null,
    risk_level: null,
    risk_note: null,
    start_date: null,
    end_date: null,
    due_date: null,
    date_certainty: null,
    window_start: null,
    window_end: null,
    country: 'Sénégal',
    city: 'Dakar',
    external_url: null,
    outcome: null,
    cancel_reason: null,
    open_tasks: 0,
    late_tasks: 0,
    created_at: '2026-11-03T10:00:00Z',
    updated_at: '2026-11-05T09:00:00Z',
    version: 2,
    ...extra,
  }
}
