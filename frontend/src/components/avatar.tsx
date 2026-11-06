/** Avatar coloré : chaque personne garde toujours la même couleur (calculée à partir de son
 * nom), ce qui aide à la reconnaître d'un écran à l'autre. Décoratif : le nom est écrit à côté. */

const PALETTE = [
  { bg: 'rgb(255 122 26 / 0.18)', fg: '#ffb27a' }, // orange
  { bg: 'rgb(56 189 248 / 0.18)', fg: '#8fdcff' }, // bleu
  { bg: 'rgb(139 92 246 / 0.22)', fg: '#c9b6ff' }, // violet
  { bg: 'rgb(34 197 94 / 0.18)', fg: '#86efac' }, // vert
  { bg: 'rgb(34 211 238 / 0.18)', fg: '#7ff0ff' }, // turquoise
  { bg: 'rgb(255 61 129 / 0.2)', fg: '#ffa3c4' }, // rose
  { bg: 'rgb(234 179 8 / 0.18)', fg: '#fde68a' }, // ambre
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
