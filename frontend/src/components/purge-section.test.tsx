import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createQueryClient } from '../api/query-client'
import { mockApi, projectFixture, SPACE_ID } from '../test-utils'
import { PurgeSection } from './purge-section'

/** Zone sensible : suppression définitive, seulement après le mot SUPPRIMER. */

const base = `/api/spaces/${SPACE_ID}`

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('suppression définitive de projets', () => {
  it('reste bloquée tant que rien n’est coché et que SUPPRIMER n’est pas tapé', async () => {
    const calls = mockApi({
      [`GET ${base}/projects`]: () => ({
        status: 200,
        json: [projectFixture(), projectFixture({ id: 'pr2', title: 'Essai 2' })],
      }),
      [`POST ${base}/projects/purge`]: () => ({
        status: 200,
        json: { deleted: 2, titles: ['Atlas', 'Essai 2'] },
      }),
    })
    render(
      <QueryClientProvider client={createQueryClient({ retry: false })}>
        <PurgeSection spaceId={SPACE_ID} />
      </QueryClientProvider>,
    )
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Supprimer définitivement des projets…' }))
    await user.click(await screen.findByLabelText('Tout sélectionner'))
    const go = screen.getByRole('button', { name: 'Supprimer définitivement 2 projet(s)' })
    expect(go).toBeDisabled()
    await user.type(screen.getByLabelText('Pour confirmer, tapez SUPPRIMER'), 'supprimer')
    expect(go).toBeDisabled()
    await user.clear(screen.getByLabelText('Pour confirmer, tapez SUPPRIMER'))
    await user.type(screen.getByLabelText('Pour confirmer, tapez SUPPRIMER'), 'SUPPRIMER')
    expect(go).toBeEnabled()
    await user.click(go)
    expect(calls.find((c) => c.key === `POST ${base}/projects/purge`)?.body).toEqual({
      project_ids: ['pr1', 'pr2'],
      confirm: 'SUPPRIMER',
    })
    expect(await screen.findByText(/2 projet\(s\) supprimé\(s\)/)).toBeInTheDocument()
  })
})
