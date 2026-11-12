import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { todayIso } from '../labels'
import { meWith, mockApi, OWNER_MEMBER, renderApp, SPACE_ID, spaceWith } from '../test-utils'

/** Jours fériés de l'espace et temps déclaré. */

const base = `/api/spaces/${SPACE_ID}`
const today = todayIso('Europe/Paris')

afterEach(() => {
  vi.unstubAllGlobals()
})

function routes(extra = {}) {
  return {
    'GET /api/auth/me': () => ({ status: 200, json: meWith('owner') }),
    [`GET ${base}`]: () => ({
      status: 200,
      json: { ...spaceWith('owner'), advanced_mode: true, timezone: 'Europe/Paris' },
    }),
    [`GET ${base}/members`]: () => ({ status: 200, json: [OWNER_MEMBER] }),
    [`GET ${base}/alerts`]: () => ({ status: 200, json: { unread: 0, items: [] } }),
    [`GET ${base}/projects`]: () => ({ status: 200, json: [] }),
    ...extra,
  }
}

describe('jours fériés et temps déclaré', () => {
  it('déclare du temps stratégique dans Ma journée', async () => {
    const calls = mockApi(
      routes({
        [`GET ${base}/agenda`]: () => ({
          status: 200,
          json: { start: today, end: today, today, items: [], occurrences: [] },
        }),
        [`GET ${base}/time-entries`]: () => ({
          status: 200,
          json: {
            start: today,
            end: today,
            entries: [
              {
                id: 'te1',
                day: today,
                minutes: 90,
                category: 'strategic',
                note: 'Revue du portefeuille',
                project_id: null,
              },
            ],
            total_minutes: 120,
            strategic_minutes: 90,
          },
        }),
        [`POST ${base}/time-entries`]: () => ({
          status: 201,
          json: { start: today, end: today, entries: [], total_minutes: 0, strategic_minutes: 0 },
        }),
      }),
    )
    renderApp(`/espaces/${SPACE_ID}/ma-journee`)
    const user = userEvent.setup()
    expect(
      await screen.findByText(/2 h déclarées · dont 1 h 30 stratégiques \(75 %\)/),
    ).toBeInTheDocument()
    await user.clear(screen.getByLabelText('Heures'))
    await user.type(screen.getByLabelText('Heures'), '1.5')
    await user.selectOptions(screen.getByLabelText('Type'), 'coordination')
    await user.click(screen.getByRole('button', { name: 'Ajouter' }))
    expect(calls.find((c) => c.key === `POST ${base}/time-entries`)?.body).toEqual({
      day: today,
      minutes: 90,
      category: 'coordination',
      note: null,
    })
  })
})
