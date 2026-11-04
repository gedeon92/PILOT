import { describe, expect, it } from 'vitest'
import type { Project } from './api/client'
import { mondays, projectSpan, timeWindow } from './timeline'

const p = (fields: Partial<Project>) =>
  ({
    start_date: null,
    end_date: null,
    due_date: null,
    window_start: null,
    window_end: null,
    ...fields,
  }) as Project

describe('timeline', () => {
  it('le trimestre montre le mois précédent, le mois en cours et le suivant', () => {
    const w = timeWindow('2026-11-04', 'quarter', 0)
    expect([w.start, w.end]).toEqual(['2026-10-01', '2027-01-01'])
    expect(w.months.map((m) => m.label)).toEqual(['Octobre 2026', 'Novembre', 'Décembre'])
  })

  it('les flèches avancent d’un pas complet, avec l’année au changement d’année', () => {
    const next = timeWindow('2026-11-04', 'quarter', 1)
    expect(next.start).toBe('2027-01-01')
    expect(next.months[0].label).toBe('Janvier 2027')
    expect(timeWindow('2026-11-04', 'month', -1).start).toBe('2026-10-01')
  })

  it('place les jours proportionnellement', () => {
    const w = timeWindow('2026-11-04', 'month', 0)
    expect(w.edge('2026-11-01')).toBe(0)
    expect(w.edge('2026-12-01')).toBe(100)
    expect(mondays(w)[0]).toBe('2026-11-02')
  })

  it('choisit la position du projet : dates, sinon période, sinon échéance', () => {
    expect(projectSpan(p({ start_date: '2026-11-10', end_date: '2026-11-20' }))).toEqual({
      from: '2026-11-10',
      to: '2026-11-20',
      kind: 'dates',
    })
    expect(projectSpan(p({ window_start: '2026-12-01', window_end: '2026-12-31' }))?.kind).toBe(
      'window',
    )
    expect(projectSpan(p({ due_date: '2026-11-12' }))?.kind).toBe('due')
    expect(projectSpan(p({}))).toBeNull()
  })
})
