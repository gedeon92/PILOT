import type { components } from './api/schema'
import type { Tone } from './components/ui'

type Schemas = components['schemas']
export type ProjectStatus = Schemas['ProjectStatus']
export type TaskStatus = Schemas['TaskStatus']
export type DateCertainty = Schemas['DateCertainty']
export type RiskLevel = Schemas['RiskLevel']
export type TaskRecurrence = Schemas['TaskRecurrence']

export const PROJECT_STATUS: Record<ProjectStatus, { label: string; tone: Tone }> = {
  to_frame: { label: 'À cadrer', tone: 'neutral' },
  to_launch: { label: 'À lancer', tone: 'neutral' },
  preparing: { label: 'En préparation', tone: 'violet' },
  in_progress: { label: 'En cours', tone: 'info' },
  awaiting_validation: { label: 'En attente de validation', tone: 'warn' },
  blocked: { label: 'Bloqué', tone: 'danger' },
  suspended: { label: 'Suspendu', tone: 'neutral' },
  done: { label: 'Terminé', tone: 'ok' },
  cancelled: { label: 'Annulé', tone: 'neutral' },
}

export const OPEN_PROJECT_STATUSES = (Object.keys(PROJECT_STATUS) as ProjectStatus[]).filter(
  (s) => s !== 'done' && s !== 'cancelled',
)

export function isClosedProject(status: ProjectStatus) {
  return status === 'done' || status === 'cancelled'
}

// Ordre d'affichage des menus : du sujet à préciser à la tâche clôturée (cahier V2, TCH03).
export const TASK_STATUS: Record<TaskStatus, { label: string; tone: Tone }> = {
  to_qualify: { label: 'À qualifier', tone: 'violet' },
  todo: { label: 'À faire', tone: 'neutral' },
  in_progress: { label: 'En cours', tone: 'info' },
  blocked: { label: 'Bloquée', tone: 'danger' },
  awaiting_validation: { label: 'En attente de validation', tone: 'warn' },
  done: { label: 'Terminée', tone: 'ok' },
  cancelled: { label: 'Annulée', tone: 'neutral' },
}

const SIMPLE_STATUSES: TaskStatus[] = ['todo', 'in_progress', 'done', 'cancelled']

/** Statuts proposés dans les menus : en mode simple, les quatre d'origine (plus le statut
 * actuel de la tâche s'il est avancé, pour qu'il reste lisible). */
export function taskStatusChoices(advanced: boolean, current?: TaskStatus): TaskStatus[] {
  const all = Object.keys(TASK_STATUS) as TaskStatus[]
  if (advanced) return all
  return all.filter((s) => SIMPLE_STATUSES.includes(s) || s === current)
}

export type TaskPriority = Schemas['TaskPriority']

export const TASK_PRIORITY: Record<TaskPriority, { label: string; tone: Tone }> = {
  low: { label: 'Basse', tone: 'neutral' },
  normal: { label: 'Normale', tone: 'neutral' },
  high: { label: 'Haute', tone: 'warn' },
  urgent: { label: 'Urgente', tone: 'danger' },
}

export const CERTAINTY: Record<DateCertainty, string> = {
  proposed: 'Proposée',
  announced: 'Annoncée',
  confirmed: 'Confirmée',
}

/** Rythme d'une tâche répétée : « Se répète chaque semaine ». */
export const RECURRENCE: Record<TaskRecurrence, string> = {
  daily: 'Chaque jour',
  weekly: 'Chaque semaine',
  monthly: 'Chaque mois',
  yearly: 'Chaque année',
}

export const RISK: Record<RiskLevel, string> = {
  watch: 'À surveiller',
  high: 'Élevé',
}

const dateFormat = new Intl.DateTimeFormat('fr-FR', {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
  timeZone: 'UTC',
})

/** Les dates de l'API sont des jours (AAAA-MM-JJ), sans heure ni fuseau. */
export function formatDay(iso: string | null | undefined): string {
  return iso ? dateFormat.format(new Date(`${iso}T00:00:00Z`)) : ''
}

const dateTimeFormat = new Intl.DateTimeFormat('fr-FR', {
  day: 'numeric',
  month: 'short',
  hour: '2-digit',
  minute: '2-digit',
})

export function formatMoment(iso: string): string {
  return dateTimeFormat.format(new Date(iso))
}

/** Le jour courant (AAAA-MM-JJ) dans un fuseau donné. */
export function todayIso(timeZone: string): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone }).format(new Date())
}

export function addDays(iso: string, days: number): string {
  const date = new Date(`${iso}T00:00:00Z`)
  date.setUTCDate(date.getUTCDate() + days)
  return date.toISOString().slice(0, 10)
}
