import { useState } from 'react'
import type { Member } from '../api/client'

import type { PersonValue } from '../person'

export type { PersonValue }

const OTHER = '__autre'

/** Choix d'un responsable : un membre de l'espace, ou un nom libre (sans compte ni rappel). */
export function PersonField({
  id,
  label,
  members,
  value,
  onChange,
}: {
  id: string
  label: string
  members: Member[]
  value: PersonValue
  onChange: (value: PersonValue) => void
}) {
  const active = members.filter((m) => m.status === 'active')
  // Choisir « nom libre » doit afficher le champ même tant qu'aucun nom n'est saisi.
  const [freeName, setFreeName] = useState(() => !value.memberId && Boolean(value.label))
  const selected = value.memberId ?? (freeName ? OTHER : '')

  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <select
        id={id}
        value={selected}
        onChange={(e) => {
          const next = e.target.value
          setFreeName(next === OTHER)
          if (next === OTHER) onChange({ memberId: null, label: value.label })
          else if (next === '') onChange({ memberId: null, label: '' })
          else onChange({ memberId: next, label: '' })
        }}
      >
        <option value="">Non attribué</option>
        {active.map((m) => (
          <option key={m.id} value={m.id}>
            {m.display_name ?? m.email}
            {m.is_me ? ' (moi)' : ''}
          </option>
        ))}
        <option value={OTHER}>Autre personne (nom libre)…</option>
      </select>
      {selected === OTHER && (
        <>
          <input
            aria-label={`${label} : nom`}
            placeholder="Ex. : Mon assistante"
            maxLength={120}
            value={value.label}
            onChange={(e) => onChange({ memberId: null, label: e.target.value })}
          />
          <span className="field__hint">
            Sans compte PILOT : cette personne ne reçoit pas de rappel.
          </span>
        </>
      )}
    </div>
  )
}
