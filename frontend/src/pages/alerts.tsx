import { useState } from 'react'
import { Link, useOutletContext } from 'react-router'
import { errorMessage, type AlertItem, type AlertPreferences } from '../api/client'
import {
  useAlertPreferences,
  useAlerts,
  useMarkAlertRead,
  useMarkAllAlertsRead,
  useSaveAlertPreferences,
  useSendTestEmail,
} from '../api/queries'
import { BellIcon } from '../components/icons'
import { Alert, PageHeader } from '../components/ui'
import { formatDay, todayIso } from '../labels'
import type { SpaceContext } from './space-layout'

const RULE_TONE: Record<string, string> = {
  overdue: 'danger',
  blocked: 'danger',
  due_soon: 'warn',
  decision_pending: 'warn',
  stale: 'neutral',
  missing_info: 'neutral',
}

function AlertRow({ alert, spaceId }: { alert: AlertItem; spaceId: string }) {
  const markRead = useMarkAlertRead(spaceId)
  return (
    <li className={alert.read ? 'alert-row alert-row--read' : 'alert-row'}>
      <span className={`todo__tag todo__tag--${RULE_TONE[alert.rule] ?? 'neutral'} alert-row__tag`}>
        {alert.rule_label}
      </span>
      <Link
        className="alert-row__text"
        to={`/espaces/${spaceId}/projets/${alert.project_id}`}
        onClick={() => !alert.read && markRead.mutate(alert.id)}
      >
        <span className="alert-row__title">{alert.title}</span>
        <span className="alert-row__detail">{alert.detail}</span>
      </Link>
      {alert.read ? (
        <span className="muted alert-row__state">Lu</span>
      ) : (
        <button
          type="button"
          className="button button--small"
          disabled={markRead.isPending}
          onClick={() => markRead.mutate(alert.id)}
        >
          Marquer comme lu
        </button>
      )}
    </li>
  )
}

function Preferences({ spaceId, prefs }: { spaceId: string; prefs: AlertPreferences }) {
  const save = useSaveAlertPreferences(spaceId)
  const test = useSendTestEmail(spaceId)
  const [disabled, setDisabled] = useState<string[]>(prefs.disabled_rules)
  const [digest, setDigest] = useState(prefs.email_digest)
  const [hour, setHour] = useState(prefs.digest_hour)
  const changed =
    digest !== prefs.email_digest ||
    hour !== prefs.digest_hour ||
    [...disabled].sort().join() !== [...prefs.disabled_rules].sort().join()

  return (
    <section className="card-panel" aria-labelledby="prefs-title">
      <div className="card-panel__head">
        <div>
          <h2 id="prefs-title">Mes préférences</h2>
          <p className="card-panel__help">Elles ne concernent que vous, dans cet espace.</p>
        </div>
      </div>

      <fieldset className="prefs__group">
        <legend>Alertes à recevoir</legend>
        {Object.entries(prefs.rules).map(([rule, label]) => (
          <label key={rule} className="checkbox">
            <input
              type="checkbox"
              checked={!disabled.includes(rule)}
              onChange={(e) =>
                setDisabled(
                  e.target.checked ? disabled.filter((r) => r !== rule) : [...disabled, rule],
                )
              }
            />
            {label}
          </label>
        ))}
      </fieldset>

      <fieldset className="prefs__group">
        <legend>Récapitulatif par e-mail</legend>
        <label className="checkbox">
          <input type="checkbox" checked={digest} onChange={(e) => setDigest(e.target.checked)} />
          Recevoir chaque jour un récapitulatif de mes alertes
        </label>
        <label className="prefs__hour">
          Heure d’envoi (fuseau de l’espace)
          <select value={hour} disabled={!digest} onChange={(e) => setHour(Number(e.target.value))}>
            {Array.from({ length: 24 }, (_, h) => (
              <option key={h} value={h}>
                {String(h).padStart(2, '0')}h00
              </option>
            ))}
          </select>
        </label>
        {!prefs.email_available && (
          <Alert tone="warn">
            L’envoi d’e-mails n’est pas encore activé sur PILOT : les alertes restent visibles ici.
          </Alert>
        )}
      </fieldset>

      <div className="form-actions">
        <button
          type="button"
          className="button button--primary"
          disabled={!changed || save.isPending}
          onClick={() =>
            save.mutate({ disabled_rules: disabled, email_digest: digest, digest_hour: hour })
          }
        >
          Enregistrer
        </button>
        <button
          type="button"
          className="button"
          disabled={!prefs.email_available || test.isPending}
          onClick={() => test.mutate()}
        >
          {test.isPending ? 'Envoi…' : 'M’envoyer un e-mail de test'}
        </button>
      </div>
      {save.isSuccess && !changed && <Alert tone="ok">Préférences enregistrées.</Alert>}
      {save.isError && <Alert>{errorMessage(save.error)}</Alert>}
      {test.data && <Alert tone={test.data.sent ? 'ok' : 'warn'}>{test.data.message}</Alert>}
      {test.isError && <Alert>{errorMessage(test.error)}</Alert>}
    </section>
  )
}

export function AlertsPage() {
  const { space } = useOutletContext<SpaceContext>()
  const alerts = useAlerts(space.id)
  const prefs = useAlertPreferences(space.id)
  const readAll = useMarkAllAlertsRead(space.id)
  const today = todayIso(space.timezone)
  const items = alerts.data?.items ?? []
  const todays = items.filter((a) => a.alert_date === today)
  const earlier = items.filter((a) => a.alert_date !== today)

  return (
    <div className="page-content">
      <PageHeader
        title="Alertes"
        subtitle="Vos rappels du jour et des deux dernières semaines. Une alerte invite à vérifier, elle ne juge pas le projet."
        actions={
          (alerts.data?.unread ?? 0) > 0 && (
            <button
              type="button"
              className="button"
              disabled={readAll.isPending}
              onClick={() => readAll.mutate()}
            >
              Tout marquer comme lu
            </button>
          )
        }
      />
      {alerts.isError && <Alert>{errorMessage(alerts.error)}</Alert>}

      <section className="card-panel" aria-labelledby="today-title">
        <h2 id="today-title">
          Aujourd’hui <span className="count">{todays.length}</span>
        </h2>
        {alerts.isPending && <p className="muted">Chargement…</p>}
        {!alerts.isPending && todays.length === 0 && (
          <div className="mini-empty">
            <span className="icon-tile icon-tile--neutral">
              <BellIcon size={18} />
            </span>
            <p>
              <strong>Aucune alerte aujourd’hui.</strong> Elles apparaissent quand une échéance
              approche, est dépassée, ou quand un projet est bloqué ou à compléter.
            </p>
          </div>
        )}
        {todays.length > 0 && (
          <ul className="alert-list">
            {todays.map((a) => (
              <AlertRow key={a.id} alert={a} spaceId={space.id} />
            ))}
          </ul>
        )}
      </section>

      {earlier.length > 0 && (
        <details className="card-panel">
          <summary className="alerts__earlier">Jours précédents · {earlier.length}</summary>
          <ul className="alert-list">
            {earlier.map((a) => (
              <li key={a.id} className="alert-day">
                <span className="muted">{formatDay(a.alert_date)}</span>
                <ul className="alert-list alert-list--nested">
                  <AlertRow alert={a} spaceId={space.id} />
                </ul>
              </li>
            ))}
          </ul>
        </details>
      )}

      {prefs.data && (
        <Preferences key={JSON.stringify(prefs.data)} spaceId={space.id} prefs={prefs.data} />
      )}
    </div>
  )
}
