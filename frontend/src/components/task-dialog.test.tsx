import { screen, within } from '@testing-library/react'
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

const base = `/api/spaces/${SPACE_ID}`

afterEach(() => {
  vi.unstubAllGlobals()
})

const MOUSSA = {
  ...OWNER_MEMBER,
  id: 'm2',
  email: 'moussa@exemple.com',
  display_name: 'Moussa Diop',
  role: 'contributor',
  is_me: false,
}

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
    parent_id: null,
    subtasks_total: 0,
    subtasks_done: 0,
    comments_count: 0,
    waiting_on: 0,
    ...extra,
  }
}

const detail = {
  task: task('t1', 'Envoyer les invitations', {
    subtasks_total: 2,
    subtasks_done: 1,
    comments_count: 1,
    waiting_on: 1,
  }),
  project_title: 'Salon Agri 2026',
  parent: null,
  subtasks: [
    task('s1', 'Imprimer les cartons', { parent_id: 't1', status: 'done' }),
    task('s2', 'Poster les cartons', { parent_id: 't1' }),
  ],
  depends_on: [
    {
      id: 't0',
      title: 'Signer le lieu',
      status: 'in_progress',
      project_id: 'pr1',
      project_title: 'Salon Agri 2026',
    },
  ],
  blocking: [],
  comments: [
    {
      id: 'c1',
      author_name: 'Aïcha Ndiaye',
      body: '@Moussa Diop peux-tu relancer ?',
      mentions: [{ member_id: 'm2', name: 'Moussa Diop' }],
      created_at: '2026-11-08T09:00:00Z',
      can_delete: true,
    },
  ],
  followers: [{ user_id: 'u1', name: 'Aïcha Ndiaye' }],
  following: true,
}

function routes(extra = {}) {
  return {
    'GET /api/auth/me': () => ({ status: 200, json: meWith('owner') }),
    [`GET ${base}`]: () => ({ status: 200, json: spaceWith('owner') }),
    [`GET ${base}/members`]: () => ({ status: 200, json: [OWNER_MEMBER, MOUSSA] }),
    [`GET ${base}/portfolios`]: () => ({ status: 200, json: [] }),
    [`GET ${base}/alerts`]: () => ({ status: 200, json: { unread: 0, items: [] } }),
    [`GET ${base}/projects`]: () => ({ status: 200, json: [projectFixture()] }),
    [`GET ${base}/projects/pr1`]: () => ({ status: 200, json: projectFixture() }),
    [`GET ${base}/projects/pr1/tasks`]: () => ({
      status: 200,
      json: [detail.task, ...detail.subtasks],
    }),
    [`GET ${base}/projects/pr1/history`]: () => ({ status: 200, json: [] }),
    [`GET ${base}/projects/pr1/documents`]: () => ({ status: 200, json: [] }),
    [`GET ${base}/projects/pr1/links`]: () => ({ status: 200, json: [] }),
    [`GET ${base}/tasks`]: () => ({ status: 200, json: [detail.task, ...detail.subtasks] }),
    [`GET ${base}/tasks/t1`]: () => ({ status: 200, json: detail }),
    ...extra,
  }
}

describe('fenêtre d’une tâche', () => {
  it('s’ouvre depuis la liste et montre sous-tâches, attente, commentaires et abonnés', async () => {
    mockApi(routes())
    renderApp(`/espaces/${SPACE_ID}/projets/pr1`)
    const user = userEvent.setup()

    const list = await screen.findByRole('region', { name: /^Tâches/ })
    expect(await within(list).findByText('☑ 1/2')).toBeInTheDocument()
    expect(within(list).getByText('En attente')).toBeInTheDocument()
    // Les sous-tâches ne sont pas des lignes de la liste : elles restent dans leur tâche.
    expect(within(list).queryByText('Imprimer les cartons')).not.toBeInTheDocument()

    await user.click(within(list).getByRole('button', { name: 'Envoyer les invitations' }))
    const dialog = await screen.findByRole('dialog', { name: 'Envoyer les invitations' })
    expect(within(dialog).getByText('1 sur 2')).toBeInTheDocument()
    expect(within(dialog).getByRole('status')).toHaveTextContent(
      'En attente de la fin de « Signer le lieu »',
    )
    expect(within(dialog).getByText('@Moussa Diop', { selector: 'mark' })).toBeInTheDocument()
    expect(within(dialog).getByRole('button', { name: '✓ Abonné' })).toHaveAttribute(
      'aria-pressed',
      'true',
    )

    await user.keyboard('{Escape}')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('mentionne un membre avec @ et envoie sa mention', async () => {
    const calls = mockApi(
      routes({ [`POST ${base}/tasks/t1/comments`]: () => ({ status: 201, json: detail }) }),
    )
    renderApp(`/espaces/${SPACE_ID}/projets/pr1?tache=t1`)
    const user = userEvent.setup()

    const dialog = await screen.findByRole('dialog', { name: 'Envoyer les invitations' })
    const field = within(dialog).getByRole('combobox', { name: 'Nouveau commentaire' })
    await user.type(field, 'Merci @mou')
    await user.click(await within(dialog).findByRole('option', { name: /Moussa Diop/ }))
    await user.type(field, 'pour le suivi')
    expect(field).toHaveValue('Merci @Moussa Diop pour le suivi')

    await user.click(within(dialog).getByRole('button', { name: 'Publier' }))
    expect(calls.find((c) => c.key === `POST ${base}/tasks/t1/comments`)?.body).toEqual({
      body: 'Merci @Moussa Diop pour le suivi',
      mentions: ['m2'],
    })
  })
})

describe('bouton « + Sous-tâche »', () => {
  it('ouvre la tâche directement sur la case des sous-tâches', async () => {
    const calls = mockApi(
      routes({
        [`POST ${base}/tasks/t1/subtasks`]: () => ({
          status: 201,
          json: task('s3', 'Acheter les timbres', { parent_id: 't1' }),
        }),
      }),
    )
    renderApp(`/espaces/${SPACE_ID}/projets/pr1`)
    const user = userEvent.setup()

    const list = await screen.findByRole('region', { name: /^Tâches/ })
    await user.click(
      await within(list).findByRole('button', {
        name: 'Ajouter une sous-tâche à « Envoyer les invitations »',
      }),
    )
    const dialog = await screen.findByRole('dialog', { name: 'Envoyer les invitations' })
    const field = within(dialog).getByRole('textbox', { name: 'Nouvelle sous-tâche' })
    expect(field).toHaveFocus()

    await user.type(field, 'Acheter les timbres{Enter}')
    expect(calls.find((c) => c.key === `POST ${base}/tasks/t1/subtasks`)?.body).toEqual({
      title: 'Acheter les timbres',
    })
  })

  it('règle la répétition et montre les fichiers joints', async () => {
    const repeated = {
      ...detail,
      task: { ...detail.task, due_date: '2026-11-16', recurrence: 'weekly', documents_count: 1 },
      documents: [
        {
          id: 'd1',
          project_id: 'pr1',
          project_title: 'Salon Agri 2026',
          filename: 'devis.pdf',
          content_type: 'application/pdf',
          size_bytes: 2048,
          uploaded_by: 'Aïcha Ndiaye',
          created_at: '2026-11-08T09:00:00Z',
          archived: false,
          revision: 1,
          replaced_at: null,
          task_id: 't1',
          task_title: 'Envoyer les invitations',
        },
      ],
    }
    const calls = mockApi(
      routes({
        [`GET ${base}/tasks/t1`]: () => ({ status: 200, json: repeated }),
        [`PATCH ${base}/tasks/t1`]: () => ({ status: 200, json: repeated.task }),
      }),
    )
    renderApp(`/espaces/${SPACE_ID}/projets/pr1?tache=t1`)
    const user = userEvent.setup()

    const dialog = await screen.findByRole('dialog', { name: 'Envoyer les invitations' })
    expect(within(dialog).getByText(/Chaque semaine/)).toBeInTheDocument()
    expect(within(dialog).getByText('devis.pdf')).toBeInTheDocument()
    expect(within(dialog).getByText('📎 Joindre un fichier')).toBeInTheDocument()

    await user.click(within(dialog).getByRole('button', { name: 'Modifier la tâche' }))
    await user.selectOptions(within(dialog).getByLabelText('Répéter'), 'monthly')
    await user.click(within(dialog).getByRole('button', { name: 'Enregistrer' }))
    const patch = calls.find((c) => c.key === `PATCH ${base}/tasks/t1`)
    expect(patch?.body).toMatchObject({ recurrence: 'monthly', due_date: '2026-11-16' })
  })
})
