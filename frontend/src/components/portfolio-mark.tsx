import { colorHex } from '../colors'

/** Repère d'un portefeuille : son emoji s'il en a un, sinon sa pastille de couleur.
 * Toujours décoratif : le nom du portefeuille est affiché à côté. */
export function PortfolioMark({ color, emoji }: { color?: string; emoji?: string | null }) {
  if (emoji) {
    return (
      <span className="portfolio-emoji" aria-hidden="true">
        {emoji}
      </span>
    )
  }
  const hex = colorHex(color)
  if (!hex) return null
  return <span className="swatch" style={{ background: hex }} aria-hidden="true" />
}
