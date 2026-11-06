import { useState, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { errorMessage } from '../api/client'
import { useForgotPassword, useLogin, useRegister, useResetPassword } from '../api/queries'
import { Alert, AuthCard } from '../components/ui'
import { PasswordInput } from '../components/password-input'

/** N'accepte qu'un chemin interne, pour qu'un lien piégé ne renvoie pas vers un autre site. */
function safeNext(value: string | null): string {
  return value && value.startsWith('/') && !value.startsWith('//') ? value : '/'
}

function withNext(path: string, next: string) {
  return next === '/' ? path : `${path}?next=${encodeURIComponent(next)}`
}

export function LoginPage() {
  const [params] = useSearchParams()
  const next = safeNext(params.get('next'))
  const navigate = useNavigate()
  const login = useLogin()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')

  function submit(event: FormEvent) {
    event.preventDefault()
    login.mutate({ email, password }, { onSuccess: () => navigate(next, { replace: true }) })
  }

  return (
    <AuthCard title="Connexion" subtitle="Retrouvez vos projets et vos priorités." showcase>
      <form className="form" onSubmit={submit}>
        <div className="field">
          <label htmlFor="email">Adresse e-mail</label>
          <input
            id="email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor="password">Mot de passe</label>
          <PasswordInput
            id="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <Link className="field__hint auth-card__forgot" to="/mot-de-passe-oublie">
            Mot de passe oublié ?
          </Link>
        </div>
        {login.isError && <Alert>{errorMessage(login.error)}</Alert>}
        <button className="button button--primary" type="submit" disabled={login.isPending}>
          {login.isPending ? 'Connexion…' : 'Se connecter'}
        </button>
      </form>
      <p className="auth-card__switch">
        Pas encore de compte ? <Link to={withNext('/inscription', next)}>Créer un compte</Link>
      </p>
    </AuthCard>
  )
}

export function RegisterPage() {
  const [params] = useSearchParams()
  const next = safeNext(params.get('next'))
  const navigate = useNavigate()
  const register = useRegister()
  const [name, setName] = useState('')
  const [email, setEmail] = useState(params.get('email') ?? '')
  const [password, setPassword] = useState('')

  function submit(event: FormEvent) {
    event.preventDefault()
    register.mutate(
      { display_name: name, email, password },
      { onSuccess: () => navigate(next, { replace: true }) },
    )
  }

  return (
    <AuthCard
      showcase
      title="Créer un compte"
      subtitle="Pilotez vos projets, vos échéances et vos documents au même endroit."
    >
      <form className="form" onSubmit={submit}>
        <div className="field">
          <label htmlFor="name">Nom affiché</label>
          <input
            id="name"
            autoComplete="name"
            required
            maxLength={120}
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor="email">Adresse e-mail</label>
          <input
            id="email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor="password">Mot de passe</label>
          <PasswordInput
            id="password"
            autoComplete="new-password"
            required
            minLength={10}
            maxLength={128}
            aria-describedby="password-hint"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <span id="password-hint" className="field__hint">
            10 caractères minimum.
          </span>
        </div>
        {register.isError && <Alert>{errorMessage(register.error)}</Alert>}
        <button className="button button--primary" type="submit" disabled={register.isPending}>
          {register.isPending ? 'Création…' : 'Créer mon compte'}
        </button>
      </form>
      <p className="auth-card__switch">
        Déjà un compte ? <Link to={withNext('/connexion', next)}>Se connecter</Link>
      </p>
    </AuthCard>
  )
}

export function ForgotPasswordPage() {
  const forgot = useForgotPassword()
  const [email, setEmail] = useState('')

  function submit(event: FormEvent) {
    event.preventDefault()
    forgot.mutate(email)
  }

  return (
    <AuthCard
      title="Mot de passe oublié"
      subtitle="Indiquez l’adresse de votre compte : nous vous envoyons un lien pour en choisir un nouveau."
    >
      {forgot.isSuccess ? (
        <Alert tone="ok">{forgot.data.message}</Alert>
      ) : (
        <form className="form" onSubmit={submit}>
          <div className="field">
            <label htmlFor="email">Adresse e-mail</label>
            <input
              id="email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>
          {forgot.isError && <Alert>{errorMessage(forgot.error)}</Alert>}
          <button className="button button--primary" type="submit" disabled={forgot.isPending}>
            {forgot.isPending ? 'Envoi…' : 'Recevoir le lien'}
          </button>
        </form>
      )}
      <p className="auth-card__switch">
        <Link to="/connexion">Retour à la connexion</Link>
      </p>
    </AuthCard>
  )
}

export function ResetPasswordPage() {
  const [params] = useSearchParams()
  const token = params.get('jeton') ?? ''
  const navigate = useNavigate()
  const reset = useResetPassword()
  const [password, setPassword] = useState('')

  function submit(event: FormEvent) {
    event.preventDefault()
    reset.mutate(
      { token, new_password: password },
      { onSuccess: () => navigate('/', { replace: true }) },
    )
  }

  return (
    <AuthCard title="Nouveau mot de passe" subtitle="Choisissez votre nouveau mot de passe PILOT.">
      {!token ? (
        <Alert>
          Ce lien est incomplet. Ouvrez le bouton reçu par e-mail, ou refaites la demande.
        </Alert>
      ) : (
        <form className="form" onSubmit={submit}>
          <div className="field">
            <label htmlFor="new-password">Nouveau mot de passe</label>
            <PasswordInput
              id="new-password"
              autoComplete="new-password"
              required
              minLength={10}
              maxLength={128}
              aria-describedby="new-password-hint"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            <span id="new-password-hint" className="field__hint">
              10 caractères minimum. Vos autres appareils seront déconnectés.
            </span>
          </div>
          {reset.isError && <Alert>{errorMessage(reset.error)}</Alert>}
          <button className="button button--primary" type="submit" disabled={reset.isPending}>
            {reset.isPending ? 'Enregistrement…' : 'Enregistrer et me connecter'}
          </button>
        </form>
      )}
      <p className="auth-card__switch">
        <Link to="/mot-de-passe-oublie">Refaire une demande</Link>
      </p>
    </AuthCard>
  )
}
