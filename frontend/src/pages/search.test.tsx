import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { meWith, mockApi, OWNER_MEMBER, renderApp, SPACE_ID, spaceWith } from '../test-utils'

const base = `/api/spaces/${SPACE_ID}`

function project(id: string, title: string, fields: Record<string, unknown> = {}) {
  return {
    id,
    title,
    status: 'in_progress',
    portfolio: { id: 'p1', name: 'Événements', color: 'orange' },
    entity: null,
    project_type: null,
    owner: { member_id: null, name: 'Aïcha Ndiaye', has_account: true },
    event: null,
    situation: null,
    situation_updated_at: null,
    next_step: 'Valider le budget',
    decision_needed: null,
    decision_maker: null,
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
    country: null,
    city: null,
    external_url: null,
    outcome: null,
    cancel_reason: null,
    open_tasks: 0,
    late_tasks: 0,
    created_at: '2026-11-03T10:00:00Z',
    updated_at: '2026-11-03T10:00:00Z',
    version: 1,
    ...fields,
  }
}

const PROJECTS = [
  project('a', 'Salon Dakar Tech', { status: 'blocked' }),
  project('b', 'Séminaire annuel'),
  project('c', 'Refonte du site', { country: 'Sénégal' }),
]

function routes() {
  return {
    'GET /api/auth/me': () => ({ status: 200, json: meWith('owner') }),
    [`GET ${base}`]: () => ({ status: 200, json: spaceWith('owner') }),
    [`GET ${base}/members`]: () => ({ status: 200, json: [OWNER_MEMBER] }),
    [`GET ${base}/portfolios`]: () => ({ status: 200, json: [] }),
    [`GET ${base}/entities`]: () => ({ status: 200, json: [] }),
    [`GET ${base}/projects`]: () => ({ status: 200, json: PROJECTS }),
    [`GET ${base}/tasks`]: () => ({ status: 200, json: [] }),
    [`GET ${base}/documents`]: () => ({ status: 200, json: [] }),
    [`GET ${base}/projects/b`]: () => ({ status: 200, json: PROJECTS[1] }),
    [`GET ${base}/projects/b/tasks`]: () => ({ status: 200, json: [] }),
    [`GET ${base}/projects/b/history`]: () => ({ status: 200, json: [] }),
    [`GET ${base}/projects/b/documents`]: () => ({ status: 200, json: [] }),
  }
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('recherche globale', () => {
  it('s’ouvre avec Ctrl+K, trouve un projet sans tenir compte des accents et l’ouvre', async () => {
    mockApi(routes())
    renderApp(`/espaces/${SPACE_ID}`)
    const user = userEvent.setup()
    await screen.findByRole('heading', { name: /Bonjour/ })

    await user.keyboard('{Control>}k{/Control}')
    const dialog = await screen.findByRole('dialog', { name: 'Recherche globale' })
    await user.type(within(dialog).getByRole('combobox'), 'seminaire')

    expect(within(dialog).getByRole('option', { name: /Séminaire annuel/ })).toBeInTheDocument()
    expect(
      within(dialog).queryByRole('option', { name: /Salon Dakar Tech/ }),
    ).not.toBeInTheDocument()

    await user.keyboard('{Enter}')
    expect(await screen.findByRole('heading', { name: 'Séminaire annuel' })).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
})

describe('listes filtrées', () => {
  it('lit le filtre d’attention dans l’adresse et n’affiche que les projets bloqués', async () => {
    mockApi(routes())
    renderApp(`/espaces/${SPACE_ID}/projets?attention=bloques`)

    const table = await screen.findByRole('table')
    await within(table).findByText('Salon Dakar Tech')
    expect(within(table).queryByText('Séminaire annuel')).not.toBeInTheDocument()
    expect(screen.getByText(/Projet au statut « Bloqué »/)).toBeInTheDocument()
  })

  it('filtre par pays depuis l’adresse', async () => {
    mockApi(routes())
    renderApp(`/espaces/${SPACE_ID}/projets?pays=S%C3%A9n%C3%A9gal`)

    const table = await screen.findByRole('table')
    await within(table).findByText('Refonte du site')
    expect(within(table).getAllByRole('row')).toHaveLength(2)
  })

  it('les cartes de la vue d’ensemble ouvrent la liste filtrée', async () => {
    mockApi(routes())
    renderApp(`/espaces/${SPACE_ID}`)

    const blocked = await screen.findByRole('link', { name: /Bloqués : 1, voir la liste/ })
    expect(blocked).toHaveAttribute('href', `/espaces/${SPACE_ID}/projets?attention=bloques`)
  })
})
