import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { meWith, mockApi, OWNER_MEMBER, renderApp, SPACE_ID, spaceWith } from '../test-utils'

/** Étape F6 : indicateurs transparents, capacité à vérifier, rencontres sans suite. */

const base = `/api/spaces/${SPACE_ID}`

afterEach(() => {
  vi.unstubAllGlobals()
})

function indicator(extra: Record<string, unknown>) {
  return {
    key: 'decisions_complete',
    label: 'Décisions complètes',
    measure: 'Part des décisions avec responsable, échéance et critère',
    target: 100,
    comparator: '>=',
    unit: '%',
    numerator: 1,
    denominator: 2,
    value: 50,
    status: 'below',
    na_reason: null,
    cancelled: 0,
    note: null,
    ...extra,
  }
}

function routes(extra = {}) {
  return {
    'GET /api/auth/me': () => ({ status: 200, json: meWith('owner') }),
    [`GET ${base}`]: () => ({ status: 200, json: { ...spaceWith('owner'), advanced_mode: true } }),
    [`GET ${base}/members`]: () => ({ status: 200, json: [OWNER_MEMBER] }),
    [`GET ${base}/alerts`]: () => ({ status: 200, json: { unread: 0, items: [] } }),
    [`GET ${base}/projects`]: () => ({ status: 200, json: [] }),
    ...extra,
  }
}

describe('pilotage', () => {
  it('montre le calcul de chaque indicateur et « non calculable » sans cas', async () => {
    mockApi(
      routes({
        [`GET ${base}/indicators`]: () => ({
          status: 200,
          json: {
            start: '2026-08-15',
            end: '2026-11-12',
            scope: 'Tout l’espace',
            computed_at: '2026-11-12T10:00:00Z',
            indicators: [
              indicator({}),
              indicator({
                key: 'minutes_24h',
                label: 'Relevés diffusés',
                numerator: 0,
                denominator: 0,
                value: null,
                status: 'na',
                na_reason: 'Non calculable : aucun cas sur la période',
              }),
            ],
          },
        }),
      }),
    )
    renderApp(`/espaces/${SPACE_ID}/pilotage`)
    const card = await screen.findByRole('article', { name: 'Décisions complètes' })
    expect(within(card).getByText('50 %')).toBeInTheDocument()
    expect(within(card).getByText(/Cible : 100 % au moins · 1 sur 2 cas/)).toBeInTheDocument()
    const empty = screen.getByRole('article', { name: 'Relevés diffusés' })
    expect(within(empty).getByText('Non calculable')).toBeInTheDocument()
    expect(screen.getByText(/Périmètre : Tout l’espace/)).toBeInTheDocument()
  })

  it('affiche « Capacité à vérifier » et laisse saisir la capacité', async () => {
    const calls = mockApi(
      routes({
        [`GET ${base}/capacity`]: () => ({
          status: 200,
          json: {
            weeks: ['2026-11-09'],
            note: 'Charge = heures estimées.',
            people: [
              {
                member_id: OWNER_MEMBER.id,
                name: 'Raissa',
                capacity: null,
                capacity_note: null,
                capacity_updated_at: null,
                late_hours: 0,
                late_unestimated: 0,
                undated_hours: 0,
                undated_unestimated: 0,
                weeks: [{ start: '2026-11-09', hours: 45, unestimated: 1, tasks: 3, over: null }],
                sustained_overload: false,
              },
            ],
          },
        }),
        [`PUT ${base}/capacity/${OWNER_MEMBER.id}`]: () => ({
          status: 200,
          json: { weeks: [], people: [], note: '' },
        }),
      }),
    )
    renderApp(`/espaces/${SPACE_ID}/pilotage?vue=charge`)
    const user = userEvent.setup()
    expect(await screen.findByText('Capacité à vérifier')).toBeInTheDocument()
    expect(screen.getByText('45 h + 1 non estimée(s)')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Saisir' }))
    await user.type(screen.getByLabelText('Heures disponibles par semaine'), '35')
    await user.click(screen.getByRole('button', { name: 'OK' }))
    expect(calls.find((c) => c.key === `PUT ${base}/capacity/${OWNER_MEMBER.id}`)?.body).toEqual({
      hours_per_week: 35,
      note: null,
    })
  })

  it('signale une rencontre sans suite', async () => {
    mockApi(
      routes({
        [`GET ${base}/relations`]: () => ({ status: 200, json: [] }),
        [`GET ${base}/encounters`]: () => ({
          status: 200,
          json: [
            {
              id: 'e1',
              title: 'Rendez-vous Banque Sahel',
              relation: null,
              project: null,
              objective: 'Accord de principe',
              expected_decision: null,
              priority_account: true,
              urgent: false,
              triage: 'accept',
              triage_note: null,
              is_trip: false,
              starts_on: '2026-11-10',
              ends_on: null,
              dossier: null,
              dossier_ready_at: null,
              dossier_due: false,
              report: null,
              report_at: null,
              report_due_on: '2026-11-10',
              follow_owner: { member_id: null, name: null, has_account: false },
              next_action: null,
              next_action_date: null,
              without_follow_up: true,
              closed_at: null,
              close_reason: null,
              owner: { member_id: null, name: null, has_account: false },
              private: false,
              can_write: true,
              version: 1,
            },
          ],
        }),
      }),
    )
    renderApp(`/espaces/${SPACE_ID}/relations`)
    const card = await screen.findByRole('article', { name: 'Rendez-vous Banque Sahel' })
    expect(within(card).getByText('Sans suite')).toBeInTheDocument()
    expect(within(card).getByText(/compte prioritaire/)).toBeInTheDocument()
  })
})
