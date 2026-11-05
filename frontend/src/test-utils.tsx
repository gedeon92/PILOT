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
