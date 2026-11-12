import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  meWith,
  mockApi,
  OWNER_MEMBER,
  projectFixture,
  renderApp,
  SPACE_ID,
  spaceWith,
} from '../test-utils'

/** Étape F4 : champs personnalisés (catalogue, valeurs du projet, mode simple). */

const base = `/api/spaces/${SPACE_ID}`

afterEach(() => {
  vi.unstubAllGlobals()
})

function field(extra: Record<string, unknown> = {}) {
  return {
    id: 'f1',
    key: 'type_de_risque',
    label: 'Type de risque',
    description: null,
    target: 'project',
    type: 'choice',
    required: true,
    project_id: null,
    options: [
      { id: 'opt_a', label: 'Financier', active: true },
      { id: 'opt_b', label: 'Juridique', active: true },
    ],
    config: {},
    position: 1,
    archived: false,
    version: 1,
    values_count: 0,
    ...extra,
  }
}

const budget = field({
  id: 'f2',
  key: 'budget',
  label: 'Budget autorisé',
  type: 'amount',
  required: false,
  options: [],
  config: { currency: 'EUR' },
})

function routes(advanced: boolean, extra = {}) {
  return {
    'GET /api/auth/me': () => ({ status: 200, json: meWith('owner') }),
    [`GET ${base}`]: () => ({
      status: 200,
      json: { ...spaceWith('owner'), advanced_mode: advanced },
    }),
    [`GET ${base}/members`]: () => ({ status: 200, json: [OWNER_MEMBER] }),
    [`GET ${base}/portfolios`]: () => ({ status: 200, json: [] }),
    [`GET ${base}/alerts`]: () => ({ status: 200, json: { unread: 0, items: [] } }),
    [`GET ${base}/projects`]: () => ({ status: 200, json: [projectFixture()] }),
    [`GET ${base}/projects/pr1`]: () => ({ status: 200, json: projectFixture() }),
    [`GET ${base}/projects/pr1/tasks`]: () => ({ status: 200, json: [] }),
    [`GET ${base}/projects/pr1/sections`]: () => ({ status: 200, json: [] }),
    [`GET ${base}/projects/pr1/milestones`]: () => ({ status: 200, json: [] }),
    [`GET ${base}/projects/pr1/history`]: () => ({ status: 200, json: [] }),
    [`GET ${base}/projects/pr1/documents`]: () => ({ status: 200, json: [] }),
    [`GET ${base}/projects/pr1/links`]: () => ({ status: 200, json: [] }),
    [`GET ${base}/projects/pr1/custom-fields`]: () => ({
      status: 200,
      json: { fields: [field(), budget], hidden_ids: [], values: {}, task_values: {} },
    }),
    ...extra,
  }
}

describe('champs personnalisés', () => {
  it('se remplissent dans la fiche projet, avec le champ obligatoire signalé', async () => {
    const calls = mockApi(
      routes(true, {
        [`PUT ${base}/projects/pr1/custom-values`]: () => ({
          status: 200,
          json: {
            fields: [field(), budget],
            hidden_ids: [],
            values: { f1: 'opt_b', f2: 1200 },
            task_values: {},
          },
        }),
      }),
    )
    renderApp(`/espaces/${SPACE_ID}/projets/pr1`)
    const user = userEvent.setup()
    const card = await screen.findByRole('region', { name: 'Champs personnalisés' })
    expect(within(card).getByText('À compléter : Type de risque')).toBeInTheDocument()
    await user.click(within(card).getByRole('button', { name: 'Modifier les champs' }))
    await user.selectOptions(within(card).getByLabelText(/Type de risque/), 'opt_b')
    await user.type(within(card).getByLabelText('Budget autorisé'), '1200')
    await user.click(within(card).getByRole('button', { name: 'Enregistrer' }))
    expect(calls.find((c) => c.key === `PUT ${base}/projects/pr1/custom-values`)?.body).toEqual({
      values: { f1: 'opt_b', f2: 1200 },
    })
  })

  it('restent cachés en mode simple', async () => {
    const calls = mockApi(routes(false))
    renderApp(`/espaces/${SPACE_ID}/projets/pr1`)
    expect(await screen.findByRole('region', { name: 'Situation' })).toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Champs personnalisés' })).not.toBeInTheDocument()
    expect(calls.some((c) => c.key.includes('custom-fields'))).toBe(false)
  })

  it('se créent dans Paramètres, avec la devise pour un montant', async () => {
    const calls = mockApi(
      routes(true, {
        [`GET ${base}/custom-fields`]: () => ({ status: 200, json: [field()] }),
        [`GET ${base}/entities`]: () => ({ status: 200, json: [] }),
        [`GET ${base}/programs`]: () => ({ status: 200, json: [] }),
        [`GET ${base}/project-types`]: () => ({ status: 200, json: [] }),
        [`GET ${base}/templates`]: () => ({ status: 200, json: [] }),
        [`GET ${base}/ai/status`]: () => ({
          status: 200,
          json: { enabled: false, configured: false, used_today: 0, daily_limit: 60 },
        }),
        [`POST ${base}/custom-fields`]: () => ({ status: 201, json: budget }),
      }),
    )
    renderApp(`/espaces/${SPACE_ID}/parametres`)
    const user = userEvent.setup()
    const card = await screen.findByRole('region', { name: 'Champs personnalisés' })
    expect(
      await within(card).findByText(/Choix unique · projets · obligatoire/),
    ).toBeInTheDocument()
    await user.click(within(card).getByRole('button', { name: '+ Champ' }))
    await user.type(within(card).getByLabelText('Nom du champ'), 'Budget autorisé')
    await user.selectOptions(within(card).getByLabelText('Type'), 'amount')
    expect(within(card).getByLabelText('Devise')).toHaveValue('EUR')
    await user.click(within(card).getByRole('button', { name: 'Ajouter le champ' }))
    expect(calls.find((c) => c.key === `POST ${base}/custom-fields`)?.body).toMatchObject({
      label: 'Budget autorisé',
      target: 'project',
      type: 'amount',
      config: { currency: 'EUR' },
    })
  })
})
