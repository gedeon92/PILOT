import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  meWith,
  mockApi,
  OWNER_MEMBER,
  projectFixture as project,
  renderApp,
  SPACE_ID,
  spaceWith,
} from '../test-utils'
import { countryFlag } from '../countries'

const base = `/api/spaces/${SPACE_ID}`

afterEach(() => {
  vi.unstubAllGlobals()
})

function routes(extra: Record<string, (body: unknown) => { status: number; json?: unknown }> = {}) {
  return {
    'GET /api/auth/me': () => ({ status: 200, json: meWith('owner') }),
    [`GET ${base}`]: () => ({ status: 200, json: spaceWith('owner') }),
    [`GET ${base}/members`]: () => ({ status: 200, json: [OWNER_MEMBER] }),
    [`GET ${base}/portfolios`]: () => ({ status: 200, json: [] }),
    [`GET ${base}/alerts`]: () => ({ status: 200, json: { unread: 0, items: [] } }),
    [`GET ${base}/projects`]: () => ({
      status: 200,
      json: [project(), project({ id: 'pr2', title: 'Campagne radio', contributors: [] })],
    }),
    [`GET ${base}/projects/pr1`]: () => ({ status: 200, json: project() }),
    [`GET ${base}/projects/pr1/tasks`]: () => ({ status: 200, json: [] }),
    [`GET ${base}/projects/pr1/history`]: () => ({ status: 200, json: [] }),
    [`GET ${base}/projects/pr1/documents`]: () => ({ status: 200, json: [] }),
    [`GET ${base}/projects/pr1/links`]: () => ({ status: 200, json: [] }),
    [`GET ${base}/tasks`]: () => ({ status: 200, json: [] }),
    ...extra,
  }
}

describe('fiche projet : compléments du cahier des charges', () => {
  it('montre la source de la situation, les options, les contributeurs et l’origine', async () => {
    mockApi(routes())
    renderApp(`/espaces/${SPACE_ID}/projets/pr1`)

    expect(
      await screen.findByText(/Source : boîte de mise à jour \(« point.docx »\)/),
    ).toBeInTheDocument()
    expect(screen.getByText(/par Aïcha Ndiaye/)).toBeInTheDocument()
    const options = screen.getByRole('list', { name: 'Options possibles' })
    expect(within(options).getByText('CICAD')).toBeInTheDocument()
    expect(within(options).getByText(/Plus cher, plus grand/)).toBeInTheDocument()
    expect(screen.getByText('Agence Lumière')).toBeInTheDocument()
    expect(screen.getByText('Demandé en comité de direction')).toBeInTheDocument()
    expect(screen.getByText('Sénégal')).toBeInTheDocument()
  })

  it('lie un projet à un autre', async () => {
    const calls = mockApi(
      routes({
        [`POST ${base}/projects/pr1/links`]: () => ({
          status: 201,
          json: {
            id: 'l1',
            project: {
              id: 'pr2',
              title: 'Campagne radio',
              status: 'in_progress',
              portfolio: { id: 'p1', name: 'Événements', color: 'orange', emoji: null },
            },
            note: 'Même audience',
            created_at: '2026-11-06T10:00:00Z',
          },
        }),
      }),
    )
    renderApp(`/espaces/${SPACE_ID}/projets/pr1`)
    const user = userEvent.setup()

    await user.click(await screen.findByRole('button', { name: 'Lier un projet' }))
    await screen.findByRole('option', { name: 'Campagne radio' })
    await user.selectOptions(screen.getByLabelText('Projet'), 'pr2')
    await user.type(screen.getByLabelText('Pourquoi ce lien ? (facultatif)'), 'Même audience')
    await user.click(screen.getByRole('button', { name: 'Lier' }))

    expect(calls.find((c) => c.key === `POST ${base}/projects/pr1/links`)?.body).toEqual({
      project_id: 'pr2',
      note: 'Même audience',
    })
  })

  it('enregistre contributeurs et options depuis « Modifier la fiche »', async () => {
    const calls = mockApi(
      routes({ [`PATCH ${base}/projects/pr1`]: () => ({ status: 200, json: project() }) }),
    )
    renderApp(`/espaces/${SPACE_ID}/projets/pr1`)
    const user = userEvent.setup()

    await user.click(await screen.findByRole('button', { name: 'Modifier la fiche' }))
    await user.selectOptions(screen.getByLabelText('Ajouter un contributeur'), '__free')
    await user.type(screen.getByLabelText('Nom du contributeur'), 'Traiteur Sall')
    await user.click(screen.getByRole('button', { name: 'Ajouter' }))
    await user.click(screen.getByRole('button', { name: 'Retirer l’option B' }))
    await user.click(screen.getByRole('button', { name: 'Enregistrer' }))

    const body = calls.find((c) => c.key === `PATCH ${base}/projects/pr1`)?.body as Record<
      string,
      unknown
    >
    expect(body.contributors).toEqual([{ label: 'Agence Lumière' }, { label: 'Traiteur Sall' }])
    expect(body.decision_options).toEqual([
      { label: 'CICAD', consequence: 'Plus cher, plus grand' },
    ])
    expect(body.origin).toBe('Demandé en comité de direction')
  })
})

describe('tâches dans la fiche projet', () => {
  it('crée la tâche dans le projet de la fiche (plus de tâche sans projet)', async () => {
    const calls = mockApi(
      routes({
        [`POST ${base}/projects/pr1/tasks`]: () => ({ status: 201, json: {} }),
      }),
    )
    renderApp(`/espaces/${SPACE_ID}/projets/pr1`)
    const user = userEvent.setup()

    await user.click(await screen.findByRole('button', { name: /Tâche$/ }))
    await user.type(screen.getByLabelText('Tâche *'), 'Préparer le comité')
    await user.click(screen.getByRole('button', { name: 'Ajouter la tâche' }))

    expect(calls.find((c) => c.key === `POST ${base}/projects/pr1/tasks`)?.body).toMatchObject({
      title: 'Préparer le comité',
    })
    expect(screen.queryByLabelText('Projet')).not.toBeInTheDocument()
  })
})

describe('point hebdo', () => {
  it('rassemble décisions, changements et informations manquantes', async () => {
    mockApi(
      routes({
        [`GET ${base}/projects`]: () => ({
          status: 200,
          json: [
            project({ updated_at: new Date().toISOString() }),
            project({
              id: 'pr2',
              title: 'Baromètre',
              owner: { member_id: null, name: null, has_account: false },
              next_step: null,
              decision_needed: null,
              situation: null,
              situation_updated_at: null,
              updated_at: '2020-01-01T00:00:00Z',
            }),
          ],
        }),
      }),
    )
    renderApp(`/espaces/${SPACE_ID}/point-hebdo`)

    const decisions = await screen.findByRole('region', { name: /Décisions attendues/ })
    expect(within(decisions).getByText('Choisir le lieu')).toBeInTheDocument()
    expect(within(decisions).getByText(/décideur : Directrice générale/)).toBeInTheDocument()
    const changed = screen.getByRole('region', { name: /Ce qui a changé cette semaine/ })
    expect(within(changed).getByText(/boîte de mise à jour \(« point.docx »\)/)).toBeInTheDocument()
    expect(within(changed).queryByText('Baromètre')).not.toBeInTheDocument()
    const missing = screen.getByRole('region', { name: /Informations manquantes/ })
    expect(
      within(missing).getByText(/responsable du suivi, prochaine étape, date, situation/),
    ).toBeInTheDocument()
  })
})

describe('drapeaux', () => {
  it('reconnaît les pays avec ou sans accents, et ignore l’inconnu', () => {
    expect(countryFlag('Sénégal')).toBe('🇸🇳')
    expect(countryFlag("côte d'ivoire")).toBe('🇨🇮')
    expect(countryFlag('fr')).toBe('🇫🇷')
    expect(countryFlag('Atlantide')).toBe('')
  })
})
