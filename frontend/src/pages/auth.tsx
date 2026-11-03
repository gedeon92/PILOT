import { useState, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { errorMessage } from '../api/client'
import { useLogin, useRegister } from '../api/queries'
import { Alert, AuthCard } from '../components/ui'

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
    <AuthCard title="Connexion" subtitle="Retrouvez vos projets et vos priorités.">
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
          <input
            id="password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
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
    <AuthCard title="Créer un compte" subtitle="Gratuit pendant la phase de test.">
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
          <input
            id="password"
            type="password"
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
