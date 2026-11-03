import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { StatusPage } from './status'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('page d’état', () => {
  it('affiche l’API et la base de données quand tout répond', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(
          new Response(
            JSON.stringify({ status: 'ok', version: '0.1.0', environment: 'test', database: 'ok' }),
            { status: 200 },
          ),
        ),
    )

    render(<StatusPage />)

    expect(await screen.findByText('Opérationnelle')).toBeInTheDocument()
    expect(screen.getByText('Connectée')).toBeInTheDocument()
    expect(screen.getByText(/Version 0\.1\.0/)).toBeInTheDocument()
  })

  it('signale une base non configurée', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            status: 'ok',
            version: '0.1.0',
            environment: 'local',
            database: 'not_configured',
          }),
          { status: 200 },
        ),
      ),
    )

    render(<StatusPage />)

    expect(await screen.findByText('Non configurée')).toBeInTheDocument()
  })
})
