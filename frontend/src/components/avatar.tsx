/** Avatar coloré : chaque personne garde toujours la même couleur (calculée à partir de son
 * nom), ce qui aide à la reconnaître d'un écran à l'autre. Décoratif : le nom est écrit à côté. */

const PALETTE = [
  { bg: 'rgb(255 122 26 / 0.18)', fg: '#ffb27a', fgLight: '#c2410c' }, // orange
  { bg: 'rgb(56 189 248 / 0.18)', fg: '#8fdcff', fgLight: '#0369a1' }, // bleu
  { bg: 'rgb(139 92 246 / 0.22)', fg: '#c9b6ff', fgLight: '#6d28d9' }, // violet
  { bg: 'rgb(34 197 94 / 0.18)', fg: '#86efac', fgLight: '#15803d' }, // vert
  { bg: 'rgb(34 211 238 / 0.18)', fg: '#7ff0ff', fgLight: '#0e7490' }, // turquoise
  { bg: 'rgb(255 61 129 / 0.2)', fg: '#ffa3c4', fgLight: '#be185d' }, // rose
  { bg: 'rgb(234 179 8 / 0.18)', fg: '#fde68a', fgLight: '#a16207' }, // ambre
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
      style={
        {
          background: color.bg,
          '--avatar-fg': color.fg,
          '--avatar-fg-light': color.fgLight,
        } as React.CSSProperties
      }
      title={title}
      aria-hidden="true"
    >
      {initials(name)}
    </span>
  )
}
