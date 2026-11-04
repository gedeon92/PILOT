import type { Project } from './api/client'
import { addDays, isClosedProject } from './labels'
import { projectSpan } from './timeline'

/** Règles d'attention partagées par la vue d'ensemble et les listes filtrées (CDC §7). */
export type Attention = 'retard' | 'bloques' | 'semaine' | 'a-completer' | 'vigilance'

export const ATTENTION: Record<Attention, { label: string; rule: string }> = {
  retard: {
    label: 'En retard',
    rule: 'Projet ouvert dont l’échéance est dépassée, ou qui a au moins une tâche en retard.',
  },
  bloques: { label: 'Bloqués', rule: 'Projet au statut « Bloqué ».' },
  semaine: {
    label: 'Échéance sous 7 jours',
    rule: 'Projet ouvert dont l’échéance tombe aujourd’hui ou dans les 6 jours suivants.',
  },
  'a-completer': {
    label: 'À compléter',
    rule: 'Projet ouvert sans responsable du suivi ou sans prochaine étape.',
  },
  vigilance: {
    label: 'Vigilance',
    rule: 'Projet ouvert avec une vigilance « À surveiller » ou « Élevé ».',
  },
}

export function matchesAttention(p: Project, attention: Attention, today: string): boolean {
  if (isClosedProject(p.status)) return false
  switch (attention) {
    case 'retard':
      return (p.due_date !== null && p.due_date < today) || p.late_tasks > 0
    case 'bloques':
      return p.status === 'blocked'
    case 'semaine':
      return p.due_date !== null && p.due_date >= today && p.due_date <= addDays(today, 6)
    case 'a-completer':
      return !p.owner.name || !p.next_step
    case 'vigilance':
      return p.risk_level !== null
  }
}

/** Le projet a-t-il une date (dates, période ou échéance) dans l'intervalle [from, to] ? */
export function inPeriod(p: Project, from: string, to: string): boolean {
  const span = projectSpan(p)
  if (!span) return false
  return span.to >= (from || '0000-01-01') && span.from <= (to || '9999-12-31')
}
