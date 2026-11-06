export type DecisionOptionValue = { label: string; consequence: string }

/** Deux ou trois options concrètes pour la décision attendue, avec leurs conséquences
 * (CDC §7). Elles aident à trancher ; PILOT ne marque jamais une option comme choisie. */
export function DecisionOptionsField({
  value,
  onChange,
}: {
  value: DecisionOptionValue[]
  onChange: (value: DecisionOptionValue[]) => void
}) {
  const set = (i: number, patch: Partial<DecisionOptionValue>) =>
    onChange(value.map((o, j) => (j === i ? { ...o, ...patch } : o)))

  return (
    <fieldset className="form-grid__full decision-options">
      <legend className="field__label">Options possibles (facultatif, 3 au maximum)</legend>
      {value.map((option, i) => (
        <div key={i} className="decision-options__row">
          <span className="decision-options__letter" aria-hidden="true">
            {String.fromCharCode(65 + i)}
          </span>
          <input
            aria-label={`Option ${String.fromCharCode(65 + i)}`}
            placeholder="Ex. : Reporter d’un mois"
            maxLength={200}
            value={option.label}
            onChange={(e) => set(i, { label: e.target.value })}
          />
          <input
            aria-label={`Conséquence de l’option ${String.fromCharCode(65 + i)}`}
            placeholder="Conséquence : ex. budget inchangé, salle à rechercher"
            maxLength={500}
            value={option.consequence}
            onChange={(e) => set(i, { consequence: e.target.value })}
          />
          <button
            type="button"
            className="button button--small button--ghost"
            aria-label={`Retirer l’option ${String.fromCharCode(65 + i)}`}
            onClick={() => onChange(value.filter((_, j) => j !== i))}
          >
            ×
          </button>
        </div>
      ))}
      {value.length < 3 && (
        <button
          type="button"
          className="button button--small"
          onClick={() => onChange([...value, { label: '', consequence: '' }])}
        >
          Ajouter une option
        </button>
      )}
    </fieldset>
  )
}
