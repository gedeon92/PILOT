import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, useOutletContext, useSearchParams } from 'react-router'
import { errorMessage } from '../api/client'
import {
  useChangePassword,
  useConfirmEmailChange,
  useMe,
  useRequestEmailChange,
  useUpdateProfile,
} from '../api/queries'
import { Alert, AuthCard, PageHeader } from '../components/ui'
import type { SpaceContext } from './space-layout'
import { PasswordInput } from '../components/password-input'

function NameForm({ current }: { current: string }) {
  const update = useUpdateProfile()
  const [name, setName] = useState(current)
  function submit(e: FormEvent) {
    e.preventDefault()
    update.mutate({ display_name: name })
  }
  return (
    <form className="card-panel form-grid" onSubmit={submit} aria-labelledby="name-title">
      <h2 id="name-title" className="form-grid__full">
        Nom affiché
      </h2>
      <div className="field form-grid__full">
        <label htmlFor="account-name">Nom visible par les membres de vos espaces</label>
        <input
          id="account-name"
          required
          maxLength={120}
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
      </div>
      <div className="form-grid__full form-actions">
        <button
          className="button button--primary"
          type="submit"
          disabled={update.isPending || name.trim() === current}
        >
          Enregistrer
        </button>
      </div>
      {update.isSuccess && name.trim() === current && (
        <div className="form-grid__full">
          <Alert tone="ok">Nom enregistré.</Alert>
        </div>
      )}
      {update.isError && (
        <div className="form-grid__full">
          <Alert>{errorMessage(update.error)}</Alert>
        </div>
      )}
    </form>
  )
}

function EmailForm({ current }: { current: string }) {
  const request = useRequestEmailChange()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  function submit(e: FormEvent) {
    e.preventDefault()
    request.mutate({ new_email: email, password }, { onSuccess: () => setPassword('') })
  }
  return (
    <form className="card-panel form-grid" onSubmit={submit} aria-labelledby="email-title">
      <div className="form-grid__full">
        <h2 id="email-title">Adresse e-mail</h2>
        <p className="card-panel__help">
          Adresse actuelle : <strong>{current}</strong>. Elle sert à vous connecter, à recevoir les
          rappels et à rejoindre les espaces où vous êtes invité.
        </p>
      </div>
      <div className="field">
        <label htmlFor="account-email">Nouvelle adresse</label>
        <input
          id="account-email"
          type="email"
          required
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
      </div>
      <div className="field">
        <label htmlFor="account-email-password">Mot de passe actuel</label>
        <PasswordInput
          id="account-email-password"
          required
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
      </div>
      <p className="field__hint form-grid__full">
        Un lien de confirmation est envoyé à la nouvelle adresse. Votre adresse ne change qu’une
        fois ce lien ouvert, connecté à ce compte.
      </p>
      <div className="form-grid__full form-actions">
        <button className="button button--primary" type="submit" disabled={request.isPending}>
          {request.isPending ? 'Envoi…' : 'Envoyer le lien de confirmation'}
        </button>
      </div>
      {request.data && (
        <div className="form-grid__full">
          <Alert tone="ok">
            Lien de confirmation envoyé à <strong>{request.data.sent_to}</strong> (valable{' '}
            {request.data.expires_hours} h). Ouvrez-le dans ce navigateur pour confirmer. S’il
            n’arrive pas d’ici quelques minutes, regardez dans les courriers indésirables.
          </Alert>
        </div>
      )}
      {request.isError && (
        <div className="form-grid__full">
          <Alert>{errorMessage(request.error)}</Alert>
        </div>
      )}
    </form>
  )
}

function PasswordForm() {
  const change = useChangePassword()
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const mismatch = confirm !== '' && confirm !== next
  function submit(e: FormEvent) {
    e.preventDefault()
    if (mismatch) return
    change.mutate(
      { current_password: current, new_password: next },
      {
        onSuccess: () => {
          setCurrent('')
          setNext('')
          setConfirm('')
        },
      },
    )
  }
  return (
    <form className="card-panel form-grid" onSubmit={submit} aria-labelledby="password-title">
      <h2 id="password-title" className="form-grid__full">
        Mot de passe
      </h2>
      <div className="field">
        <label htmlFor="pw-current">Mot de passe actuel</label>
        <PasswordInput
          id="pw-current"
          required
          autoComplete="current-password"
          value={current}
          onChange={(e) => setCurrent(e.target.value)}
        />
      </div>
      <div className="field">
        <label htmlFor="pw-new">Nouveau mot de passe</label>
        <PasswordInput
          id="pw-new"
          required
          minLength={10}
          maxLength={128}
          autoComplete="new-password"
          value={next}
          onChange={(e) => setNext(e.target.value)}
        />
      </div>
      <div className="field">
        <label htmlFor="pw-confirm">Confirmer le nouveau mot de passe</label>
        <PasswordInput
          id="pw-confirm"
          required
          autoComplete="new-password"
          aria-invalid={mismatch}
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
        />
      </div>
      <p className="field__hint form-grid__full">
        10 caractères minimum. Vos autres appareils connectés seront déconnectés.
      </p>
      {mismatch && (
        <div className="form-grid__full">
          <Alert tone="warn">Les deux nouveaux mots de passe ne sont pas identiques.</Alert>
        </div>
      )}
      <div className="form-grid__full form-actions">
        <button
          className="button button--primary"
          type="submit"
          disabled={change.isPending || mismatch}
        >
          Changer le mot de passe
        </button>
      </div>
      {change.isSuccess && (
        <div className="form-grid__full">
          <Alert tone="ok">Mot de passe changé. Les autres appareils ont été déconnectés.</Alert>
        </div>
      )}
      {change.isError && (
        <div className="form-grid__full">
          <Alert>{errorMessage(change.error)}</Alert>
        </div>
      )}
    </form>
  )
}

export function AccountPage() {
  const { me } = useOutletContext<SpaceContext>()
  return (
    <div className="page-content page-content--narrow">
      <PageHeader title="Mon compte" subtitle="Ces réglages valent pour tous vos espaces." />
      <NameForm key={me.user.display_name} current={me.user.display_name} />
      <EmailForm current={me.user.email} />
      <PasswordForm />
    </div>
  )
}

/** Page ouverte depuis le lien reçu par e-mail. */
export function ConfirmEmailPage() {
  const [params] = useSearchParams()
  const token = params.get('jeton') ?? ''
  const me = useMe()
  const confirm = useConfirmEmailChange()
  const started = useRef(false)

  useEffect(() => {
    if (token && !started.current) {
      started.current = true
      confirm.mutate(token)
    }
  }, [token, confirm])

  const home = me.data?.spaces[0] ? `/espaces/${me.data.spaces[0].id}` : '/'
  return (
    <AuthCard title="Confirmation de l’adresse e-mail">
      {!token && <Alert>Lien incomplet. Ouvrez le lien reçu par e-mail en entier.</Alert>}
      {confirm.isPending && <p className="muted">Confirmation en cours…</p>}
      {confirm.isSuccess && (
        <Alert tone="ok">
          C’est fait : votre compte utilise maintenant <strong>{confirm.data.user.email}</strong>.
        </Alert>
      )}
      {confirm.isError && <Alert>{errorMessage(confirm.error)}</Alert>}
      <Link className="button" to={home}>
        Revenir à PILOT
      </Link>
    </AuthCard>
  )
}
