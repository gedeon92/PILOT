/** Avatar coloré : chaque personne garde toujours la même couleur (calculée à partir de son
 * nom), ce qui aide à la reconnaître d'un écran à l'autre. Décoratif : le nom est écrit à côté. */

const PALETTE = [
  { bg: '#ffedd5', fg: '#c2410c' }, // orange
  { bg: '#dbeafe', fg: '#1d4ed8' }, // bleu
  { bg: '#ede9fe', fg: '#6d28d9' }, // violet
  { bg: '#dcfce7', fg: '#15803d' }, // vert
  { bg: '#ccfbf1', fg: '#0f766e' }, // turquoise
  { bg: '#fce7f3', fg: '#be185d' }, // rose
  { bg: '#fef3c7', fg: '#b45309' }, // ambre
]

export function initials(name: string) {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase())
    .join('')
}

export function personColor(name: string) {
  let hash = 0
  for (const char of name.toLowerCase()) hash = (hash * 31 + char.charCodeAt(0)) >>> 0
  return PALETTE[hash % PALETTE.length]
}

export function Avatar({
  name,
  size = 'medium',
  title,
}: {
  name: string
  size?: 'tiny' | 'small' | 'medium'
  title?: string
}) {
  const color = personColor(name)
  return (
    <span
      className={`avatar avatar--${size}`}
      style={{ background: color.bg, color: color.fg }}
      title={title}
      aria-hidden="true"
    >
      {initials(name)}
    </span>
  )
}
