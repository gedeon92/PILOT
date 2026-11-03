/** Limite de la phase de test, identique à celle de l'API (max_upload_mb). */
export const MAX_UPLOAD_BYTES = 4 * 1024 * 1024
export const MAX_FILES_PER_UPLOAD = 3

export function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} o`
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} Ko`
  return `${(bytes / (1024 * 1024)).toFixed(1).replace('.', ',')} Mo`
}

/** Libellé court du format, affiché dans la pastille du fichier. */
export function extensionOf(filename: string): string {
  const ext = filename.includes('.') ? filename.split('.').pop() : ''
  return (ext || 'FICHIER').slice(0, 5).toUpperCase()
}
