/** Couleurs proposées pour les portefeuilles (valeurs acceptées par l'API). */
export const COLORS: { value: string; label: string; hex: string }[] = [
  { value: 'orange', label: 'Orange', hex: '#F26A1B' },
  { value: 'blue', label: 'Bleu', hex: '#2563EB' },
  { value: 'violet', label: 'Violet', hex: '#7C3AED' },
  { value: 'green', label: 'Vert', hex: '#16A34A' },
  { value: 'teal', label: 'Turquoise', hex: '#0D9488' },
  { value: 'pink', label: 'Rose', hex: '#DB2777' },
  { value: 'gray', label: 'Gris', hex: '#71717A' },
]

export function colorHex(value: string | undefined): string | undefined {
  return COLORS.find((c) => c.value === value)?.hex
}

/** Emojis proposés pour repérer un portefeuille (CDC §13) : un repère en plus du nom. */
export const PORTFOLIO_EMOJIS: { value: string; label: string }[] = [
  { value: '🎪', label: 'Événement' },
  { value: '🏢', label: 'Entreprise' },
  { value: '📈', label: 'Croissance' },
  { value: '🚀', label: 'Lancement' },
  { value: '🎯', label: 'Objectif' },
  { value: '📣', label: 'Communication' },
  { value: '🤝', label: 'Partenariat' },
  { value: '💡', label: 'Idée' },
  { value: '🌍', label: 'International' },
  { value: '🛠️', label: 'Technique' },
  { value: '📦', label: 'Produit' },
  { value: '🎓', label: 'Formation' },
  { value: '💼', label: 'Affaires' },
  { value: '🌱', label: 'Développement durable' },
  { value: '🏗️', label: 'Construction' },
  { value: '⭐', label: 'Prioritaire' },
]
