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

/** Étape F1 : tâches rangées par sections, priorités, statuts et reports. */

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
    postpone_count: 0,
    ...extra,
  }
}

const section = (id: string, title: string, position: number, archived = false) => ({
  id,
  project_id: 'pr1',
  title,
  description: null,
  position,
  archived,
  version: 1,
})

function routes(tasks: unknown[], sections: unknown[], extra = {}) {
  return {
    'GET /api/auth/me': () => ({ status: 200, json: meWith('owner') }),
    [`GET ${base}`]: () => ({ status: 200, json: { ...spaceWith('owner'), advanced_mode: true } }),
    [`GET ${base}/members`]: () => ({ status: 200, json: [OWNER_MEMBER] }),
    [`GET ${base}/portfolios`]: () => ({ status: 200, json: [] }),
    [`GET ${base}/alerts`]: () => ({ status: 200, json: { unread: 0, items: [] } }),
    [`GET ${base}/projects`]: () => ({ status: 200, json: [projectFixture()] }),
    [`GET ${base}/projects/pr1`]: () => ({ status: 200, json: projectFixture() }),
    [`GET ${base}/projects/pr1/tasks`]: () => ({ status: 200, json: tasks }),
    [`GET ${base}/projects/pr1/sections`]: () => ({ status: 200, json: sections }),
    [`GET ${base}/projects/pr1/history`]: () => ({ status: 200, json: [] }),
    [`GET ${base}/projects/pr1/documents`]: () => ({ status: 200, json: [] }),
    [`GET ${base}/projects/pr1/links`]: () => ({ status: 200, json: [] }),
    ...extra,
  }
}

describe('sections d’un projet', () => {
  it('range les tâches par section, garde les retards visibles une fois repliée', async () => {
    const calls = mockApi(
      routes(
        [
          task('t1', 'Fixer l’objectif', { section_id: 's1', priority: 'urgent' }),
          task('t2', 'Réserver la salle', {
            section_id: 's2',
            late: true,
            due_date: '2026-11-01',
            postpone_count: 2,
            original_due_date: '2026-10-20',
          }),
          task('t3', 'Bloquée par le devis', { section_id: 's2', status: 'blocked' }),
          task('t4', 'Ranger plus tard'),
        ],
        [
          section('s1', 'Cadrage', 1),
          section('s2', 'Préparation', 2),
          section('s3', 'Bilan', 3, true),
        ],
        {
          [`PUT ${base}/projects/pr1/sections/order`]: () => ({ status: 200, json: [] }),
        },
      ),
    )
    renderApp(`/espaces/${SPACE_ID}/projets/pr1`)
    const user = userEvent.setup()

    const prep = await screen.findByRole('region', { name: 'Préparation' })
    expect(within(prep).getByText('Réserver la salle')).toBeInTheDocument()
    expect(within(prep).getByText('↷ Reportée 2 fois')).toBeInTheDocument()
    expect(within(prep).getByText('⛔ Bloquée')).toBeInTheDocument()
    const cadrage = screen.getByRole('region', { name: 'Cadrage' })
    expect(within(cadrage).getByText('⚡ Urgente')).toBeInTheDocument()
    expect(
      within(screen.getByRole('region', { name: 'Tâches sans section' })).getByText(
        'Ranger plus tard',
      ),
    ).toBeInTheDocument()
    expect(screen.getByText('1 section(s) archivée(s)')).toBeInTheDocument()

    // Repliée : les tâches disparaissent, mais pas le signal du retard et du blocage.
    await user.click(within(prep).getByRole('button', { expanded: true }))
    expect(within(prep).queryByText('Réserver la salle')).not.toBeInTheDocument()
    expect(within(prep).getByText('1 en retard')).toBeInTheDocument()
    expect(within(prep).getByText('1 bloquée(s)')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Monter la section « Préparation »' }))
    expect(calls.find((c) => c.key === `PUT ${base}/projects/pr1/sections/order`)?.body).toEqual({
      ids: ['s2', 's1'],
    })
  })

  it('propose les sections types quand le projet n’en a pas', async () => {
    const calls = mockApi(
      routes([task('t1', 'Une tâche')], [], {
        [`POST ${base}/projects/pr1/sections/defaults`]: () => ({ status: 201, json: [] }),
      }),
    )
    renderApp(`/espaces/${SPACE_ID}/projets/pr1`)
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Sections types' }))
    expect(calls.some((c) => c.key === `POST ${base}/projects/pr1/sections/defaults`)).toBe(true)
  })

  it('demande un motif quand l’échéance est repoussée', async () => {
    const t = task('t1', 'Imprimer', { due_date: '2026-12-01' })
    const calls = mockApi(
      routes([t], [], {
        [`GET ${base}/tasks/t1`]: () => ({
          status: 200,
          json: {
            task: t,
            project_title: 'Atlas',
            parent: null,
            subtasks: [],
            depends_on: [],
            blocking: [],
            comments: [],
            followers: [],
            following: false,
            can_write: true,
            project_closed: false,
            documents: [],
          },
        }),
        [`PATCH ${base}/tasks/t1`]: (body: unknown) => ({
          status: 200,
          json: { ...t, ...(body as object), version: 2, postpone_count: 1 },
        }),
      }),
    )
    renderApp(`/espaces/${SPACE_ID}/projets/pr1?tache=t1`)
    const user = userEvent.setup()
    const dialog = await screen.findByRole('dialog')
    await user.click(await within(dialog).findByRole('button', { name: 'Modifier la tâche' }))
    expect(within(dialog).queryByLabelText('Motif du report *')).not.toBeInTheDocument()
    const due = within(dialog).getByLabelText('Échéance')
    await user.clear(due)
    await user.type(due, '2026-12-08')
    const reason = within(dialog).getByLabelText('Motif du report *')
    await user.type(reason, 'Devis tardif')
    await user.selectOptions(within(dialog).getByLabelText('Priorité'), 'high')
    await user.click(within(dialog).getByRole('button', { name: 'Enregistrer' }))
    const sent = calls.find((c) => c.key === `PATCH ${base}/tasks/t1`)?.body as Record<
      string,
      unknown
    >
    expect(sent).toMatchObject({
      due_date: '2026-12-08',
      postpone_reason: 'Devis tardif',
      priority: 'high',
    })
  })
})
