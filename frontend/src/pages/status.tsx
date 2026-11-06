import { useEffect, useState } from 'react'
import { fetchHealth, type Health } from '../api/health'
import { StatusPill, type Tone } from '../components/ui'

type ApiState =
  { kind: 'loading' } | { kind: 'waking' } | { kind: 'ready'; health: Health } | { kind: 'error' }

// Au-delà de ce délai sans réponse, le service est probablement en train de redémarrer.
const WAKING_HINT_MS = 3_000

function apiStatus(state: ApiState): { tone: Tone; label: string } {
  switch (state.kind) {
    case 'loading':
      return { tone: 'neutral', label: 'Vérification…' }
    case 'waking':
      return { tone: 'warn', label: 'Démarrage…' }
    case 'ready':
      return { tone: 'ok', label: 'Opérationnelle' }
    case 'error':
      return { tone: 'danger', label: 'Indisponible' }
  }
}

function databaseStatus(state: ApiState): { tone: Tone; label: string } {
  if (state.kind !== 'ready') return { tone: 'neutral', label: 'Vérification…' }
  switch (state.health.database) {
    case 'ok':
      return { tone: 'ok', label: 'Connectée' }
    case 'not_configured':
      return { tone: 'warn', label: 'Indisponible' }
    case 'unavailable':
      return { tone: 'danger', label: 'Indisponible' }
  }
}

export function StatusPage() {
  const [state, setState] = useState<ApiState>({ kind: 'loading' })

  useEffect(() => {
    const controller = new AbortController()
    const wakingTimer = setTimeout(() => {
      setState((current) => (current.kind === 'loading' ? { kind: 'waking' } : current))
    }, WAKING_HINT_MS)

    fetchHealth(controller.signal)
      .then((health) => setState({ kind: 'ready', health }))
      .catch(() => {
        if (!controller.signal.aborted) setState({ kind: 'error' })
      })
      .finally(() => clearTimeout(wakingTimer))

    return () => {
      controller.abort()
      clearTimeout(wakingTimer)
    }
  }, [])

  const api = apiStatus(state)
  const database = databaseStatus(state)

  return (
    <main className="page">
      <div className="panel">
        <header className="brand">
          <img src="/favicon.svg" alt="" width="36" height="36" />
          <span className="brand__name">PILOT</span>
        </header>

        <div className="intro">
          <h1>État du service</h1>
          <p>Disponibilité de PILOT en temps réel.</p>
        </div>

        <ul className="checks" aria-live="polite">
          <li className="check">
            <span className="check__label">Application</span>
            <StatusPill tone="ok">En ligne</StatusPill>
          </li>
          <li className="check">
            <span className="check__label">Service</span>
            <StatusPill tone={api.tone}>{api.label}</StatusPill>
          </li>
          <li className="check">
            <span className="check__label">Données</span>
            <StatusPill tone={database.tone}>{database.label}</StatusPill>
          </li>
        </ul>

        {state.kind === 'waking' && (
          <p className="note">
            PILOT redémarre après une période d’inactivité : cela peut prendre jusqu’à une minute.
          </p>
        )}
        {state.kind === 'ready' && <p className="note">Version {state.health.version}</p>}
      </div>
    </main>
  )
}
