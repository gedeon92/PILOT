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
        json: { member: invited, token: 'jeton-secret-de-test-1234567890' },
      }),
    })
    renderApp(`/espaces/${SPACE_ID}/membres`)
    const user = userEvent.setup()

    await user.type(await screen.findByLabelText('Adresse e-mail'), 'fatou@exemple.com')
    await user.click(screen.getByRole('button', { name: /Inviter/ }))

    const link = await screen.findByLabelText('Lien d’invitation')
    expect(link).toHaveValue('http://localhost:3000/invitation/jeton-secret-de-test-1234567890')
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
