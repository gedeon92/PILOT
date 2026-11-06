import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { meWith, mockApi, OWNER_MEMBER, renderApp, SPACE_ID, spaceWith } from './test-utils'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('connexion', () => {
  it('renvoie vers la connexion quand personne n’est connecté', async () => {
    mockApi({ 'GET /api/auth/me': () => ({ status: 401, json: { detail: 'Connexion requise.' } }) })

    renderApp(`/espaces/${SPACE_ID}/membres`)

    expect(await screen.findByRole('heading', { name: 'Connexion' })).toBeInTheDocument()
  })

  it('affiche le message de l’API quand le mot de passe est faux', async () => {
    const calls = mockApi({
      'GET /api/auth/me': () => ({ status: 401 }),
      'POST /api/auth/login': () => ({
        status: 401,
        json: { detail: 'Adresse e-mail ou mot de passe incorrect.' },
      }),
    })
    renderApp('/connexion')
    const user = userEvent.setup()

    await user.type(await screen.findByLabelText('Adresse e-mail'), 'a@exemple.com')
    await user.type(screen.getByLabelText('Mot de passe'), 'faux')
    await user.click(screen.getByRole('button', { name: 'Se connecter' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('mot de passe incorrect')
    const login = calls.find((c) => c.key === 'POST /api/auth/login')
    expect(login?.headers['X-PILOT-CSRF']).toBe('1')
  })

  it('envoie vers la création d’espace quand le compte n’en a aucun', async () => {
    mockApi({
      'GET /api/auth/me': () => ({ status: 200, json: { ...meWith('owner'), spaces: [] } }),
    })

    renderApp('/')

    expect(await screen.findByRole('heading', { name: 'Créer un espace' })).toBeInTheDocument()
  })
})

describe('accès et membres', () => {
  it('la propriétaire invite une personne et obtient un lien à copier', async () => {
    const invited = {
      ...OWNER_MEMBER,
      id: 'm2',
      email: 'fatou@exemple.com',
      display_name: null,
      role: 'contributor',
      status: 'invited',
      is_me: false,
      invite_expires_at: '2026-11-17T10:00:00Z',
    }
    const calls = mockApi({
      'GET /api/auth/me': () => ({ status: 200, json: meWith('owner') }),
      [`GET /api/spaces/${SPACE_ID}`]: () => ({ status: 200, json: spaceWith('owner') }),
      [`GET /api/spaces/${SPACE_ID}/members`]: () => ({ status: 200, json: [OWNER_MEMBER] }),
      [`POST /api/spaces/${SPACE_ID}/invitations`]: () => ({
        status: 201,
        json: { member: invited, token: 'jeton-secret-de-test-1234567890', emailed: true },
      }),
    })
    renderApp(`/espaces/${SPACE_ID}/membres`)
    const user = userEvent.setup()

    await user.type(await screen.findByLabelText('Adresse e-mail'), 'fatou@exemple.com')
    await user.click(screen.getByRole('button', { name: /Inviter/ }))

    const link = await screen.findByLabelText('Lien d’invitation')
    expect(link).toHaveValue('http://localhost:3000/invitation/jeton-secret-de-test-1234567890')
    expect(
      screen.getByText(/Invitation envoyée par e-mail à fatou@exemple.com/),
    ).toBeInTheDocument()
    expect(calls.find((c) => c.key.endsWith('/invitations'))?.body).toEqual({
      email: 'fatou@exemple.com',
      role: 'contributor',
    })
  })

  it('un lecteur voit les membres sans pouvoir gérer les accès', async () => {
    const reader = {
      ...OWNER_MEMBER,
      id: 'm3',
      email: 'lecteur@exemple.com',
      role: 'reader',
      is_me: true,
    }
    mockApi({
      'GET /api/auth/me': () => ({ status: 200, json: meWith('reader') }),
      [`GET /api/spaces/${SPACE_ID}`]: () => ({ status: 200, json: spaceWith('reader') }),
      [`GET /api/spaces/${SPACE_ID}/members`]: () => ({
        status: 200,
        json: [{ ...OWNER_MEMBER, is_me: false }, reader],
      }),
    })

    renderApp(`/espaces/${SPACE_ID}/membres`)

    const table = await screen.findByRole('table')
    expect(within(table).getAllByRole('row')).toHaveLength(3)
    expect(screen.queryByRole('heading', { name: 'Inviter une personne' })).not.toBeInTheDocument()
    expect(within(table).queryByRole('combobox')).not.toBeInTheDocument()
    expect(within(table).queryByRole('button')).not.toBeInTheDocument()
  })
})

describe('paramètres et structure', () => {
  const base = `/api/spaces/${SPACE_ID}`
  const types = [{ id: 't1', name: 'Événement', archived: false, version: 1 }]

  function structureRoutes(role: 'owner' | 'reader', portfolios: unknown[]) {
    return {
      'GET /api/auth/me': () => ({ status: 200, json: meWith(role) }),
      [`GET ${base}`]: () => ({ status: 200, json: spaceWith(role) }),
      [`GET ${base}/members`]: () => ({ status: 200, json: [OWNER_MEMBER] }),
      [`GET ${base}/portfolios`]: () => ({ status: 200, json: portfolios }),
      [`GET ${base}/entities`]: () => ({ status: 200, json: [] }),
      [`GET ${base}/project-types`]: () => ({ status: 200, json: types }),
    }
  }

  it('la propriétaire ajoute un portefeuille avec sa couleur', async () => {
    const portfolios: unknown[] = []
    const calls = mockApi({
      ...structureRoutes('owner', portfolios),
      [`POST ${base}/portfolios`]: (body) => {
        const created = { id: 'p1', archived: false, version: 1, ...(body as object) }
        portfolios.push(created)
        return { status: 201, json: created }
      },
    })
    renderApp(`/espaces/${SPACE_ID}/parametres`)
    const user = userEvent.setup()

    const section = await screen.findByRole('region', { name: 'Portefeuilles' })
    await user.click(within(section).getByRole('button', { name: /Ajouter/ }))
    await user.type(within(section).getByLabelText('Nom'), 'Événements')
    await user.selectOptions(within(section).getByLabelText('Couleur'), 'blue')
    await user.selectOptions(within(section).getByLabelText('Repère (emoji)'), '🎪')
    await user.click(within(section).getByRole('button', { name: 'Ajouter le portefeuille' }))

    expect(calls.find((c) => c.key === `POST ${base}/portfolios`)?.body).toEqual({
      name: 'Événements',
      color: 'blue',
      emoji: '🎪',
      description: '',
    })
    expect(await within(section).findByText('Événements')).toBeInTheDocument()
  })

  it('un lecteur consulte la structure sans pouvoir la modifier', async () => {
    mockApi(
      structureRoutes('reader', [
        {
          id: 'p1',
          name: 'Événements',
          color: 'orange',
          description: null,
          archived: false,
          version: 1,
        },
      ]),
    )

    renderApp(`/espaces/${SPACE_ID}/parametres`)

    const section = await screen.findByRole('region', { name: 'Portefeuilles' })
    expect(await within(section).findByText('Événements')).toBeInTheDocument()
    expect(within(section).queryByRole('button')).not.toBeInTheDocument()
    expect(screen.getByLabelText('Nom de l’espace')).toBeDisabled()
  })
})

describe('mot de passe oublié', () => {
  it('demande un lien puis enregistre le nouveau mot de passe', async () => {
    const calls = mockApi({
      'GET /api/auth/me': () => ({ status: 401, json: { detail: 'Connexion requise.' } }),
      'POST /api/auth/password-reset': () => ({
        status: 202,
        json: { message: 'Si un compte existe avec cette adresse, un e-mail vient de partir.' },
      }),
    })
    renderApp('/connexion')
    const user = userEvent.setup()

    await user.click(await screen.findByRole('link', { name: 'Mot de passe oublié ?' }))
    await user.type(await screen.findByLabelText('Adresse e-mail'), 'aicha@exemple.com')
    await user.click(screen.getByRole('button', { name: 'Recevoir le lien' }))

    expect(await screen.findByText(/un e-mail vient de partir/)).toBeInTheDocument()
    expect(calls.find((c) => c.key === 'POST /api/auth/password-reset')?.body).toEqual({
      email: 'aicha@exemple.com',
    })
  })

  it('envoie le jeton du lien avec le nouveau mot de passe', async () => {
    const calls = mockApi({
      'GET /api/auth/me': () => ({ status: 401, json: { detail: 'Connexion requise.' } }),
      'POST /api/auth/password-reset/confirm': () => ({
        status: 410,
        json: { detail: 'Ce lien a expiré.' },
      }),
    })
    renderApp('/mot-de-passe/nouveau?jeton=abcdefghijklmnopqrstuvwxyz')
    const user = userEvent.setup()

    await user.type(await screen.findByLabelText('Nouveau mot de passe'), 'un-nouveau-secret')
    await user.click(screen.getByRole('button', { name: 'Enregistrer et me connecter' }))

    expect(await screen.findByText('Ce lien a expiré.')).toBeInTheDocument()
    expect(calls.find((c) => c.key === 'POST /api/auth/password-reset/confirm')?.body).toEqual({
      token: 'abcdefghijklmnopqrstuvwxyz',
      new_password: 'un-nouveau-secret',
    })
  })
})
