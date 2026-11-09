import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { meWith, mockApi, OWNER_MEMBER, renderApp, SPACE_ID, spaceWith } from '../test-utils'

const base = `/api/spaces/${SPACE_ID}`

afterEach(() => {
  vi.unstubAllGlobals()
})

function task(id: string, title: string, extra: Record<string, unknown> = {}) {
  return {
    id,
    project_id: 'pr1',
    title,
    deliverable: null,
    status: 'todo',
    assignee: { member_id: null, name: null, has_account: false },
    due_date: null,
    due_certainty: null,
    late: false,
    closed_at: null,
    version: 1,
    ...extra,
  }
}

describe('page Tâches', () => {
  it('rassemble les tâches, filtre les retards et coche une tâche', async () => {
    const calls = mockApi({
      'GET /api/auth/me': () => ({ status: 200, json: meWith('owner') }),
      [`GET ${base}`]: () => ({ status: 200, json: spaceWith('owner') }),
      [`GET ${base}/members`]: () => ({ status: 200, json: [OWNER_MEMBER] }),
      [`GET ${base}/portfolios`]: () => ({ status: 200, json: [] }),
      [`GET ${base}/alerts`]: () => ({ status: 200, json: { unread: 0, items: [] } }),
      [`GET ${base}/projects`]: () => ({
        status: 200,
        json: [{ id: 'pr1', title: 'Salon Agri 2026' }],
      }),
      [`GET ${base}/tasks`]: () => ({
        status: 200,
        json: [
          task('t1', 'Signer le traiteur', { due_date: '2020-01-10', late: true }),
          task('t2', 'Réserver la salle'),
        ],
      }),
      [`PATCH ${base}/tasks/t1`]: () => ({ status: 200, json: task('t1', 'Signer le traiteur') }),
    })
    renderApp(`/espaces/${SPACE_ID}/taches`)
    const user = userEvent.setup()

    const list = await screen.findByRole('region', { name: 'Liste des tâches' })
    expect(await within(list).findByText('Réserver la salle')).toBeInTheDocument()
    expect(within(list).getAllByText('Projet : Salon Agri 2026')).toHaveLength(2)
    expect(within(list).queryByRole('link')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /En retard/ }))
    expect(within(list).queryByText('Réserver la salle')).not.toBeInTheDocument()

    await user.click(
      within(list).getByRole('checkbox', { name: 'Marquer « Signer le traiteur » comme terminée' }),
    )
    expect(calls.find((c) => c.key === `PATCH ${base}/tasks/t1`)?.body).toEqual({
      status: 'done',
      version: 1,
    })
  })
})

describe('fiche projet et page Tâches', () => {
  it('la fiche résume les tâches et renvoie vers la page Tâches filtrée sur le projet', async () => {
    mockApi({
      'GET /api/auth/me': () => ({ status: 200, json: meWith('owner') }),
      [`GET ${base}`]: () => ({ status: 200, json: spaceWith('owner') }),
      [`GET ${base}/members`]: () => ({ status: 200, json: [OWNER_MEMBER] }),
      [`GET ${base}/portfolios`]: () => ({ status: 200, json: [] }),
      [`GET ${base}/alerts`]: () => ({ status: 200, json: { unread: 0, items: [] } }),
      [`GET ${base}/projects`]: () => ({
        status: 200,
        json: [
          { id: 'pr1', title: 'Salon Agri 2026' },
          { id: 'pr2', title: 'Baromètre' },
        ],
      }),
      [`GET ${base}/tasks`]: () => ({
        status: 200,
        json: [
          task('t1', 'Signer le traiteur'),
          task('t2', 'Analyser les réponses', { project_id: 'pr2' }),
        ],
      }),
    })
    renderApp(`/espaces/${SPACE_ID}/taches?projet=pr2`)

    const list = await screen.findByRole('region', { name: 'Liste des tâches' })
    expect(await within(list).findByText('Analyser les réponses')).toBeInTheDocument()
    expect(within(list).queryByText('Signer le traiteur')).not.toBeInTheDocument()
  })
})
