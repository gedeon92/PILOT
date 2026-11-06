import { screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { meWith, mockApi, OWNER_MEMBER, renderApp, SPACE_ID, spaceWith } from '../test-utils'

const base = `/api/spaces/${SPACE_ID}`

afterEach(() => {
  vi.unstubAllGlobals()
})

function project(id: string, title: string, dates: Record<string, string | null> = {}) {
  return {
    id,
    title,
    status: 'in_progress',
    kind: 'standard',
    portfolio: { id: 'p1', name: 'Projets groupe', color: 'blue' },
    entity: null,
    owner: { member_id: null, name: null, has_account: false },
    start_date: null,
    end_date: null,
    due_date: null,
    window_start: null,
    window_end: null,
    open_tasks: 0,
    late_tasks: 0,
    version: 1,
    ...dates,
  }
}

describe('timeline', () => {
  it('liste à part les projets sans date', async () => {
    mockApi({
      'GET /api/auth/me': () => ({ status: 200, json: meWith('owner') }),
      [`GET ${base}`]: () => ({ status: 200, json: spaceWith('owner') }),
      [`GET ${base}/members`]: () => ({ status: 200, json: [OWNER_MEMBER] }),
      [`GET ${base}/portfolios`]: () => ({ status: 200, json: [] }),
      [`GET ${base}/entities`]: () => ({ status: 200, json: [] }),
      [`GET ${base}/alerts`]: () => ({ status: 200, json: { unread: 0, items: [] } }),
      [`GET ${base}/tasks`]: () => ({ status: 200, json: [] }),
      [`GET ${base}/projects`]: () => ({
        status: 200,
        json: [
          project('pr1', 'Atlas', { due_date: '2026-11-20' }),
          project('pr2', 'Orion'),
          { ...project('pr3', 'Vega'), status: 'cancelled' },
        ],
      }),
    })
    renderApp(`/espaces/${SPACE_ID}/timeline`)

    const list = await screen.findByRole('region', { name: /Projets sans date/ })
    expect(within(list).getByRole('link', { name: 'Orion' })).toHaveAttribute(
      'href',
      `/espaces/${SPACE_ID}/projets/pr2`,
    )
    expect(within(list).queryByText('Atlas')).not.toBeInTheDocument()
    expect(within(list).queryByText('Vega')).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: '1 sans date' })).toBeInTheDocument()
  })
})
