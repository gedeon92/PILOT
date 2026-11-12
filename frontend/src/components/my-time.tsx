import { useState, type FormEvent } from 'react'
import { errorMessage, type MyTime } from '../api/client'
import { useAddTime, useDeleteTime, useMyTime } from '../api/queries'
import { formatDay } from '../labels'
import { Alert } from './ui'

/** « Mon temps » : chacun déclare son temps passé, par type. Le détail reste personnel ; seul
 * le total sert à l'indicateur « Temps stratégique ». Rien n'est déduit des connexions. */

const TIME_CATEGORY: Record<MyTime['entries'][number]['category'], string> = {
  strategic: 'Stratégique',
  coordination: 'Coordination',
  operational: 'Opérationnel',
  admin: 'Administratif',
}

const hours = (minutes: number) =>
  `${Math.floor(minutes / 60)} h${minutes % 60 ? ` ${String(minutes % 60).padStart(2, '0')}` : ''}`

export function MyTimeCard({
  spaceId,
  start,
  end,
  today,
}: {
  spaceId: string
  start: string
  end: string
  today: string
}) {
  const time = useMyTime(spaceId, start, end)
  const add = useAddTime(spaceId)
  const remove = useDeleteTime(spaceId)
  const [day, setDay] = useState(today)
  const [duration, setDuration] = useState('1')
  const [category, setCategory] = useState<keyof typeof TIME_CATEGORY>('strategic')
  const [note, setNote] = useState('')

  function submit(event: FormEvent) {
    event.preventDefault()
    add.mutate(
      { day, minutes: Math.round(Number(duration) * 60), category, note: note.trim() || null },
      { onSuccess: () => setNote('') },
    )
  }

  const data = time.data
  const share =
    data && data.total_minutes
      ? Math.round((100 * data.strategic_minutes) / data.total_minutes)
      : null

  return (
    <section className="card-panel" aria-labelledby="my-time-title">
      <div className="card-panel__head">
        <div>
          <h2 id="my-time-title">Mon temps</h2>
          <p className="card-panel__help">
            Notez le temps passé et son type. Ce détail est personnel : seul le total compte pour
            l’indicateur « Temps stratégique ».
          </p>
        </div>
      </div>
      {time.isError && <Alert>{errorMessage(time.error)}</Alert>}
      {data && data.total_minutes > 0 && (
        <p className="my-time__total">
          {hours(data.total_minutes)} déclarées · dont {hours(data.strategic_minutes)} stratégiques
          {share !== null && ` (${share} %)`}
        </p>
      )}
      {data && data.entries.length > 0 && (
        <ul className="item-list">
          {data.entries.map((e) => (
            <li key={e.id} className="item-row">
              <span className="item-row__text">
                <span className="item-row__name">
                  {hours(e.minutes)} · {TIME_CATEGORY[e.category]}
                </span>
                <span className="item-row__details">
                  {start !== end && `${formatDay(e.day)} · `}
                  {e.note ?? ''}
                </span>
              </span>
              <span className="item-row__actions">
                <button
                  type="button"
                  className="button button--small button--ghost"
                  disabled={remove.isPending}
                  onClick={() => remove.mutate(e.id)}
                >
                  Retirer
                </button>
              </span>
            </li>
          ))}
        </ul>
      )}
      <form className="inline-form my-time__form" onSubmit={submit} aria-label="Déclarer du temps">
        {start !== end && (
          <>
            <label htmlFor="time-day">Jour</label>
            <input
              id="time-day"
              type="date"
              required
              max={today}
              value={day}
              onChange={(e) => setDay(e.target.value)}
            />
          </>
        )}
        <label htmlFor="time-hours">Heures</label>
        <input
          id="time-hours"
          type="number"
          min={0.25}
          max={24}
          step={0.25}
          required
          value={duration}
          onChange={(e) => setDuration(e.target.value)}
        />
        <label htmlFor="time-category">Type</label>
        <select
          id="time-category"
          value={category}
          onChange={(e) => setCategory(e.target.value as keyof typeof TIME_CATEGORY)}
        >
          {Object.entries(TIME_CATEGORY).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
        <label htmlFor="time-note" className="visually-hidden">
          Note
        </label>
        <input
          id="time-note"
          maxLength={300}
          placeholder="Note (facultatif)"
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
        <button className="button button--small button--primary" disabled={add.isPending}>
          Ajouter
        </button>
      </form>
      {add.isError && <Alert>{errorMessage(add.error)}</Alert>}
      {remove.isError && <Alert>{errorMessage(remove.error)}</Alert>}
    </section>
  )
}
