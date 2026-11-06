/** Barre d'avancement. N'apparaît que si l'avancement est renseigné : une valeur inconnue
 * reste inconnue, jamais déduite d'une date (CDC §2). */
export function ProgressBar({ value, label }: { value: number | null; label?: string }) {
  if (value === null || value === undefined) return null
  const tone = value >= 100 ? 'done' : value >= 60 ? 'high' : value >= 30 ? 'mid' : 'low'
  return (
    <span className={`progress progress--${tone}`}>
      <span
        className="progress__track"
        role="progressbar"
        aria-valuenow={value}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={label ?? 'Avancement'}
      >
        <span className="progress__fill" style={{ width: `${Math.min(100, value)}%` }} />
      </span>
      <span className="progress__value">{value} %</span>
    </span>
  )
}
