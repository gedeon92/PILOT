import { describe, expect, it } from 'vitest'
import type { Project } from './api/client'
import { eventDays, findOverlaps } from './events'

function event(id: string, fields: Partial<Project>): Project {
  return {
    id,
    title: id,
    status: 'in_progress',
    start_date: null,
    end_date: null,
    due_date: null,
    window_start: null,
    window_end: null,
    ...fields,
  } as Project
}

describe('règles du calendrier des événements', () => {
  it('une période à préciser n’a pas de jours fixés (CAL01)', () => {
    expect(
      eventDays(event('a', { window_start: '2026-12-01', window_end: '2026-12-31' })),
    ).toBeNull()
    expect(eventDays(event('b', { start_date: '2026-11-12', end_date: '2026-11-13' }))).toEqual({
      from: '2026-11-12',
      to: '2026-11-13',
    })
  })

  it('signale deux événements avec un jour commun', () => {
    const overlaps = findOverlaps([
      event('salon', { start_date: '2026-11-12', end_date: '2026-11-14' }),
      event('seminaire', { start_date: '2026-11-14' }),
      event('gala', { start_date: '2026-11-20' }),
    ])
    expect(overlaps.map((o) => [o.a.id, o.b.id, o.from, o.to])).toEqual([
      ['salon', 'seminaire', '2026-11-14', '2026-11-14'],
    ])
  })

  it('ignore une édition annulée (CAL02)', () => {
    const overlaps = findOverlaps([
      event('salon', { start_date: '2026-11-12' }),
      event('ancien', { start_date: '2026-11-12', status: 'cancelled' }),
    ])
    expect(overlaps).toEqual([])
  })
})
