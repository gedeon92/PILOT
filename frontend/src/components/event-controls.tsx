import { useState } from 'react'
import { errorMessage } from '../api/client'
import { useEventControls, useSetEventControl } from '../api/queries'
import { formatDay, formatMoment } from '../labels'
import { Alert, StatusPill } from './ui'

/** Étape F6 : contrôles d'un événement — cibles prioritaires confirmées à J−10, répétition la
 * veille, contacts qualifiés transmis sous cinq jours ouvrés, bilan chiffré sous dix jours. */
export function EventControls({
  spaceId,
  projectId,
  canWrite,
  today,
}: {
  spaceId: string
  projectId: string
  canWrite: boolean
  today: string
}) {
  const controls = useEventControls(spaceId, projectId)
  const set = useSetEventControl(spaceId, projectId)
  const [notes, setNotes] = useState<Record<string, string>>({})
  if (controls.isPending || controls.isError) return null
  return (
    <section className="card-panel" aria-labelledby="event-controls-title">
      <h2 id="event-controls-title">Contrôles de l’événement</h2>
      <ul className="event-controls">
        {controls.data.map((c) => {
          const soon = !c.done_at && c.due_date !== null && c.due_date >= today
          return (
            <li key={c.key} className="event-controls__item">
              <div className="event-controls__line">
                <label className="checkbox">
                  <input
                    type="checkbox"
                    checked={Boolean(c.done_at)}
                    disabled={!canWrite || set.isPending}
                    onChange={(e) =>
                      set.mutate({ key: c.key, done: e.target.checked, note: notes[c.key] || null })
                    }
                  />
                  {c.label}
                </label>
                {c.done_at ? (
                  <StatusPill tone="ok">Fait</StatusPill>
                ) : c.late ? (
                  <StatusPill tone="danger">En retard</StatusPill>
                ) : soon ? (
                  <StatusPill tone="info">À venir</StatusPill>
                ) : null}
              </div>
              <span className="muted event-controls__meta">
                {c.due_date ? `Pour le ${formatDay(c.due_date)}` : 'Date de l’événement à fixer'}
                {c.done_at &&
                  ` · fait le ${formatMoment(c.done_at)}${c.done_by ? ` par ${c.done_by}` : ''}`}
                {c.note && ` · ${c.note}`}
              </span>
              {canWrite && !c.done_at && (
                <>
                  <label className="visually-hidden" htmlFor={`ctl-${c.key}`}>
                    Note pour « {c.label} »
                  </label>
                  <input
                    id={`ctl-${c.key}`}
                    className="event-controls__note"
                    placeholder="Note (facultatif), ex. 12 cibles sur 15 confirmées"
                    value={notes[c.key] ?? ''}
                    onChange={(e) => setNotes((n) => ({ ...n, [c.key]: e.target.value }))}
                  />
                </>
              )}
            </li>
          )
        })}
      </ul>
      {set.isError && <Alert>{errorMessage(set.error)}</Alert>}
    </section>
  )
}
