import type { Project } from './api/client'
import { addDays } from './labels'

export type Zoom = 'month' | 'quarter' | 'semester'

export const ZOOMS: Record<Zoom, { label: string; months: number; step: number; before: number }> =
  {
    month: { label: 'Mois', months: 1, step: 1, before: 0 },
    quarter: { label: 'Trimestre', months: 3, step: 3, before: 1 },
    semester: { label: 'Semestre', months: 6, step: 6, before: 1 },
  }

const DAY_MS = 86_400_000

function utc(iso: string) {
  return new Date(`${iso}T00:00:00Z`).getTime()
}

function iso(ms: number) {
  return new Date(ms).toISOString().slice(0, 10)
}

export type TimeWindow = {
  start: string
  /** Premier jour après la période (exclu). */
  end: string
  totalDays: number
  months: { label: string; from: string; days: number }[]
  /** Position d'un jour en % de la largeur, au milieu du jour. */
  percent: (day: string) => number
  /** Position du début d'un jour en %. */
  edge: (day: string) => number
}

/** Période affichée selon le zoom ; `offset` avance ou recule d'un pas (1, 3 ou 6 mois). */
export function timeWindow(today: string, zoom: Zoom, offset: number): TimeWindow {
  const { months, step, before } = ZOOMS[zoom]
  const d = new Date(utc(today))
  const year = d.getUTCFullYear()
  const firstMonth = d.getUTCMonth() - before + offset * step
  const start = Date.UTC(year, firstMonth, 1)
  const end = Date.UTC(year, firstMonth + months, 1)
  const totalDays = (end - start) / DAY_MS
  const monthFormat = new Intl.DateTimeFormat('fr-FR', { month: 'long', timeZone: 'UTC' })
  const yearFormat = new Intl.DateTimeFormat('fr-FR', {
    month: 'long',
    year: 'numeric',
    timeZone: 'UTC',
  })
  const list = Array.from({ length: months }, (_, i) => {
    const from = Date.UTC(year, firstMonth + i, 1)
    const to = Date.UTC(year, firstMonth + i + 1, 1)
    const text = (i === 0 || new Date(from).getUTCMonth() === 0 ? yearFormat : monthFormat).format(
      from,
    )
    return {
      label: text.charAt(0).toUpperCase() + text.slice(1),
      from: iso(from),
      days: (to - from) / DAY_MS,
    }
  })
  const edge = (day: string) => ((utc(day) - start) / DAY_MS / totalDays) * 100
  return {
    start: iso(start),
    end: iso(end),
    totalDays,
    months: list,
    edge,
    percent: (day: string) => edge(day) + 50 / totalDays,
  }
}

export type Span = { from: string; to: string; kind: 'dates' | 'window' | 'due' }

/** Position d'un projet : début/fin, sinon période à préciser, sinon échéance seule. */
export function projectSpan(p: Project): Span | null {
  if (p.start_date || p.end_date) {
    const from = p.start_date ?? p.end_date!
    const to = p.end_date ?? (p.due_date && p.due_date > from ? p.due_date : from)
    return { from, to: to < from ? from : to, kind: 'dates' }
  }
  if (p.window_start && p.window_end)
    return { from: p.window_start, to: p.window_end, kind: 'window' }
  if (p.due_date) return { from: p.due_date, to: p.due_date, kind: 'due' }
  return null
}

export function overlapsWindow(span: Span, w: TimeWindow) {
  return span.to >= w.start && span.from < w.end
}

/** Lundis de la période, pour les repères de semaines en vue « mois ». */
export function mondays(w: TimeWindow): string[] {
  const days: string[] = []
  for (let day = w.start; day < w.end; day = addDays(day, 1)) {
    if (new Date(utc(day)).getUTCDay() === 1) days.push(day)
  }
  return days
}

export function weekends(w: TimeWindow): string[] {
  const days: string[] = []
  for (let day = w.start; day < w.end; day = addDays(day, 1)) {
    const weekday = new Date(utc(day)).getUTCDay()
    if (weekday === 0 || weekday === 6) days.push(day)
  }
  return days
}
