import { useState } from 'react'
import type { Member } from '../api/client'
import type { PersonValue } from '../person'

/** Contributeurs d'un projet (CDC §21) : membres de l'espace ou noms libres, distincts du
 * responsable du suivi. Ajouter quelqu'un ici ne lui donne aucun droit. */
export function ContributorsField({
  members,
  value,
  onChange,
}: {
  members: Member[]
  value: PersonValue[]
  onChange: (value: PersonValue[]) => void
}) {
  const [choice, setChoice] = useState('')
  const [freeName, setFreeName] = useState('')
  const active = members.filter((m) => m.status === 'active')
  const nameOf = (p: PersonValue) => {
    const member = active.find((m) => m.id === p.memberId)
    return member ? (member.display_name ?? member.email) : p.label
  }
  const available = active.filter((m) => !value.some((p) => p.memberId === m.id))

  function add() {
    if (choice === '__free') {
      const label = freeName.trim()
      if (!label || value.some((p) => !p.memberId && p.label.toLowerCase() === label.toLowerCase()))
        return
      onChange([...value, { memberId: null, label }])
      setFreeName('')
    } else if (choice) {
      onChange([...value, { memberId: choice, label: '' }])
    }
    setChoice('')
  }

  return (
    <div className="field form-grid__full contributors">
      <span className="field__label" id="contributors-label">
        Contributeurs
      </span>
      {value.length > 0 ? (
        <ul className="chips" aria-labelledby="contributors-label">
          {value.map((p, i) => (
            <li key={`${p.memberId ?? p.label}-${i}`} className="chip">
              {nameOf(p)}
              <button
                type="button"
                className="chip__remove"
                aria-label={`Retirer ${nameOf(p)}`}
                onClick={() => onChange(value.filter((_, j) => j !== i))}
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <span className="field__hint">Aucun contributeur.</span>
      )}
      <div className="contributors__add">
        <select
          aria-label="Ajouter un contributeur"
          value={choice}
          onChange={(e) => setChoice(e.target.value)}
        >
          <option value="">Choisir une personne…</option>
          {available.map((m) => (
            <option key={m.id} value={m.id}>
              {m.display_name ?? m.email}
              {m.is_me ? ' (moi)' : ''}
            </option>
          ))}
          <option value="__free">Autre personne (nom libre)…</option>
        </select>
        {choice === '__free' && (
          <input
            aria-label="Nom du contributeur"
            placeholder="Ex. : Agence partenaire"
            maxLength={120}
            value={freeName}
            onChange={(e) => setFreeName(e.target.value)}
          />
        )}
        <button
          type="button"
          className="button button--small"
          disabled={!choice || (choice === '__free' && !freeName.trim())}
          onClick={add}
        >
          Ajouter
        </button>
      </div>
      <span className="field__hint">
        Les personnes qui participent au projet, en plus du responsable. Cela ne leur donne aucun
        droit dans PILOT.
      </span>
    </div>
  )
}
