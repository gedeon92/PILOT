import { useToasts } from '../toast'

/** Zone des confirmations, en bas à droite ; annoncées aux lecteurs d'écran. */
export function Toaster() {
  const toasts = useToasts()
  return (
    <div className="toaster" role="status" aria-live="polite">
      {toasts.map((t) => (
        <div key={t.id} className="toast">
          <span className="toast__icon" aria-hidden="true">
            ✓
          </span>
          {t.text}
        </div>
      ))}
    </div>
  )
}
