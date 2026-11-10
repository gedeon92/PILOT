import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { meWith, mockApi, OWNER_MEMBER, renderApp, SPACE_ID, spaceWith } from '../test-utils'

const base = `/api/spaces/${SPACE_ID}`

afterEach(() => {
  vi.unstubAllGlobals()
})

const action = {
  id: 'a1',
  kind: 'create_task',
  summary: 'Créer la tâche « Réserver la salle » dans le projet « Salon Agri »',
  changes: [
    { field: 'Titre', before: '', after: 'Réserver la salle' },
    { field: 'Échéance', before: '', after: '01/12/2026' },
  ],
  state: 'pending',
  result: null as string | null,
  project_id: 'pr1',
  task_id: null,
}

const conversation = {
  id: 'c1',
  title: 'Ajoute une tâche',
  status: 'idle',
  updated_at: '2026-11-10T10:00:00Z',
  turns: [
    { role: 'user', text: 'Ajoute une tâche', at: '2026-11-10T10:00:00Z', actions: [] },
    {
      role: 'assistant',
      text: 'Je vous propose **une tâche** :\n\n- Réserver la salle',
      at: '2026-11-10T10:00:05Z',
      actions: [action],
    },
  ],
}

function routes(extra: Record<string, (body: unknown) => { status: number; json?: unknown }>) {
  return {
    'GET /api/auth/me': () => ({ status: 200, json: meWith('owner') }),
    [`GET ${base}`]: () => ({ status: 200, json: spaceWith('owner') }),
    [`GET ${base}/members`]: () => ({ status: 200, json: [OWNER_MEMBER] }),
    [`GET ${base}/portfolios`]: () => ({ status: 200, json: [] }),
    [`GET ${base}/alerts`]: () => ({ status: 200, json: { unread: 0, items: [] } }),
    [`GET ${base}/projects`]: () => ({ status: 200, json: [] }),
    [`GET ${base}/updates`]: () => ({ status: 200, json: [] }),
    [`GET ${base}/ai/conversations`]: () => ({ status: 200, json: [] }),
    ...extra,
  }
}

const statusOn = {
  available: true,
  enabled: true,
  can_toggle: true,
  daily_limit: 60,
  used_today: 0,
}

describe('assistant IA dans « Mises à jour »', () => {
  it('envoie une demande, montre la proposition et ne l’applique qu’au clic', async () => {
    let current: typeof conversation = conversation
    const applied = { ...action, state: 'applied', result: 'Tâche « Réserver la salle » créée.' }
    const calls = mockApi(
      routes({
        [`GET ${base}/ai/status`]: () => ({ status: 200, json: statusOn }),
        [`POST ${base}/ai/conversations`]: () => ({ status: 201, json: current }),
        [`GET ${base}/ai/conversations/c1`]: () => ({ status: 200, json: current }),
        [`POST ${base}/ai/actions/a1/apply`]: () => {
          current = {
            ...conversation,
            turns: [conversation.turns[0], { ...conversation.turns[1], actions: [applied] }],
          }
          return { status: 200, json: applied }
        },
      }),
    )
    renderApp(`/espaces/${SPACE_ID}/mises-a-jour`)
    const user = userEvent.setup()

    await user.type(
      await screen.findByLabelText('Votre message à l’assistant'),
      'Ajoute une tâche{Enter}',
    )
    expect(calls.find((c) => c.key === `POST ${base}/ai/conversations`)?.body).toEqual({
      text: 'Ajoute une tâche',
    })

    const card = (await screen.findByText(action.summary)).closest('article') as HTMLElement
    expect(within(card).getByText('À valider')).toBeInTheDocument()
    expect(within(card).getByText('01/12/2026')).toBeInTheDocument()
    expect(screen.getByText('une tâche').tagName).toBe('STRONG')
    expect(calls.some((c) => c.key.endsWith('/apply'))).toBe(false)

    await user.click(within(card).getByRole('button', { name: 'Appliquer' }))
    expect(await within(card).findByText('Appliquée')).toBeInTheDocument()
    expect(within(card).getByText('Tâche « Réserver la salle » créée.')).toBeInTheDocument()
    expect(within(card).queryByRole('button', { name: 'Appliquer' })).not.toBeInTheDocument()
  })

  it('assistant éteint : le propriétaire est guidé vers les Paramètres', async () => {
    mockApi(
      routes({
        [`GET ${base}/ai/status`]: () => ({ status: 200, json: { ...statusOn, enabled: false } }),
      }),
    )
    renderApp(`/espaces/${SPACE_ID}/mises-a-jour`)
    const user = userEvent.setup()
    // Éteint : la page s'ouvre sur la saisie de texte habituelle, avec l'onglet de l'assistant.
    await user.click(await screen.findByRole('button', { name: '✨ Assistant IA' }))
    expect(await screen.findByText(/L’assistant est éteint pour cet espace/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Paramètres → Assistant IA' })).toBeInTheDocument()
  })
})
