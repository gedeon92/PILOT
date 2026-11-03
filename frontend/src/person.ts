import type { PersonRef } from './api/client'

export type PersonValue = { memberId: string | null; label: string }

export function personValue(ref: PersonRef): PersonValue {
  return ref.member_id
    ? { memberId: ref.member_id, label: '' }
    : { memberId: null, label: ref.name ?? '' }
}

/** Champs à envoyer à l'API pour un responsable de projet ou de tâche. */
export function personPayload(value: PersonValue, prefix: 'owner' | 'assignee') {
  return value.memberId
    ? { [`${prefix}_member_id`]: value.memberId }
    : { [`${prefix}_member_id`]: null, [`${prefix}_label`]: value.label.trim() || null }
}
