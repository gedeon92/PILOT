import { useState, type CSSProperties } from 'react'
import { Link } from 'react-router'
import type { Project, Task } from '../api/client'
import { colorHex } from '../colors'
import { addDays, formatDay, isClosedProject, PROJECT_STATUS } from '../labels'
import {
  mondays,
  overlapsWindow,
  projectSpan,
  timeWindow,
  weekends,
  ZOOMS,
  type Span,
  type Zoom,
} from '../timeline'
import type { Tone } from './ui'

const TONE_COLOR: Record<Tone, string> = {
  info: '#2563EB',
  danger: '#DC2626',
  warn: '#CA8A04',
  violet: '#7C3AED',
  ok: '#16A34A',
  neutral: '#71717A',
}

const shortDay = new Intl.DateTimeFormat('fr-FR', {
  day: 'numeric',
  month: 'short',
  timeZone: 'UTC',
})

function short(day: string) {
  return shortDay.format(new Date(`${day}T00:00:00Z`))
}

function spanText(span: Span) {
  if (span.kind === 'due' || span.from === span.to) return short(span.from)
  return `${short(span.from)} → ${short(span.to)}`
}

function initials(name: string) {
  return name
    .split(/\s+/)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase())
    .join('')
}

type Row = { project: Project; span: Span; tasks: Task[] }

function Tooltip({ row, today }: { row: Row; today: string }) {
  const { project: p, span } = row
  const status = PROJECT_STATUS[p.status]
  const late = row.tasks.filter((t) => t.late)
  const dueLate = !isClosedProject(p.status) && p.due_date !== null && p.due_date < today
  return (
    <div className="tl-tip" role="tooltip" id={`tip-${p.id}`}>
      <div className="tl-tip__head">
        <strong>{p.title}</strong>
        <span className={`tl-tip__status tl-tip__status--${status.tone}`}>{status.label}</span>
      </div>
      <dl className="tl-tip__list">
        <div>
          <dt>
            {span.kind === 'window'
              ? 'Période à préciser'
              : span.kind === 'due'
                ? 'Échéance'
                : 'Dates'}
          </dt>
          <dd>
            {span.kind === 'due'
              ? formatDay(span.from)
              : `${formatDay(span.from)} → ${formatDay(span.to)}`}
          </dd>
        </div>
        {span.kind !== 'due' && p.due_date && (
          <div>
            <dt>Échéance</dt>
            <dd className={dueLate ? 'tl-tip__late' : ''}>
              {formatDay(p.due_date)}
              {dueLate && ' · dépassée'}
            </dd>
          </div>
        )}
        <div>
          <dt>Responsable</dt>
          <dd>{p.owner.name ?? 'Non attribué'}</dd>
        </div>
        <div>
          <dt>Prochaine étape</dt>
          <dd>{p.next_step ?? 'À définir'}</dd>
        </div>
        {p.open_tasks > 0 && (
          <div>
            <dt>Tâches</dt>
            <dd>
              {p.open_tasks} ouverte(s)
              {late.length > 0 && <span className="tl-tip__late"> · {late.length} en retard</span>}
            </dd>
          </div>
        )}
      </dl>
    </div>
  )
}

export function ProjectTimeline({
  projects,
  tasks,
  today,
  spaceId,
  compact = false,
  maxRows,
  defaultZoom = 'quarter',
}: {
  projects: Project[]
  tasks: Task[]
  today: string
  spaceId: string
  compact?: boolean
  /** Nombre de lignes affichées en version compacte (adapté à la hauteur de l'écran). */
  maxRows?: number
  defaultZoom?: Zoom
}) {
  const [zoom, setZoom] = useState<Zoom>(defaultZoom)
  const [offset, setOffset] = useState(0)
  const [active, setActive] = useState<string | null>(null)
  const w = timeWindow(today, zoom, offset)
  const base = `/espaces/${spaceId}`

  const tasksByProject = new Map<string, Task[]>()
  for (const t of tasks)
    tasksByProject.set(t.project_id, [...(tasksByProject.get(t.project_id) ?? []), t])

  const open = projects.filter((p) => p.status !== 'cancelled')
  const rows: Row[] = open
    .map((project) => ({
      project,
      span: projectSpan(project),
      tasks: tasksByProject.get(project.id) ?? [],
    }))
    .filter((r): r is Row => r.span !== null && overlapsWindow(r.span, w))
    .sort((a, b) => a.span.from.localeCompare(b.span.from))
  const undated = open.filter((p) => !projectSpan(p)).length
  const shown = compact ? rows.slice(0, maxRows ?? 12) : rows

  // Regroupement par portefeuille, dans l'ordre d'apparition.
  const groups: { id: string; name: string; color: string; rows: Row[] }[] = []
  for (const row of shown) {
    const pf = row.project.portfolio
    let group = groups.find((g) => g.id === pf.id)
    if (!group) {
      group = { id: pf.id, name: pf.name, color: colorHex(pf.color) ?? '#71717A', rows: [] }
      groups.push(group)
    }
    group.rows.push(row)
  }
  const lateCount = rows.filter(
    (r) =>
      r.tasks.some((t) => t.late) ||
      (!isClosedProject(r.project.status) &&
        r.project.due_date !== null &&
        r.project.due_date < today),
  ).length
  const todayVisible = today >= w.start && today < w.end
  const clamp = (n: number) => Math.min(100, Math.max(0, n))
  let index = 0

  return (
    <div className={compact ? 'tl tl--compact' : 'tl'}>
      <div className="tl__toolbar">
        <div className="segmented" role="group" aria-label="Zoom de la timeline">
          {(Object.keys(ZOOMS) as Zoom[]).map((z) => (
            <button
              key={z}
              type="button"
              aria-pressed={zoom === z}
              className={zoom === z ? 'segmented__item segmented__item--on' : 'segmented__item'}
              onClick={() => {
                setZoom(z)
                setOffset(0)
              }}
            >
              {ZOOMS[z].label}
            </button>
          ))}
        </div>
        <div className="tl__nav">
          <button
            type="button"
            className="button button--small"
            aria-label="Période précédente"
            onClick={() => setOffset((o) => o - 1)}
          >
            ‹
          </button>
          <button
            type="button"
            className="button button--small"
            onClick={() => setOffset(0)}
            disabled={offset === 0}
          >
            Aujourd’hui
          </button>
          <button
            type="button"
            className="button button--small"
            aria-label="Période suivante"
            onClick={() => setOffset((o) => o + 1)}
          >
            ›
          </button>
        </div>
        <p className="tl__summary" aria-live="polite">
          <strong>{rows.length}</strong> projet(s) sur la période
          {lateCount > 0 && (
            <>
              {' · '}
              <span className="tl__summary-late">{lateCount} avec du retard</span>
            </>
          )}
          {undated > 0 && ` · ${undated} sans date`}
          {compact && rows.length > shown.length && (
            <>
              {' · '}
              <Link className="tl__more" to={`${base}/timeline`}>
                {rows.length - shown.length} de plus dans la timeline complète
              </Link>
            </>
          )}
        </p>
      </div>

      <div className="tl__scroll">
        <div className="tl__frame">
          {/* En-tête : mois, et lundis en vue « mois ». */}
          <div className="tl__header">
            <div className="tl__corner">Projet</div>
            <div className="tl__scale">
              {w.months.map((m) => (
                <span key={m.from} className="tl__month" style={{ left: `${w.edge(m.from)}%` }}>
                  {m.label}
                </span>
              ))}
              {zoom === 'month' &&
                mondays(w)
                  .filter((d) => !todayVisible || Math.abs(w.edge(d) - w.percent(today)) > 11)
                  .map((d) => (
                    <span key={d} className="tl__week" style={{ left: `${w.edge(d)}%` }}>
                      lun. {Number(d.slice(8))}
                    </span>
                  ))}
              {todayVisible && (
                <span className="tl__today-label" style={{ left: `${w.percent(today)}%` }}>
                  Aujourd’hui
                </span>
              )}
            </div>
          </div>

          <div className="tl__body">
            {/* Repères : limites de mois, semaines, week-ends, ligne d'aujourd'hui. */}
            <div className="tl__grid" aria-hidden="true">
              {w.months.map((m) => (
                <span
                  key={m.from}
                  className="tl__line tl__line--month"
                  style={{ left: `${w.edge(m.from)}%` }}
                />
              ))}
              {zoom === 'month' &&
                weekends(w).map((d) => (
                  <span
                    key={d}
                    className="tl__weekend"
                    style={{ left: `${w.edge(d)}%`, width: `${100 / w.totalDays}%` }}
                  />
                ))}
              {zoom === 'month' &&
                mondays(w).map((d) => (
                  <span key={d} className="tl__line" style={{ left: `${w.edge(d)}%` }} />
                ))}
              {todayVisible && (
                <span className="tl__today" style={{ left: `${w.percent(today)}%` }} />
              )}
            </div>

            {groups.length === 0 && (
              <p className="tl__empty">
                Aucun projet daté sur cette période. Utilisez les flèches ou changez de zoom.
              </p>
            )}

            {groups.map((group) => (
              <div key={group.id} className="tl__group">
                <div className="tl__group-head">
                  <span className="swatch" style={{ background: group.color }} aria-hidden="true" />
                  {group.name}
                  <span className="tl__group-count">{group.rows.length}</span>
                </div>
                {group.rows.map((row) => {
                  const { project: p, span } = row
                  const status = PROJECT_STATUS[p.status]
                  const left = clamp(w.edge(span.from))
                  const right = clamp(w.edge(addDays(span.to, 1)))
                  const width = right - left
                  const color = TONE_COLOR[status.tone]
                  const dueLate =
                    !isClosedProject(p.status) && p.due_date !== null && p.due_date < today
                  const i = index++
                  const showDue =
                    span.kind !== 'due' &&
                    p.due_date !== null &&
                    p.due_date >= w.start &&
                    p.due_date < w.end
                  // Échéance seule : une pastille centrée sur le jour, qui porte sa date.
                  const dueOnly = span.kind === 'due'
                  const style = {
                    left: dueOnly ? `${w.percent(span.from)}%` : `${left}%`,
                    width: dueOnly ? undefined : `max(${width}%, 12px)`,
                    '--bar': color,
                    '--i': i,
                  } as CSSProperties
                  const textInside = dueOnly || width > 9
                  return (
                    <div
                      key={p.id}
                      className={active === p.id ? 'tl__row tl__row--active' : 'tl__row'}
                      onMouseEnter={() => setActive(p.id)}
                      onMouseLeave={() => setActive(null)}
                    >
                      <div className="tl__label">
                        <Link className="tl__title" to={`${base}/projets/${p.id}`}>
                          {p.title}
                        </Link>
                        <span className="tl__meta">
                          {p.owner.name ? (
                            <span className="tl__avatar" title={p.owner.name}>
                              {initials(p.owner.name)}
                            </span>
                          ) : (
                            <span className="tl__avatar tl__avatar--none" title="Non attribué">
                              ?
                            </span>
                          )}
                          <span className={`tl__status tl__status--${status.tone}`}>
                            {status.label}
                          </span>
                        </span>
                      </div>
                      <div className="tl__lane">
                        <Link
                          to={`${base}/projets/${p.id}`}
                          className={`tl__bar tl__bar--${span.kind}`}
                          style={style}
                          aria-describedby={active === p.id ? `tip-${p.id}` : undefined}
                          aria-label={`${p.title}, ${status.label}, ${spanText(span)}`}
                          onFocus={() => setActive(p.id)}
                          onBlur={() => setActive(null)}
                        >
                          {textInside && (
                            <span className="tl__bar-text">
                              {span.kind === 'window'
                                ? `Période · ${spanText(span)}`
                                : dueOnly
                                  ? `${dueLate ? 'Dépassée · ' : 'Échéance · '}${spanText(span)}`
                                  : spanText(span)}
                            </span>
                          )}
                        </Link>
                        {!textInside && (
                          <span
                            className="tl__bar-outside"
                            style={{ left: `calc(${right}% + 8px)` }}
                            aria-hidden="true"
                          >
                            {spanText(span)}
                          </span>
                        )}
                        {showDue && (
                          <span
                            className={dueLate ? 'tl__due tl__due--late' : 'tl__due'}
                            style={{ left: `${w.percent(p.due_date!)}%` }}
                            title={`Échéance ${formatDay(p.due_date)}${dueLate ? ' (dépassée)' : ''}`}
                          />
                        )}
                        {row.tasks
                          .filter((t) => t.due_date && t.due_date >= w.start && t.due_date < w.end)
                          .map((t) => (
                            <span
                              key={t.id}
                              className={t.late ? 'tl__task tl__task--late' : 'tl__task'}
                              style={{ left: `${w.percent(t.due_date!)}%` }}
                              title={`Tâche : ${t.title} · ${formatDay(t.due_date)}${t.late ? ' (en retard)' : ''}`}
                            />
                          ))}
                        {active === p.id && (
                          <div
                            className="tl__tip-anchor"
                            style={{ left: `${Math.min(left, 62)}%` }}
                          >
                            <Tooltip row={row} today={today} />
                          </div>
                        )}
                      </div>
                    </div>
                  )
                })}
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="tl__legend" aria-label="Légende">
        {(['info', 'violet', 'warn', 'danger', 'ok', 'neutral'] as Tone[]).map((tone) => (
          <span key={tone} className="tl__legend-item">
            <span className="tl__legend-dot" style={{ background: TONE_COLOR[tone] }} />
            {
              {
                info: 'En cours',
                violet: 'En préparation',
                warn: 'À valider',
                danger: 'Bloqué',
                ok: 'Terminé',
                neutral: 'À cadrer / suspendu',
              }[tone]
            }
          </span>
        ))}
        <span className="tl__legend-item">
          <span className="tl__legend-window" /> Période à préciser
        </span>
        <span className="tl__legend-item">
          <span className="tl__due tl__due--legend" /> Échéance
        </span>
        <span className="tl__legend-item">
          <span className="tl__task tl__task--legend" /> Tâche (rouge : en retard)
        </span>
      </div>
    </div>
  )
}
