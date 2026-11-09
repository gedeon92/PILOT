import { fireEvent, screen, waitFor, within } from '@testing-library/react'
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
    // Depuis le 9 nov. 2026, les tâches se gèrent dans la fiche projet : plus d'entrée au menu.
    const nav = screen.getByRole('navigation', { name: 'Navigation principale' })
    expect(within(nav).queryByRole('link', { name: 'Tâches' })).not.toBeInTheDocument()
  })
})

describe('vue Tableau', () => {
  function routes(role: 'owner' | 'reader') {
    return {
      'GET /api/auth/me': () => ({ status: 200, json: meWith(role) }),
      [`GET ${base}`]: () => ({ status: 200, json: spaceWith(role) }),
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
          task('t1', 'Signer le traiteur'),
          task('t2', 'Réserver la salle', { status: 'in_progress' }),
          task('t3', 'Choisir la date', { status: 'done', closed_at: '2026-11-01T10:00:00Z' }),
        ],
      }),
      [`PATCH ${base}/tasks/t1`]: () => ({
        status: 200,
        json: task('t1', 'Signer le traiteur', { status: 'in_progress', version: 2 }),
      }),
    }
  }

  it('range les cartes par colonne et les déplace en glissant ou avec le menu', async () => {
    const calls = mockApi(routes('owner'))
    renderApp(`/espaces/${SPACE_ID}/taches?vue=tableau`)
    const user = userEvent.setup()

    const todo = await screen.findByRole('region', { name: /^À faire/ })
    const doing = screen.getByRole('region', { name: /^En cours/ })
    const done = screen.getByRole('region', { name: /^Terminé/ })
    expect(await within(todo).findByText('Signer le traiteur')).toBeInTheDocument()
    expect(within(doing).getByText('Réserver la salle')).toBeInTheDocument()
    expect(within(done).getByText('Choisir la date')).toBeInTheDocument()

    // Glisser « Signer le traiteur » dans « En cours ».
    const data = new Map<string, string>()
    const dataTransfer = {
      setData: (k: string, v: string) => data.set(k, v),
      getData: (k: string) => data.get(k) ?? '',
      effectAllowed: '',
      dropEffect: '',
    }
    const card = within(todo).getByText('Signer le traiteur').closest('li')!
    fireEvent.dragStart(card, { dataTransfer })
    fireEvent.dragOver(doing, { dataTransfer })
    fireEvent.drop(doing, { dataTransfer })
    await waitFor(() =>
      expect(calls.find((c) => c.key === `PATCH ${base}/tasks/t1`)?.body).toEqual({
        status: 'in_progress',
        version: 1,
      }),
    )
    // La carte change de colonne tout de suite, sans attendre le serveur.
    expect(within(doing).getByText('Signer le traiteur')).toBeInTheDocument()

    // Même chose au clavier : le menu « Colonne » de la carte.
    await user.selectOptions(
      screen.getByRole('combobox', { name: 'Colonne de « Réserver la salle »' }),
      'done',
    )
    await waitFor(() => expect(calls.some((c) => c.key === `PATCH ${base}/tasks/t2`)).toBe(true))
  })

  it('un lecteur voit le tableau sans pouvoir déplacer les cartes', async () => {
    mockApi(routes('reader'))
    renderApp(`/espaces/${SPACE_ID}/taches?vue=tableau`)

    const todo = await screen.findByRole('region', { name: /^À faire/ })
    const card = (await within(todo).findByText('Signer le traiteur')).closest('li')!
    expect(card).toHaveAttribute('draggable', 'false')
    expect(screen.queryByRole('combobox', { name: /Colonne de/ })).not.toBeInTheDocument()
  })
})
