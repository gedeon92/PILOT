import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { meWith, mockApi, OWNER_MEMBER, renderApp, SPACE_ID, spaceWith } from '../test-utils'

/** Étape F3 : registre des décisions et relevés de réunion. */

const base = `/api/spaces/${SPACE_ID}`

afterEach(() => {
  vi.unstubAllGlobals()
})

const person = (name: string | null, member: string | null = null) => ({
  member_id: member,
  name,
  has_account: Boolean(member),
})

function decision(id: string, extra: Record<string, unknown> = {}) {
  return {
    id,
    statement: 'Envoyer le devis au client',
    project: null,
    meeting: null,
    source: null,
    decider: person(null),
    executor: person('Aïcha Ndiaye', 'm1'),
    executor_accepted: false,
    due_date: '2026-11-20',
    criterion: 'Devis envoyé et accusé de réception',
    private: false,
    state: 'open',
    proof: null,
    cancel_reason: null,
    closed_at: null,
    created_at: '2026-11-10T10:00:00Z',
    missing: [],
    late: false,
    reminder_on: '2026-11-15',
    orphan_days: 0,
    is_executor: true,
    can_write: true,
    tasks: [],
    version: 1,
    ...extra,
  }
}

const meeting = {
  id: 'mt1',
  title: 'Comité du lundi',
  project: null,
  ended_at: '2026-11-09T10:00:00Z',
  participants: null,
  minutes_state: 'validated',
  minutes_due_at: '2026-11-10T10:00:00Z',
  minutes_late: true,
  minutes_sent_at: null,
  minutes_channel: null,
  minutes_recipients: null,
  minutes_url: null,
  decisions_count: 1,
  version: 2,
}

function routes(decisions: unknown[], extra = {}) {
  return {
    'GET /api/auth/me': () => ({ status: 200, json: meWith('owner') }),
    [`GET ${base}`]: () => ({ status: 200, json: spaceWith('owner') }),
    [`GET ${base}/members`]: () => ({ status: 200, json: [OWNER_MEMBER] }),
    [`GET ${base}/portfolios`]: () => ({ status: 200, json: [] }),
    [`GET ${base}/alerts`]: () => ({ status: 200, json: { unread: 0, items: [] } }),
    [`GET ${base}/projects`]: () => ({ status: 200, json: [] }),
    [`GET ${base}/decisions`]: () => ({ status: 200, json: decisions }),
    [`GET ${base}/meetings`]: () => ({ status: 200, json: [meeting] }),
    ...extra,
  }
}

describe('registre des décisions', () => {
  it('montre ce qui manque à un brouillon et laisse le responsable accepter', async () => {
    const calls = mockApi(
      routes(
        [
          decision('d1', {
            statement: 'Améliorer la coordination',
            state: 'draft',
            executor: person('L’équipe'),
            is_executor: false,
            missing: ['un responsable nommé', 'un critère observable'],
            reminder_on: null,
          }),
          decision('d2'),
        ],
        {
          [`POST ${base}/decisions/d2/accept`]: () => ({
            status: 200,
            json: decision('d2', { executor_accepted: true, orphan_days: null, version: 2 }),
          }),
        },
      ),
    )
    renderApp(`/espaces/${SPACE_ID}/decisions`)
    const user = userEvent.setup()

    const draft = (await screen.findByText('Améliorer la coordination')).closest(
      'li',
    ) as HTMLElement
    expect(
      within(draft).getByText(
        'Pour valider, il manque : un responsable nommé, un critère observable.',
      ),
    ).toBeInTheDocument()
    expect(within(draft).getByRole('button', { name: 'Valider' })).toBeDisabled()

    const mine = screen.getByText('Envoyer le devis au client').closest('li') as HTMLElement
    expect(within(mine).getByText(/relance le/)).toBeInTheDocument()
    await user.click(within(mine).getByRole('button', { name: 'J’accepte cette responsabilité' }))
    expect(calls.some((c) => c.key === `POST ${base}/decisions/d2/accept`)).toBe(true)
  })

  it('déclare l’envoi d’un relevé en retard avec son canal', async () => {
    const calls = mockApi(
      routes([], {
        [`PATCH ${base}/meetings/mt1`]: () => ({
          status: 200,
          json: { ...meeting, minutes_state: 'sent', minutes_late: false, version: 3 },
        }),
      }),
    )
    renderApp(`/espaces/${SPACE_ID}/decisions?vue=meetings`)
    const user = userEvent.setup()
    const card = (await screen.findByText('Comité du lundi')).closest('li') as HTMLElement
    expect(within(card).getByText('Délai de 24 h dépassé')).toBeInTheDocument()
    await user.click(within(card).getByRole('button', { name: 'Déclarer envoyé' }))
    await user.type(within(card).getByLabelText('Canal'), 'E-mail')
    await user.type(within(card).getByLabelText('Destinataires'), 'Comité de direction')
    await user.click(within(card).getAllByRole('button', { name: 'Déclarer envoyé' })[0])
    expect(calls.find((c) => c.key === `PATCH ${base}/meetings/mt1`)?.body).toEqual({
      version: 2,
      minutes_state: 'sent',
      minutes_channel: 'E-mail',
      minutes_recipients: 'Comité de direction',
      minutes_url: null,
    })
  })
})
