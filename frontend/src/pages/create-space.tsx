import { useMemo, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router'
import { errorMessage } from '../api/client'
import { useCreateSpace, useMe } from '../api/queries'
import { Alert, AuthCard } from '../components/ui'
import { allTimezones, detectedTimezone } from '../timezones'

export function CreateSpacePage() {
  const me = useMe()
  const navigate = useNavigate()
  const create = useCreateSpace()
  const [name, setName] = useState('')
  const [timezone, setTimezone] = useState(detectedTimezone)
  const zones = useMemo(() => allTimezones(timezone), [timezone])
  const hasSpaces = (me.data?.spaces.length ?? 0) > 0

  function submit(event: FormEvent) {
    event.preventDefault()
    create.mutate(
      { name, timezone },
      { onSuccess: (space) => navigate(`/espaces/${space.id}`, { replace: true }) },
    )
  }

  return (
    <AuthCard
      title="Créer un espace"
      subtitle="Un espace regroupe les projets, les documents et les membres d’une organisation. Vous en serez propriétaire."
    >
      <form className="form" onSubmit={submit}>
        <div className="field">
          <label htmlFor="space-name">Nom de l’espace</label>
          <input
            id="space-name"
            required
            maxLength={120}
            placeholder="Ex. : Groupe Horizon"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor="space-tz">Fuseau horaire</label>
          <select id="space-tz" value={timezone} onChange={(e) => setTimezone(e.target.value)}>
            {zones.map((zone) => (
              <option key={zone} value={zone}>
                {zone}
              </option>
            ))}
          </select>
          <span className="field__hint">Utilisé pour les échéances et les rappels.</span>
        </div>
        {create.isError && <Alert>{errorMessage(create.error)}</Alert>}
        <button className="button button--primary" type="submit" disabled={create.isPending}>
          {create.isPending ? 'Création…' : 'Créer l’espace'}
        </button>
        {hasSpaces && (
          <Link className="button button--ghost" to="/">
            Annuler
          </Link>
        )}
      </form>
    </AuthCard>
  )
}
