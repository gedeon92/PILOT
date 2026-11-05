import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { meWith, mockApi, OWNER_MEMBER, renderApp, SPACE_ID, spaceWith } from '../test-utils'

const base = `/api/spaces/${SPACE_ID}`

afterEach(() => {
  vi.unstubAllGlobals()
})

const proposal = {
  id: 'pp1',
  state: 'to_validate',
  project: { id: 'pr1', title: 'Atlas', detail: 'Projets groupe' },
  candidates: [],
  source_label: 'Message',
  excerpt: 'Projet Atlas — Statut : en cours. Avancement : 40 %',
  changes: [
    {
      field: 'status',
      label: 'Statut',
      current: 'À cadrer',
      proposed: 'En cours',
      excerpt: 'Statut : en cours',
      unchanged: false,
    },
    {
      field: 'progress',
      label: 'Avancement',
      current: null,
      proposed: '40 %',
      excerpt: 'Avancement : 40 %',
      unchanged: false,
    },
  ],
  issues: [],
  base_version: 3,
  applied_fields: [],
  decided_by: null,
  decided_at: null,
  discard_reason: null,
}

const request = {
  id: 'rq1',
  created_at: '2026-11-05T10:00:00Z',
  author_name: 'Aïcha',
  mine: true,
  visibility: 'private',
  message: 'Projet Atlas — Statut : en cours. Avancement : 40 %',
  sources: [],
  proposals: [proposal],
  notes: ['« Orion » : Date relative « vendredi » non convertie.'],
}

describe('boîte de mise à jour', () => {
  it('analyse un message, résume le résultat et applique seulement les champs cochés', async () => {
    let listed: unknown[] = []
    const calls = mockApi({
      'GET /api/auth/me': () => ({ status: 200, json: meWith('owner') }),
      [`GET ${base}`]: () => ({ status: 200, json: spaceWith('owner') }),
      [`GET ${base}/members`]: () => ({ status: 200, json: [OWNER_MEMBER] }),
      [`GET ${base}/portfolios`]: () => ({ status: 200, json: [] }),
      [`GET ${base}/alerts`]: () => ({ status: 200, json: { unread: 0, items: [] } }),
      [`GET ${base}/projects`]: () => ({ status: 200, json: [] }),
      [`GET ${base}/updates`]: () => ({ status: 200, json: listed }),
      [`POST ${base}/updates`]: () => {
        listed = [request]
        return { status: 201, json: request }
      },
      [`POST ${base}/proposals/pp1/apply`]: () => ({
        status: 200,
        json: { ...proposal, state: 'applied', applied_fields: ['status'] },
      }),
    })
    renderApp(`/espaces/${SPACE_ID}/mises-a-jour`)
    const user = userEvent.setup()

    expect(await screen.findByText('Rien à traiter.')).toBeInTheDocument()
    await user.type(screen.getByLabelText('Message'), 'Projet Atlas — Statut : en cours')
    await user.click(screen.getByRole('button', { name: 'Analyser' }))

    const sent = calls.find((c) => c.key === `POST ${base}/updates`)?.body as FormData
    expect(sent.get('message')).toBe('Projet Atlas — Statut : en cours')
    expect(sent.get('visibility')).toBe('private')

    const summary = await screen.findByRole('region', { name: 'Résultat de l’analyse' })
    expect(within(summary).getByText(/1 proposition : 1 à valider/)).toBeInTheDocument()
    expect(within(summary).getByText(/aucune modification n’est appliquée/)).toBeInTheDocument()
    expect(await screen.findByText(/Date relative « vendredi »/)).toBeInTheDocument()

    await user.click(screen.getByRole('checkbox', { name: 'Avancement' }))
    await user.click(screen.getByRole('button', { name: 'Appliquer 1 modification' }))
    expect(calls.find((c) => c.key === `POST ${base}/proposals/pp1/apply`)?.body).toEqual({
      fields: ['status'],
      base_version: 3,
    })
  })

  it('reste fermée aux lecteurs', async () => {
    mockApi({
      'GET /api/auth/me': () => ({ status: 200, json: meWith('reader') }),
      [`GET ${base}`]: () => ({ status: 200, json: spaceWith('reader') }),
      [`GET ${base}/members`]: () => ({ status: 200, json: [OWNER_MEMBER] }),
      [`GET ${base}/portfolios`]: () => ({ status: 200, json: [] }),
      [`GET ${base}/alerts`]: () => ({ status: 200, json: { unread: 0, items: [] } }),
      [`GET ${base}/projects`]: () => ({ status: 200, json: [] }),
    })
    renderApp(`/espaces/${SPACE_ID}/mises-a-jour`)

    expect(await screen.findByText(/rôle de lecteur/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Analyser' })).not.toBeInTheDocument()
  })
})
