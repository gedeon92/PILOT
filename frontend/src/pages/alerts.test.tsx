import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { todayIso } from '../labels'
import { meWith, mockApi, OWNER_MEMBER, renderApp, SPACE_ID, spaceWith } from '../test-utils'

const base = `/api/spaces/${SPACE_ID}`

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('alertes', () => {
  it('affiche les alertes du jour, les marque comme lues et enregistre les préférences', async () => {
    const today = todayIso('Africa/Dakar')
    const alert = {
      id: 'al1',
      rule: 'overdue',
      rule_label: 'En retard',
      target_type: 'project',
      project_id: 'pr1',
      alert_date: today,
      title: 'Salon Dakar Tech',
      detail: 'Échéance dépassée depuis le 2 nov.',
      read: false,
    }
    const prefs = {
      disabled_rules: [],
      email_digest: true,
      digest_hour: 7,
      email_available: true,
      rules: { overdue: 'En retard', blocked: 'Bloqué' },
    }
    const calls = mockApi({
      'GET /api/auth/me': () => ({ status: 200, json: meWith('owner') }),
      [`GET ${base}`]: () => ({ status: 200, json: spaceWith('owner') }),
      [`GET ${base}/members`]: () => ({ status: 200, json: [OWNER_MEMBER] }),
      [`GET ${base}/portfolios`]: () => ({ status: 200, json: [] }),
      [`GET ${base}/alerts`]: () => ({ status: 200, json: { unread: 1, items: [alert] } }),
      [`GET ${base}/alert-preferences`]: () => ({ status: 200, json: prefs }),
      [`POST ${base}/alerts/al1/read`]: () => ({ status: 200, json: { ...alert, read: true } }),
      [`PUT ${base}/alert-preferences`]: (body) => ({
        status: 200,
        json: { ...prefs, ...(body as object) },
      }),
    })
    renderApp(`/espaces/${SPACE_ID}/alertes`)
    const user = userEvent.setup()

    const today_ = await screen.findByRole('region', { name: /Aujourd’hui/ })
    expect(await within(today_).findByText('Salon Dakar Tech')).toBeInTheDocument()
    expect(await screen.findByLabelText('1 alerte(s) non lue(s)')).toBeInTheDocument()

    await user.click(within(today_).getByRole('button', { name: 'Marquer comme lu' }))
    expect(calls.some((c) => c.key === `POST ${base}/alerts/al1/read`)).toBe(true)

    await user.click(screen.getByRole('checkbox', { name: 'Bloqué' }))
    await user.selectOptions(screen.getByLabelText(/Heure d’envoi/), '8')
    await user.click(screen.getByRole('button', { name: 'Enregistrer' }))
    expect(calls.find((c) => c.key === `PUT ${base}/alert-preferences`)?.body).toEqual({
      disabled_rules: ['blocked'],
      email_digest: true,
      digest_hour: 8,
    })
  })
})
