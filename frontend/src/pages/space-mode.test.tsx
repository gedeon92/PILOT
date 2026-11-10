import { screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  meWith,
  mockApi,
  OWNER_MEMBER,
  projectFixture,
  renderApp,
  SPACE_ID,
  spaceWith,
} from '../test-utils'

/** Mode simple (par défaut) : PILOT reste léger ; les fonctions du cahier « Assistante
 * augmentée » n'apparaissent qu'en mode complet. */

const base = `/api/spaces/${SPACE_ID}`

afterEach(() => {
  vi.unstubAllGlobals()
})

function routes(advanced: boolean) {
  return {
    'GET /api/auth/me': () => ({ status: 200, json: meWith('owner') }),
    [`GET ${base}`]: () => ({
      status: 200,
      json: { ...spaceWith('owner'), advanced_mode: advanced },
    }),
    [`GET ${base}/members`]: () => ({ status: 200, json: [OWNER_MEMBER] }),
    [`GET ${base}/portfolios`]: () => ({ status: 200, json: [] }),
    [`GET ${base}/alerts`]: () => ({ status: 200, json: { unread: 0, items: [] } }),
    [`GET ${base}/projects`]: () => ({ status: 200, json: [projectFixture()] }),
    [`GET ${base}/projects/pr1`]: () => ({ status: 200, json: projectFixture() }),
    [`GET ${base}/projects/pr1/tasks`]: () => ({
      status: 200,
      json: [
        {
          id: 't1',
          project_id: 'pr1',
          title: 'Réserver la salle',
          deliverable: null,
          status: 'todo',
          assignee: { member_id: null, name: null, has_account: false },
          due_date: null,
          due_certainty: null,
          late: false,
          closed_at: null,
          version: 1,
          priority: 'urgent',
        },
      ],
    }),
    [`GET ${base}/projects/pr1/sections`]: () => ({ status: 200, json: [] }),
    [`GET ${base}/projects/pr1/milestones`]: () => ({ status: 200, json: [] }),
    [`GET ${base}/projects/pr1/history`]: () => ({ status: 200, json: [] }),
    [`GET ${base}/projects/pr1/documents`]: () => ({ status: 200, json: [] }),
    [`GET ${base}/projects/pr1/links`]: () => ({ status: 200, json: [] }),
  }
}

describe('mode simple et mode complet', () => {
  it('mode simple : ni jalons, ni décisions, ni statuts avancés, ni priorité', async () => {
    mockApi(routes(false))
    renderApp(`/espaces/${SPACE_ID}/projets/pr1`)
    const status = await screen.findByRole('combobox', { name: 'Statut de « Réserver la salle »' })
    const labels = within(status)
      .getAllByRole('option')
      .map((o) => o.textContent)
    expect(labels).toEqual(['À faire', 'En cours', 'Terminée', 'Annulée'])
    expect(screen.queryByRole('heading', { name: /^Jalons/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Décisions' })).not.toBeInTheDocument()
    expect(screen.queryByText('⚡ Urgente')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Sections types' })).not.toBeInTheDocument()
  })

  it('mode complet : tout apparaît', async () => {
    mockApi(routes(true))
    renderApp(`/espaces/${SPACE_ID}/projets/pr1`)
    const status = await screen.findByRole('combobox', { name: 'Statut de « Réserver la salle »' })
    expect(within(status).getAllByRole('option')).toHaveLength(7)
    expect(await screen.findByRole('heading', { name: /^Jalons/ })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Décisions' })).toBeInTheDocument()
    expect(screen.getByText('⚡ Urgente')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Sections types' })).toBeInTheDocument()
  })
})
