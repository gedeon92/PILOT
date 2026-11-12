import { useState } from 'react'
import { errorMessage } from '../api/client'
import { holidayPreset, useHolidays, useSaveHolidays } from '../api/queries'
import { formatDay } from '../labels'
import { Alert } from './ui'

/** Paramètres → Jours fériés : la liste de l'espace. Les routines « jours ouvrés » ne tombent
 * pas un jour férié, et les délais en jours ouvrés (contacts d'un événement) les sautent. */
export function HolidaysSettings({ spaceId, canManage }: { spaceId: string; canManage: boolean }) {
  const current = useHolidays(spaceId)
  const save = useSaveHolidays(spaceId)
  // Brouillon : null tant que rien n'a été modifié (la liste enregistrée s'affiche).
  const [draft, setList] = useState<{ date: string; label: string }[] | null>(null)
  const list = draft ?? current.data?.holidays ?? []
  const [date, setDate] = useState('')
  const [label, setLabel] = useState('')
  const [country, setCountry] = useState('SN')
  const [year, setYear] = useState(() => String(new Date().getFullYear() + 1))
  const [note, setNote] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const changed = JSON.stringify(list) !== JSON.stringify(current.data?.holidays ?? [])
  const sorted = [...list].sort((a, b) => a.date.localeCompare(b.date))

  async function prefill() {
    setError(null)
    try {
      const preset = await holidayPreset(spaceId, country, Number(year))
      const known = new Set(list.map((h) => h.date))
      setList([...list, ...preset.holidays.filter((h) => !known.has(h.date))])
      setNote(preset.note)
    } catch (e) {
      setError(errorMessage(e))
    }
  }

  return (
    <section className="card-panel" aria-labelledby="title-holidays">
      <div className="card-panel__head">
        <div>
          <h2 id="title-holidays">Jours fériés</h2>
          <p className="card-panel__help">
            Les routines en jours ouvrés ne tombent pas un jour férié (une routine au jour du mois
            passe au jour ouvré précédent), et les délais en jours ouvrés les sautent.
          </p>
        </div>
      </div>
      {current.isError && <Alert>{errorMessage(current.error)}</Alert>}
      {canManage && (
        <div className="filters" role="group" aria-label="Pré-remplir les jours fériés">
          <select aria-label="Pays" value={country} onChange={(e) => setCountry(e.target.value)}>
            {Object.entries(current.data?.countries ?? { SN: 'Sénégal', FR: 'France' }).map(
              ([code, name]) => (
                <option key={code} value={code}>
                  {name}
                </option>
              ),
            )}
          </select>
          <input
            aria-label="Année"
            type="number"
            min={2000}
            max={2100}
            value={year}
            onChange={(e) => setYear(e.target.value)}
          />
          <button type="button" className="button button--small" onClick={() => void prefill()}>
            Ajouter les jours fériés de l’année
          </button>
        </div>
      )}
      {note && <Alert tone="info">{note}</Alert>}
      {error && <Alert>{error}</Alert>}
      {sorted.length === 0 ? (
        <p className="muted">Aucun jour férié enregistré.</p>
      ) : (
        <ul className="item-list">
          {sorted.map((h) => (
            <li key={h.date} className="item-row">
              <span className="item-row__text">
                <span className="item-row__name">{h.label}</span>
                <span className="item-row__details">{formatDay(h.date)}</span>
              </span>
              {canManage && (
                <span className="item-row__actions">
                  <button
                    type="button"
                    className="button button--small button--ghost"
                    aria-label={`Retirer ${h.label} du ${formatDay(h.date)}`}
                    onClick={() => setList(list.filter((x) => x.date !== h.date))}
                  >
                    Retirer
                  </button>
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
      {canManage && (
        <form
          className="inline-form"
          onSubmit={(e) => {
            e.preventDefault()
            setList([...list.filter((h) => h.date !== date), { date, label: label.trim() }])
            setDate('')
            setLabel('')
          }}
        >
          <label htmlFor="holiday-date">Date</label>
          <input
            id="holiday-date"
            type="date"
            required
            value={date}
            onChange={(e) => setDate(e.target.value)}
          />
          <label htmlFor="holiday-label">Nom</label>
          <input
            id="holiday-label"
            required
            maxLength={80}
            placeholder="ex. Tabaski"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
          />
          <button className="button button--small">Ajouter</button>
        </form>
      )}
      {canManage && changed && (
        <div className="item-form__actions">
          <button
            type="button"
            className="button button--primary"
            disabled={save.isPending}
            onClick={() =>
              save.mutate(sorted, {
                onSuccess: () => {
                  setNote(null)
                  setList(null)
                },
              })
            }
          >
            Enregistrer les jours fériés
          </button>
          <button type="button" className="button button--ghost" onClick={() => setList(null)}>
            Annuler
          </button>
        </div>
      )}
      {save.isError && <Alert>{errorMessage(save.error)}</Alert>}
    </section>
  )
}
