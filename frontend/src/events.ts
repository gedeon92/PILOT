import type { Project } from './api/client'

/** Jours d'un événement : début → fin, ou l'échéance seule. Une période à préciser n'en a pas. */
export function eventDays(p: Project): { from: string; to: string } | null {
  const from = p.start_date ?? p.due_date
  if (!from) return null
  const to = p.end_date ?? from
  return { from, to: to < from ? from : to }
}

export type Overlap = { a: Project; b: Project; from: string; to: string }

/** Règle de chevauchement : au moins un jour commun entre deux événements non annulés. */
export function findOverlaps(events: Project[]): Overlap[] {
  const dated = events
    .filter((p) => p.status !== 'cancelled')
    .map((p) => ({ p, d: eventDays(p) }))
    .filter((x): x is { p: Project; d: { from: string; to: string } } => x.d !== null)
  const overlaps: Overlap[] = []
  for (let i = 0; i < dated.length; i++) {
    for (let j = i + 1; j < dated.length; j++) {
      const from = dated[i].d.from > dated[j].d.from ? dated[i].d.from : dated[j].d.from
      const to = dated[i].d.to < dated[j].d.to ? dated[i].d.to : dated[j].d.to
      if (from <= to) overlaps.push({ a: dated[i].p, b: dated[j].p, from, to })
    }
  }
  return overlaps
}
