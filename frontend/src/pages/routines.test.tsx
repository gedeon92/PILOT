import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { meWith, mockApi, OWNER_MEMBER, renderApp, SPACE_ID, spaceWith } from '../test-utils'
import { todayIso } from '../labels'

/** Étape F5 : « Ma journée » et les routines. */

const base = `/api/spaces/${SPACE_ID}`

afterEach(() => {
  vi.unstubAllGlobals()
})

const today = todayIso('Europe/Paris')

function occurrence(extra: Record<string, unknown> = {}) {
  return {
    id: 'o1',
    routine_id: 'r1',
    routine_title: 'Clore ma journée',
    time_of_day: '17:30',
    duration_minutes: 10,
    scheduled_date: today,
    due_date: today,
    postponed: false,
    postpone_reason: null,
    state: 'planned',
    late: false,
    owner: { member_id: OWNER_MEMBER.id, name: 'Raissa', has_account: true },
    checklist: [
      { id: 'c1', label: 'Décisions nouvelles consignées', mandatory: true },
      { id: 'c2', label: 'Lendemain préparé', mandatory: false },
    ],
    checks: {},
    missing_mandatory: ['Décisions nouvelles consignées'],
    result: null,
    expected_output: 'Aucun sujet sans suite',
    exception_reason: null,
    cancel_reason: null,
    links: [],
    version: 1,
    ...extra,
  }
}

function routes(advanced: boolean, extra = {}) {
  return {
    'GET /api/auth/me': () => ({ status: 200, json: meWith('owner') }),
    [`GET ${base}`]: () => ({
      status: 200,
      json: { ...spaceWith('owner'), advanced_mode: advanced, timezone: 'Europe/Paris' },
    }),
    [`GET ${base}/members`]: () => ({ status: 200, json: [OWNER_MEMBER] }),
    [`GET ${base}/alerts`]: () => ({ status: 200, json: { unread: 0, items: [] } }),
    [`GET ${base}/projects`]: () => ({ status: 200, json: [] }),
    ...extra,
  }
}

describe('ma journée et routines', () => {
  it('montre les tâches en retard et la routine du jour, clôturée avec exception', async () => {
    const calls = mockApi(
      routes(true, {
        [`GET ${base}/agenda`]: () => ({
          status: 200,
          json: {
            start: today,
            end: today,
            today,
            items: [
              {
                kind: 'task',
                id: 't1',
                title: 'Envoyer le devis',
                project_id: 'pr1',
                project_title: 'Atlas',
                due_date: '2026-01-05',
                late: true,
                detail: null,
              },
            ],
            occurrences: [occurrence()],
          },
        }),
        [`POST ${base}/routine-occurrences/o1/close`]: () => ({
          status: 200,
          json: occurrence({ state: 'done', exception_reason: 'Réunion annulée' }),
        }),
      }),
    )
    renderApp(`/espaces/${SPACE_ID}/ma-journee`)
    const user = userEvent.setup()
    expect(await screen.findByRole('button', { name: 'Envoyer le devis' })).toBeInTheDocument()
    expect(screen.getByText('En retard')).toBeInTheDocument()
    const card = screen.getByRole('article', { name: 'Clore ma journée' })
    await user.click(within(card).getByRole('button', { name: /Clore ma journée/ }))
    await user.click(within(card).getByRole('button', { name: 'Clôturer' }))
    expect(within(card).getByText(/Contrôles obligatoires non faits/)).toBeInTheDocument()
    await user.type(within(card).getByLabelText('Motif de l’exception'), 'Réunion annulée')
    await user.click(within(card).getByRole('button', { name: 'Clôturer comme faite' }))
    expect(calls.find((c) => c.key === `POST ${base}/routine-occurrences/o1/close`)?.body).toEqual({
      version: 1,
      state: 'done',
      result: null,
      exception_reason: 'Réunion annulée',
    })
  })

  it('ajoute des routines types choisies', async () => {
    const calls = mockApi(
      routes(true, {
        [`GET ${base}/routines`]: () => ({ status: 200, json: [] }),
        [`GET ${base}/routines/profiles`]: () => ({
          status: 200,
          json: [
            {
              key: 'point_dirigeant',
              title: 'Préparer le point dirigeant',
              purpose: 'Trois alertes, arbitrages.',
              frequency: 'weekly',
              weekdays: [0],
              month_days: [],
              time_of_day: null,
              duration_minutes: 45,
              checklist: [],
              already_added: false,
            },
          ],
        }),
        [`POST ${base}/routines/profiles`]: () => ({ status: 201, json: [] }),
      }),
    )
    renderApp(`/espaces/${SPACE_ID}/routines`)
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Routines types' }))
    await user.click(await screen.findByLabelText(/Préparer le point dirigeant/))
    expect(screen.getByText(/Chaque semaine · Lun · 45 min/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Ajouter 1 routine/ }))
    expect(calls.find((c) => c.key === `POST ${base}/routines/profiles`)?.body).toEqual({
      keys: ['point_dirigeant'],
    })
  })

  it('n’apparaît pas dans le menu en mode simple', async () => {
    mockApi(routes(false, { [`GET ${base}/projects`]: () => ({ status: 200, json: [] }) }))
    renderApp(`/espaces/${SPACE_ID}/projets`)
    expect(await screen.findByRole('link', { name: 'Projets' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Ma journée' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Routines' })).not.toBeInTheDocument()
  })
})
