import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { meWith, mockApi, OWNER_MEMBER, renderApp, SPACE_ID, spaceWith } from '../test-utils'

const base = `/api/spaces/${SPACE_ID}`

afterEach(() => {
  vi.unstubAllGlobals()
})

function routes(role: 'owner' | 'reader') {
  return {
    'GET /api/auth/me': () => ({ status: 200, json: meWith(role) }),
    [`GET ${base}`]: () => ({ status: 200, json: spaceWith(role) }),
    [`GET ${base}/members`]: () => ({ status: 200, json: [OWNER_MEMBER] }),
    [`GET ${base}/portfolios`]: () => ({ status: 200, json: [] }),
    [`GET ${base}/alerts`]: () => ({ status: 200, json: { unread: 0, items: [] } }),
    [`GET ${base}/projects`]: () => ({
      status: 200,
      json: [
        { id: 'pr1', title: 'Atlas' },
        { id: 'pr2', title: 'Orion' },
      ],
    }),
    [`GET ${base}/documents`]: () => ({ status: 200, json: [] }),
  }
}

describe('page Documents', () => {
  it('ajoute un PDF dans le projet choisi', async () => {
    const calls = mockApi({
      ...routes('owner'),
      [`POST ${base}/projects/pr2/documents`]: () => ({ status: 201, json: { id: 'd1' } }),
    })
    renderApp(`/espaces/${SPACE_ID}/documents`)
    const user = userEvent.setup()

    await screen.findByRole('option', { name: 'Orion' })
    await user.selectOptions(screen.getByRole('combobox', { name: 'Projet' }), 'pr2')
    const pdf = new File(['%PDF-1.4'], 'rapport.pdf', { type: 'application/pdf' })
    await user.upload(screen.getByLabelText('Choisir les fichiers'), pdf)

    expect(await screen.findByText('Enregistré')).toBeInTheDocument()
    const sent = calls.find((c) => c.key === `POST ${base}/projects/pr2/documents`)
      ?.body as FormData
    expect((sent.get('file') as File).name).toBe('rapport.pdf')
  })

  it('ne propose pas l’ajout aux lecteurs', async () => {
    mockApi(routes('reader'))
    renderApp(`/espaces/${SPACE_ID}/documents`)

    expect(await screen.findByText('Aucun document pour l’instant.')).toBeInTheDocument()
    expect(screen.queryByText('Choisir les fichiers')).not.toBeInTheDocument()
  })
})
