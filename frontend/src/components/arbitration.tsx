import { useState, type FormEvent } from 'react'
import { errorMessage, type Decision } from '../api/client'
import { useSaveArbitration } from '../api/queries'
import { formatMoment } from '../labels'
import { Alert, StatusPill } from './ui'

/** Étape F6 (cahier V2, DEC04) : dossier d'arbitrage d'une décision. Un dossier soumis
 * comporte contexte, faits, impact, deux ou trois options, recommandation, risques et décision
 * attendue. Les droits de l'application ne donnent aucun mandat pour trancher ou signer. */

const FIELDS: [string, string][] = [
  ['context', 'Contexte'],
  ['facts', 'Faits'],
  ['impact_delay', 'Impact sur les délais'],
  ['impact_cost', 'Impact sur les coûts'],
  ['impact_capacity', 'Impact sur la capacité'],
  ['recommendation', 'Recommandation'],
  ['risks', 'Risques'],
  ['expected_decision', 'Décision attendue'],
]

type Option = { label: string; consequence: string }

export function ArbitrationSummary({ decision }: { decision: Decision }) {
  const a = decision.arbitration as Record<string, unknown> | null
  if (!a) return null
  const options = (a.options as Option[] | undefined) ?? []
  return (
    <div className="arbitration">
      <p className="arbitration__title">
        Dossier d’arbitrage{' '}
        {decision.arbitration_submitted_at ? (
          <StatusPill tone="violet">
            Soumis le {formatMoment(decision.arbitration_submitted_at)}
          </StatusPill>
        ) : (
          <StatusPill tone="neutral">En préparation</StatusPill>
        )}
      </p>
      <dl className="decision__facts">
        {FIELDS.filter(([k]) => a[k]).map(([k, label]) => (
          <div key={k}>
            <dt>{label}</dt>
            <dd>{String(a[k])}</dd>
          </div>
        ))}
        {options.length > 0 && (
          <div>
            <dt>Options</dt>
            <dd>
              <ol className="arbitration__options">
                {options.map((o, i) => (
                  <li key={i}>
                    <strong>{o.label}</strong>
                    {o.consequence ? ` — ${o.consequence}` : ''}
                  </li>
                ))}
              </ol>
            </dd>
          </div>
        )}
      </dl>
    </div>
  )
}

export function ArbitrationForm({
  spaceId,
  decision,
  onDone,
}: {
  spaceId: string
  decision: Decision
  onDone: () => void
}) {
  const save = useSaveArbitration(spaceId)
  const a = (decision.arbitration as Record<string, unknown> | null) ?? {}
  const [values, setValues] = useState<Record<string, string>>(
    Object.fromEntries(FIELDS.map(([k]) => [k, String(a[k] ?? '')])),
  )
  const [options, setOptions] = useState<Option[]>(() => {
    const current = ((a.options as Option[] | undefined) ?? []).map((o) => ({
      label: o.label,
      consequence: o.consequence ?? '',
    }))
    while (current.length < 2) current.push({ label: '', consequence: '' })
    return current
  })
  const id = `arb-${decision.id}`

  function send(submit: boolean) {
    save.mutate(
      {
        decision,
        ...Object.fromEntries(Object.entries(values).map(([k, v]) => [k, v.trim() || null])),
        options: options
          .filter((o) => o.label.trim())
          .map((o) => ({ label: o.label.trim(), consequence: o.consequence.trim() || null })),
        submit,
      },
      { onSuccess: onDone },
    )
  }

  function submit(event: FormEvent) {
    event.preventDefault()
    send(true)
  }

  return (
    <form className="item-form arbitration-form" onSubmit={submit} aria-label="Dossier d’arbitrage">
      <p className="field__hint item-form__name">
        Préparez les éléments ; la personne habilitée tranche. Ce dossier ne donne aucun mandat pour
        signer ou dépasser un budget.
      </p>
      {FIELDS.map(([k, label]) => (
        <div className="field item-form__name" key={k}>
          <label htmlFor={`${id}-${k}`}>{label}</label>
          <textarea
            id={`${id}-${k}`}
            rows={2}
            maxLength={4000}
            value={values[k]}
            onChange={(e) => setValues((v) => ({ ...v, [k]: e.target.value }))}
          />
        </div>
      ))}
      <fieldset className="enc-block item-form__name">
        <legend>Options (deux ou trois)</legend>
        {options.map((o, i) => (
          <div key={i} className="cf-options__row">
            <label className="visually-hidden" htmlFor={`${id}-opt-${i}`}>
              Option {i + 1}
            </label>
            <input
              id={`${id}-opt-${i}`}
              placeholder={`Option ${i + 1} (ex. décaler, renforcer, réduire)`}
              maxLength={200}
              value={o.label}
              onChange={(e) =>
                setOptions((all) =>
                  all.map((x, j) => (j === i ? { ...x, label: e.target.value } : x)),
                )
              }
            />
            <label className="visually-hidden" htmlFor={`${id}-cons-${i}`}>
              Conséquence de l’option {i + 1}
            </label>
            <input
              id={`${id}-cons-${i}`}
              placeholder="Conséquence"
              maxLength={4000}
              value={o.consequence}
              onChange={(e) =>
                setOptions((all) =>
                  all.map((x, j) => (j === i ? { ...x, consequence: e.target.value } : x)),
                )
              }
            />
          </div>
        ))}
        {options.length < 3 && (
          <button
            type="button"
            className="button button--small button--ghost"
            onClick={() => setOptions((all) => [...all, { label: '', consequence: '' }])}
          >
            + Option
          </button>
        )}
      </fieldset>
      {save.isError && <Alert>{errorMessage(save.error)}</Alert>}
      <div className="item-form__actions">
        <button className="button button--primary" disabled={save.isPending}>
          Soumettre le dossier
        </button>
        <button
          type="button"
          className="button"
          disabled={save.isPending}
          onClick={() => send(false)}
        >
          Enregistrer le brouillon
        </button>
        <button type="button" className="button button--ghost" onClick={onDone}>
          Annuler
        </button>
      </div>
    </form>
  )
}
