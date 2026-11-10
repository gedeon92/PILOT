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

/** Étape F2 : jalons, risque, reports et revue de cadrage. */

const base = `/api/spaces/${SPACE_ID}`

afterEach(() => {
  vi.unstubAllGlobals()
})

function milestone(extra: Record<string, unknown> = {}) {
  return {
    id: 'm1',
    project_id: 'pr1',
    project_title: 'Atlas',
    section_id: null,
    title: 'Salle confirmée',
    criterion: 'Contrat signé',
    owner: { member_id: null, name: 'Mon assistante', has_account: false },
    due_date: '2026-11-20',
    original_due_date: '2026-11-06',
    postpone_count: 2,
    critical: true,
    state: 'planned',
    close_note: null,
    closed_at: null,
    reframe_note: null,
    late: false,
    at_risk: true,
    risk_reasons: ['1 tâche(s) liée(s) bloquée(s)', 'déjà reporté 2 fois'],
    reframe_needed: true,
    tasks: [{ id: 't1', title: 'Réserver la salle', status: 'blocked', late: false }],
    version: 3,
    ...extra,
  }
}

function routes(milestones: unknown[], extra = {}) {
  return {
    'GET /api/auth/me': () => ({ status: 200, json: meWith('owner') }),
    [`GET ${base}`]: () => ({ status: 200, json: spaceWith('owner') }),
    [`GET ${base}/members`]: () => ({ status: 200, json: [OWNER_MEMBER] }),
    [`GET ${base}/portfolios`]: () => ({ status: 200, json: [] }),
    [`GET ${base}/alerts`]: () => ({ status: 200, json: { unread: 0, items: [] } }),
    [`GET ${base}/projects`]: () => ({ status: 200, json: [projectFixture()] }),
    [`GET ${base}/projects/pr1`]: () => ({ status: 200, json: projectFixture() }),
    [`GET ${base}/projects/pr1/tasks`]: () => ({ status: 200, json: [] }),
    [`GET ${base}/projects/pr1/sections`]: () => ({ status: 200, json: [] }),
    [`GET ${base}/projects/pr1/milestones`]: () => ({ status: 200, json: milestones }),
    [`GET ${base}/projects/pr1/history`]: () => ({ status: 200, json: [] }),
    [`GET ${base}/projects/pr1/documents`]: () => ({ status: 200, json: [] }),
    [`GET ${base}/projects/pr1/links`]: () => ({ status: 200, json: [] }),
    ...extra,
  }
}

describe('jalons d’un projet', () => {
  it('montre le risque et exige une revue de cadrage au troisième report', async () => {
    const calls = mockApi(
      routes([milestone()], {
        [`PATCH ${base}/milestones/m1`]: (body: unknown) => ({
          status: 200,
          json: milestone({ ...(body as object), postpone_count: 3, version: 4 }),
        }),
      }),
    )
    renderApp(`/espaces/${SPACE_ID}/projets/pr1`)
    const user = userEvent.setup()

    const panel = (await screen.findByRole('heading', { name: /Jalons/ })).closest(
      'section',
    ) as HTMLElement
    expect(await within(panel).findByText('1 à venir · 1 à surveiller')).toBeInTheDocument()
    expect(within(panel).getByText('⚠ À risque')).toBeInTheDocument()
    expect(within(panel).getByText('↷ Reporté 2 fois')).toBeInTheDocument()
    expect(within(panel).getByText('Revue de cadrage')).toBeInTheDocument()
    expect(
      within(panel).getByText('⚠ 1 tâche(s) liée(s) bloquée(s) · déjà reporté 2 fois'),
    ).toBeInTheDocument()

    await user.click(within(panel).getByRole('button', { name: 'Reporter' }))
    const form = within(panel).getByRole('form', { name: 'Reporter le jalon' })
    await user.type(within(form).getByLabelText('Nouvelle date *'), '2026-12-04')
    await user.type(within(form).getByLabelText('Motif du report *'), 'Traiteur indisponible')
    await user.type(
      within(form).getByLabelText('Revue de cadrage *'),
      'Une seule salle : date tenable',
    )
    await user.click(within(form).getByRole('button', { name: 'Reporter' }))
    expect(calls.find((c) => c.key === `PATCH ${base}/milestones/m1`)?.body).toEqual({
      version: 3,
      due_date: '2026-12-04',
      postpone_reason: 'Traiteur indisponible',
      reframe_note: 'Une seule salle : date tenable',
    })
  })

  it('demande un motif pour un jalon manqué', async () => {
    const calls = mockApi(
      routes([milestone({ reframe_needed: false, postpone_count: 0, at_risk: false })], {
        [`POST ${base}/milestones/m1/close`]: () => ({
          status: 200,
          json: milestone({ state: 'missed', close_note: 'Salle prise' }),
        }),
      }),
    )
    renderApp(`/espaces/${SPACE_ID}/projets/pr1`)
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Manqué / annulé' }))
    const form = screen.getByRole('form', { name: 'Clôturer le jalon' })
    await user.selectOptions(within(form).getByLabelText('Résultat'), 'missed')
    expect(within(form).getByLabelText('Motif *')).toBeRequired()
    await user.type(within(form).getByLabelText('Motif *'), 'Salle prise')
    await user.click(within(form).getByRole('button', { name: 'Enregistrer' }))
    expect(calls.find((c) => c.key === `POST ${base}/milestones/m1/close`)?.body).toEqual({
      version: 3,
      state: 'missed',
      note: 'Salle prise',
    })
  })
})
