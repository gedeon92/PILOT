import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { meWith, mockApi, OWNER_MEMBER, renderApp, SPACE_ID, spaceWith } from '../test-utils'

const base = `/api/spaces/${SPACE_ID}`
const PORTFOLIO = {
  id: 'p1',
  name: 'Événements',
  color: 'orange',
  description: null,
  archived: false,
  version: 1,
}

const PROJECT = {
  id: 'pr1',
  title: 'Salon Dakar Tech',
  status: 'in_progress',
  portfolio: { id: 'p1', name: 'Événements', color: 'orange' },
  entity: null,
  project_type: null,
  owner: { member_id: null, name: 'Mon assistante', has_account: false },
  situation: null,
  situation_updated_at: null,
  next_step: 'Valider le budget',
  decision_needed: null,
  decision_maker: null,
  objective: null,
  deliverables: null,
  progress: null,
  risk_level: null,
  risk_note: null,
  start_date: null,
  end_date: null,
  due_date: null,
  date_certainty: null,
  window_start: null,
  window_end: null,
  country: null,
  city: null,
  external_url: null,
  outcome: null,
  cancel_reason: null,
  open_tasks: 0,
  late_tasks: 0,
  created_at: '2026-11-03T10:00:00Z',
  updated_at: '2026-11-03T10:00:00Z',
  version: 3,
}

function routes(extra: Record<string, (body: unknown) => { status: number; json?: unknown }> = {}) {
  return {
    'GET /api/auth/me': () => ({ status: 200, json: meWith('contributor') }),
    [`GET ${base}`]: () => ({ status: 200, json: spaceWith('contributor') }),
    [`GET ${base}/members`]: () => ({ status: 200, json: [OWNER_MEMBER] }),
    [`GET ${base}/portfolios`]: () => ({ status: 200, json: [PORTFOLIO] }),
    [`GET ${base}/entities`]: () => ({ status: 200, json: [] }),
    [`GET ${base}/project-types`]: () => ({ status: 200, json: [] }),
    [`GET ${base}/projects/pr1`]: () => ({ status: 200, json: PROJECT }),
    [`GET ${base}/projects/pr1/tasks`]: () => ({ status: 200, json: [] }),
    [`GET ${base}/projects/pr1/history`]: () => ({ status: 200, json: [] }),
    [`GET ${base}/projects/pr1/documents`]: () => ({ status: 200, json: [] }),
    ...extra,
  }
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('projets', () => {
  it('crée un projet attribué à un nom libre, avec un identifiant anti-doublon', async () => {
    const calls = mockApi(
      routes({ [`POST ${base}/projects`]: () => ({ status: 201, json: PROJECT }) }),
    )
    renderApp(`/espaces/${SPACE_ID}/projets/nouveau`)
    const user = userEvent.setup()

    await user.type(await screen.findByLabelText('Titre du projet *'), 'Salon Dakar Tech')
    await user.selectOptions(screen.getByLabelText('Portefeuille *'), 'p1')
    await user.selectOptions(screen.getByLabelText('Responsable du suivi'), '__autre')
    await user.type(screen.getByLabelText('Responsable du suivi : nom'), 'Mon assistante')
    await user.click(screen.getByRole('button', { name: 'Créer le projet' }))

    expect(await screen.findByRole('heading', { name: 'Salon Dakar Tech' })).toBeInTheDocument()
    const body = calls.find((c) => c.key === `POST ${base}/projects`)?.body as Record<
      string,
      unknown
    >
    expect(body).toMatchObject({
      title: 'Salon Dakar Tech',
      portfolio_id: 'p1',
      status: 'to_frame',
      owner_member_id: null,
      owner_label: 'Mon assistante',
    })
    expect(body.client_request_id).toMatch(/^[0-9a-f-]{36}$/)
  })

  it('exige un bilan pour passer un projet à Terminé', async () => {
    const calls = mockApi(
      routes({
        [`POST ${base}/projects/pr1/status`]: () => ({
          status: 200,
          json: { ...PROJECT, status: 'done', outcome: 'Objectif atteint', version: 4 },
        }),
      }),
    )
    renderApp(`/espaces/${SPACE_ID}/projets/pr1`)
    const user = userEvent.setup()

    await user.click(await screen.findByRole('button', { name: 'Changer le statut' }))
    const panel = screen.getByRole('region', { name: 'Changer le statut' })
    await user.selectOptions(within(panel).getByLabelText('Nouveau statut'), 'done')
    const outcome = within(panel).getByLabelText('Bilan du projet *')
    expect(outcome).toBeRequired()
    await user.type(outcome, 'Objectif atteint')
    await user.click(within(panel).getByRole('button', { name: 'Confirmer' }))

    expect(calls.find((c) => c.key.endsWith('/status'))?.body).toEqual({
      version: 3,
      status: 'done',
      outcome: 'Objectif atteint',
    })
  })

  it('signale un conflit de version sans perdre la saisie', async () => {
    mockApi(
      routes({
        [`PATCH ${base}/projects/pr1`]: () => ({
          status: 409,
          json: { detail: 'Cet élément a été modifié entre-temps.' },
        }),
      }),
    )
    renderApp(`/espaces/${SPACE_ID}/projets/pr1`)
    const user = userEvent.setup()

    await user.click(await screen.findByRole('button', { name: 'Modifier la fiche' }))
    const situation = screen.getByLabelText('Situation')
    await user.type(situation, 'Devis reçu')
    await user.click(screen.getByRole('button', { name: 'Enregistrer' }))

    expect(await screen.findByText(/Vos saisies sont conservées/)).toBeInTheDocument()
    expect(screen.getByLabelText('Situation')).toHaveValue('Devis reçu')
  })
})

describe('documents du projet', () => {
  it('envoie un fichier et refuse un fichier trop volumineux sans l’envoyer', async () => {
    const calls = mockApi(
      routes({
        [`POST ${base}/projects/pr1/documents`]: () => ({
          status: 201,
          json: {
            id: 'd1',
            project_id: 'pr1',
            project_title: 'Salon Dakar Tech',
            filename: 'Programme.pdf',
            content_type: 'application/pdf',
            size_bytes: 12,
            uploaded_by: 'Aïcha Ndiaye',
            created_at: '2026-11-03T10:00:00Z',
            archived: false,
          },
        }),
      }),
    )
    renderApp(`/espaces/${SPACE_ID}/projets/pr1`)
    const user = userEvent.setup()

    const picker = await screen.findByLabelText('Ajouter des documents')
    const small = new File(['contenu test'], 'Programme.pdf', { type: 'application/pdf' })
    const big = new File([new Uint8Array(4 * 1024 * 1024 + 1)], 'Vidéo.mp4', { type: 'video/mp4' })
    await user.upload(picker, [small, big])

    expect(await screen.findByText('Enregistré')).toBeInTheDocument()
    expect(await screen.findByText(/Non enregistré : Trop volumineux/)).toBeInTheDocument()
    const sent = calls.filter((c) => c.key === `POST ${base}/projects/pr1/documents`)
    expect(sent).toHaveLength(1)
    expect(sent[0].headers['X-PILOT-CSRF']).toBe('1')
    expect(sent[0].headers['Content-Type']).toBeUndefined()
  })
})
