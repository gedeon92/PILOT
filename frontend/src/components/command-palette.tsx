import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react'
import { createPortal } from 'react-dom'
import { useNavigate } from 'react-router'
import { useProjects, useSpaceDocuments } from '../api/queries'
import { PROJECT_STATUS } from '../labels'

type Result = { id: string; group: string; title: string; detail?: string; to: string }

const PAGES = [
  { title: 'Vue d’ensemble', path: '' },
  { title: 'Point hebdo', path: '/point-hebdo' },
  { title: 'Projets', path: '/projets' },
  { title: 'Nouveau projet', path: '/projets/nouveau' },
  { title: 'Événements', path: '/evenements' },
  { title: 'Timeline', path: '/timeline' },
  { title: 'Documents', path: '/documents' },
  { title: 'Mises à jour', path: '/mises-a-jour' },
  { title: 'Alertes', path: '/alertes' },
  { title: 'Mon compte', path: '/compte' },
  { title: 'Accès et membres', path: '/membres' },
  { title: 'Paramètres et structure', path: '/parametres' },
]

/** Compare sans tenir compte des majuscules ni des accents. */
function normalize(text: string) {
  return text
    .normalize('NFD')
    .replace(/\p{Diacritic}/gu, '')
    .toLowerCase()
}

function isPaletteShortcut(e: { key: string; metaKey: boolean; ctrlKey: boolean }) {
  return (e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k'
}

function Palette({ spaceId, onClose }: { spaceId: string; onClose: () => void }) {
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const [index, setIndex] = useState(0)
  const input = useRef<HTMLInputElement>(null)
  const projects = useProjects(spaceId)
  const documents = useSpaceDocuments(spaceId, query.trim().length >= 2 ? query.trim() : '')
  const base = `/espaces/${spaceId}`

  useEffect(() => {
    input.current?.focus()
  }, [])

  const results = useMemo<Result[]>(() => {
    const q = normalize(query.trim())
    const found: Result[] = []
    for (const p of projects.data ?? []) {
      const haystack = normalize(
        [p.title, p.next_step, p.owner.name, p.entity?.name, p.portfolio.name]
          .filter(Boolean)
          .join(' '),
      )
      if (!q || haystack.includes(q)) {
        found.push({
          id: `p-${p.id}`,
          group: 'Projets',
          title: p.title,
          detail: `${PROJECT_STATUS[p.status].label} · ${p.portfolio.name}${p.owner.name ? ` · ${p.owner.name}` : ''}`,
          to: `${base}/projets/${p.id}`,
        })
      }
    }
    const projectResults = found.slice(0, q ? 8 : 5)
    const docResults: Result[] =
      q.length >= 2
        ? (documents.data?.items ?? []).slice(0, 5).map((d) => ({
            id: `d-${d.id}`,
            group: 'Documents',
            title: d.filename,
            detail: d.project_title,
            to: `${base}/projets/${d.project_id}`,
          }))
        : []
    const pageResults: Result[] = PAGES.filter(
      (page) => !q || normalize(page.title).includes(q),
    ).map((page) => ({
      id: `n-${page.path}`,
      group: 'Aller à',
      title: page.title,
      to: `${base}${page.path}`,
    }))
    return [...projectResults, ...docResults, ...pageResults]
  }, [query, projects.data, documents.data, base])

  const current = Math.min(index, Math.max(0, results.length - 1))

  function open(result: Result | undefined) {
    if (!result) return
    onClose()
    navigate(result.to)
  }

  function onKeyDown(e: KeyboardEvent) {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setIndex((i) => Math.min(i + 1, results.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setIndex((i) => Math.max(i - 1, 0))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      open(results[current])
    } else if (e.key === 'Escape') {
      e.preventDefault()
      onClose()
    }
  }

  let lastGroup = ''
  return (
    <div className="palette-backdrop" onMouseDown={onClose}>
      <div
        className="palette"
        role="dialog"
        aria-modal="true"
        aria-label="Recherche globale"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <input
          ref={input}
          className="palette__input"
          role="combobox"
          aria-expanded="true"
          aria-controls="palette-results"
          aria-activedescendant={results[current] ? `palette-${results[current].id}` : undefined}
          placeholder="Rechercher un projet, un document, une page…"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value)
            setIndex(0)
          }}
          onKeyDown={onKeyDown}
        />
        <ul className="palette__results" id="palette-results" role="listbox" aria-label="Résultats">
          {results.length === 0 && (
            <li className="palette__empty">Aucun résultat pour « {query} ».</li>
          )}
          {results.map((r, i) => {
            const heading = r.group !== lastGroup ? r.group : null
            lastGroup = r.group
            return (
              <li key={r.id} role="presentation">
                {heading && <div className="palette__group">{heading}</div>}
                <div
                  id={`palette-${r.id}`}
                  role="option"
                  aria-selected={i === current}
                  className={i === current ? 'palette__item palette__item--on' : 'palette__item'}
                  onMouseEnter={() => setIndex(i)}
                  onClick={() => open(r)}
                >
                  <span className="palette__title">{r.title}</span>
                  {r.detail && <span className="palette__detail">{r.detail}</span>}
                </div>
              </li>
            )
          })}
        </ul>
        <div className="palette__help" aria-hidden="true">
          <span>↑ ↓ pour choisir</span>
          <span>Entrée pour ouvrir</span>
          <span>Échap pour fermer</span>
        </div>
      </div>
    </div>
  )
}

/** Recherche globale : ⌘K (Mac) ou Ctrl+K (PC), ou le bouton « Rechercher » du menu. */
export function CommandPalette({
  spaceId,
  open,
  setOpen,
}: {
  spaceId: string
  open: boolean
  setOpen: (v: boolean) => void
}) {
  useEffect(() => {
    function onKey(e: globalThis.KeyboardEvent) {
      if (isPaletteShortcut(e)) {
        e.preventDefault()
        setOpen(!open)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, setOpen])

  if (!open) return null
  return createPortal(<Palette spaceId={spaceId} onClose={() => setOpen(false)} />, document.body)
}
