import { useEffect, useState, type ReactNode } from 'react'
import { Logo } from './icons'
import { ThemeToggle } from './theme-toggle'
import { Showcase } from './showcase'

export type Tone = 'ok' | 'warn' | 'danger' | 'neutral' | 'info' | 'violet'

export function StatusPill({ tone, children }: { tone: Tone; children: ReactNode }) {
  return (
    <span className={`pill pill--${tone}`}>
      <span className="pill__dot" aria-hidden="true" />
      {children}
    </span>
  )
}

export function PageHeader({
  title,
  subtitle,
  actions,
}: {
  title: string
  subtitle?: ReactNode
  actions?: ReactNode
}) {
  return (
    <header className="page-header">
      <div className="page-header__text">
        <h1>{title}</h1>
        {subtitle && <p>{subtitle}</p>}
      </div>
      {actions && <div className="page-header__actions">{actions}</div>}
    </header>
  )
}

export function Alert({ tone = 'danger', children }: { tone?: Tone; children: ReactNode }) {
  return (
    <p className={`alert alert--${tone}`} role={tone === 'danger' ? 'alert' : 'status'}>
      {children}
    </p>
  )
}

// Au-delà de ce délai, on suppose que l'API gratuite de Render est en train de se réveiller.
const WAKING_HINT_MS = 3_000

export function FullPageLoader() {
  const [waking, setWaking] = useState(false)
  useEffect(() => {
    const timer = setTimeout(() => setWaking(true), WAKING_HINT_MS)
    return () => clearTimeout(timer)
  }, [])

  return (
    <main className="centered" aria-busy="true">
      <div className="loader">
        <Logo size={40} />
        <p>
          {waking ? 'Démarrage de PILOT… cela peut prendre jusqu’à une minute.' : 'Chargement…'}
        </p>
      </div>
    </main>
  )
}

export function AuthCard({
  title,
  subtitle,
  children,
  showcase = false,
}: {
  title: string
  subtitle?: ReactNode
  children: ReactNode
  /** Affiche à côté la présentation animée de PILOT (connexion, inscription). */
  showcase?: boolean
}) {
  const card = (
    <div className="panel auth-card">
      <div className="brand">
        <Logo size={34} />
        <span className="brand__name">PILOT</span>
      </div>
      <div className="auth-card__intro">
        <h1>{title}</h1>
        {subtitle && <p>{subtitle}</p>}
      </div>
      {children}
    </div>
  )
  return (
    <main className={showcase ? 'centered centered--showcase' : 'centered'}>
      <ThemeToggle className="button button--small theme-corner" />
      {showcase ? (
        <div className="auth-split">
          {card}
          <Showcase />
        </div>
      ) : (
        card
      )}
    </main>
  )
}

/** Chargement « vivant » : quelques barres qui scintillent à la place d'un simple texte. */
export function Skeleton({ lines = 3 }: { lines?: number }) {
  return (
    <div className="skeleton" aria-busy="true">
      <span className="visually-hidden">Chargement…</span>
      {Array.from({ length: lines }, (_, i) => (
        <span key={i} className="skeleton__bar" style={{ width: `${92 - i * 17}%` }} />
      ))}
    </div>
  )
}
