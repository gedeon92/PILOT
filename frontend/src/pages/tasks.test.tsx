import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
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

/** Les tâches se gèrent dans la fiche de leur projet (décision du 9 nov. 2026) :
 * liste ou tableau, plus d'onglet « Tâches » dans le menu. */

const base = `/api/spaces/${SPACE_ID}`
const page = `/espaces/${SPACE_ID}/projets/pr1`

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

function routes(role: 'owner' | 'reader', tasks: unknown[], extra = {}) {
  return {
    'GET /api/auth/me': () => ({ status: 200, json: meWith(role) }),
    [`GET ${base}`]: () => ({ status: 200, json: spaceWith(role) }),
    [`GET ${base}/members`]: () => ({ status: 200, json: [OWNER_MEMBER] }),
    [`GET ${base}/portfolios`]: () => ({ status: 200, json: [] }),
    [`GET ${base}/alerts`]: () => ({ status: 200, json: { unread: 0, items: [] } }),
    [`GET ${base}/projects`]: () => ({ status: 200, json: [projectFixture()] }),
    [`GET ${base}/projects/pr1`]: () => ({ status: 200, json: projectFixture() }),
    [`GET ${base}/projects/pr1/tasks`]: () => ({ status: 200, json: tasks }),
    [`GET ${base}/projects/pr1/history`]: () => ({ status: 200, json: [] }),
    [`GET ${base}/projects/pr1/documents`]: () => ({ status: 200, json: [] }),
    [`GET ${base}/projects/pr1/links`]: () => ({ status: 200, json: [] }),
    ...extra,
  }
}

const TASKS = [
  task('t1', 'Signer le traiteur'),
  task('t2', 'Réserver la salle', { status: 'in_progress' }),
  task('t3', 'Choisir la date', { status: 'done', closed_at: '2026-11-01T10:00:00Z' }),
]

describe('tâches dans la fiche projet', () => {
  it('n’apparaissent plus dans le menu, et se cochent dans la liste du projet', async () => {
    const calls = mockApi(
      routes('owner', TASKS, {
        [`PATCH ${base}/tasks/t1`]: () => ({ status: 200, json: task('t1', 'Signer le traiteur') }),
      }),
    )
    renderApp(page)
    const user = userEvent.setup()

    const nav = await screen.findByRole('navigation', { name: 'Navigation principale' })
    expect(within(nav).queryByRole('link', { name: 'Tâches' })).not.toBeInTheDocument()

    await user.click(
      await screen.findByRole('checkbox', {
        name: 'Marquer « Signer le traiteur » comme terminée',
      }),
    )
    await waitFor(() =>
      expect(calls.find((c) => c.key === `PATCH ${base}/tasks/t1`)?.body).toEqual({
        status: 'done',
        version: 1,
      }),
    )
  })

  it('vue Tableau : les cartes se déplacent en glissant ou avec le menu', async () => {
    const calls = mockApi(
      routes('owner', TASKS, {
        [`PATCH ${base}/tasks/t1`]: () => ({
          status: 200,
          json: task('t1', 'Signer le traiteur', { status: 'in_progress', version: 2 }),
        }),
        [`PATCH ${base}/tasks/t2`]: () => ({
          status: 200,
          json: task('t2', 'Réserver la salle', { status: 'done', version: 2 }),
        }),
      }),
    )
    renderApp(page)
    const user = userEvent.setup()

    await user.click(await screen.findByRole('button', { name: '▦ Tableau' }))
    const todo = await screen.findByRole('region', { name: /^À faire/ })
    const doing = screen.getByRole('region', { name: /^En cours/ })
    const done = screen.getByRole('region', { name: /^Terminé/ })
    expect(within(todo).getByText('Signer le traiteur')).toBeInTheDocument()
    expect(within(doing).getByText('Réserver la salle')).toBeInTheDocument()
    expect(within(done).getByText('Choisir la date')).toBeInTheDocument()

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
    expect(within(doing).getByText('Signer le traiteur')).toBeInTheDocument()

    await user.selectOptions(
      screen.getByRole('combobox', { name: 'Colonne de « Réserver la salle »' }),
      'done',
    )
    await waitFor(() => expect(calls.some((c) => c.key === `PATCH ${base}/tasks/t2`)).toBe(true))
  })

  it('un lecteur voit le tableau sans pouvoir déplacer les cartes', async () => {
    mockApi(routes('reader', TASKS))
    renderApp(page)
    const user = userEvent.setup()

    await user.click(await screen.findByRole('button', { name: '▦ Tableau' }))
    const todo = await screen.findByRole('region', { name: /^À faire/ })
    const card = within(todo).getByText('Signer le traiteur').closest('li')!
    expect(card).toHaveAttribute('draggable', 'false')
    expect(screen.queryByRole('combobox', { name: /Colonne de/ })).not.toBeInTheDocument()
  })
})

describe('historique du projet', () => {
  it('s’ouvre seulement avec le bouton « Historique »', async () => {
    mockApi(
      routes('reader', [], {
        [`GET ${base}/projects/pr1/history`]: () => ({
          status: 200,
          json: [
            {
              id: 'h1',
              action: 'project.created',
              target_type: 'project',
              actor_name: 'Aïcha Ndiaye',
              created_at: '2026-11-03T10:00:00Z',
              before: null,
              after: { title: 'Salon Agri' },
            },
          ],
        }),
      }),
    )
    renderApp(page)
    const user = userEvent.setup()

    await screen.findByRole('heading', { name: /^Tâches/ })
    expect(screen.queryByText('Projet créé')).not.toBeInTheDocument()

    // Même un lecteur peut consulter l'historique.
    await user.click(screen.getByRole('button', { name: 'Historique' }))
    const drawer = await screen.findByRole('dialog', { name: 'Historique' })
    expect(await within(drawer).findByText('Projet créé')).toBeInTheDocument()

    await user.click(within(drawer).getByRole('button', { name: 'Fermer l’historique' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
})

describe('accès au projet (lot C)', () => {
  const MOUSSA = {
    ...OWNER_MEMBER,
    id: 'm2',
    email: 'moussa@exemple.com',
    display_name: 'Moussa Diop',
    role: 'contributor',
    is_me: false,
  }

  it('le propriétaire rend le projet privé et y ajoute une personne', async () => {
    const calls = mockApi(
      routes('owner', [], {
        [`GET ${base}/members`]: () => ({ status: 200, json: [OWNER_MEMBER, MOUSSA] }),
        [`GET ${base}/projects/pr1/access`]: () => ({
          status: 200,
          json: { private: false, members: [] },
        }),
        [`PUT ${base}/projects/pr1/access`]: () => ({
          status: 200,
          json: { private: true, members: [] },
        }),
      }),
    )
    renderApp(page)
    const user = userEvent.setup()

    await user.click(await screen.findByRole('button', { name: 'Accès' }))
    const drawer = await screen.findByRole('dialog', { name: 'Accès au projet' })
    await user.click(await within(drawer).findByRole('radio', { name: /Privé/ }))
    await user.selectOptions(within(drawer).getByLabelText('Ajouter une personne'), 'm2')
    await user.click(within(drawer).getByRole('button', { name: 'Ajouter' }))
    await user.selectOptions(
      within(drawer).getByRole('combobox', { name: 'Rôle de Moussa Diop sur ce projet' }),
      'reader',
    )
    await user.click(within(drawer).getByRole('button', { name: 'Enregistrer les accès' }))

    await waitFor(() =>
      expect(calls.find((c) => c.key === `PUT ${base}/projects/pr1/access`)?.body).toEqual({
        private: true,
        members: [{ member_id: 'm2', role: 'reader' }],
      }),
    )
  })

  it('un lecteur sur ce projet ne voit pas les boutons de modification', async () => {
    mockApi({
      ...routes('owner', TASKS),
      'GET /api/auth/me': () => ({ status: 200, json: meWith('contributor') }),
      [`GET ${base}`]: () => ({ status: 200, json: spaceWith('contributor') }),
      [`GET ${base}/projects/pr1`]: () => ({
        status: 200,
        json: projectFixture({ my_role: 'reader', private: true }),
      }),
    })
    renderApp(page)

    expect(await screen.findByText('🔒 Privé')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Modifier la fiche' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Sous-tâche/ })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '🔒 Accès' })).toBeInTheDocument()
  })
})

describe('corrections de l’audit (écran)', () => {
  it('E2 : deux cartes déplacées très vite restent toutes deux à leur place', async () => {
    const calls = mockApi(
      routes('owner', TASKS, {
        [`PATCH ${base}/tasks/t1`]: () => ({
          status: 200,
          json: task('t1', 'Signer le traiteur', { status: 'in_progress', version: 2 }),
        }),
        [`PATCH ${base}/tasks/t2`]: () => ({
          status: 200,
          json: task('t2', 'Réserver la salle', { status: 'done', version: 2 }),
        }),
      }),
    )
    renderApp(page)
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: '▦ Tableau' }))

    const first = screen.getByRole('combobox', { name: 'Colonne de « Signer le traiteur »' })
    const second = screen.getByRole('combobox', { name: 'Colonne de « Réserver la salle »' })
    await user.selectOptions(first, 'in_progress')
    await user.selectOptions(second, 'done')

    await waitFor(() =>
      expect(calls.filter((c) => c.key.startsWith(`PATCH ${base}/tasks/`))).toHaveLength(2),
    )
    const doing = screen.getByRole('region', { name: /^En cours/ })
    const done = screen.getByRole('region', { name: /^Terminé/ })
    expect(within(doing).getByText('Signer le traiteur')).toBeInTheDocument()
    expect(within(done).getByText('Réserver la salle')).toBeInTheDocument()
  })

  it('M6 : pas de « + Sous-tâche » dans un projet terminé', async () => {
    mockApi({
      ...routes('owner', TASKS),
      [`GET ${base}/projects/pr1`]: () => ({
        status: 200,
        json: projectFixture({ status: 'done', outcome: 'Bilan positif' }),
      }),
    })
    renderApp(page)
    expect(await screen.findByText('Signer le traiteur')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Ajouter une sous-tâche/ })).not.toBeInTheDocument()
  })

  it('M9 : le panneau Historique rend le focus au bouton qui l’a ouvert', async () => {
    mockApi(routes('owner', []))
    renderApp(page)
    const user = userEvent.setup()
    const opener = await screen.findByRole('button', { name: 'Historique' })
    await user.click(opener)
    const drawer = await screen.findByRole('dialog', { name: 'Historique' })
    expect(drawer).toHaveFocus()
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(opener).toHaveFocus()
  })
})
