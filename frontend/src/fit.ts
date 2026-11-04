import { useEffect, useState, type RefObject } from 'react'

/** Nombre de lignes qui tiennent dans la hauteur de l'élément, recalculé quand il change de taille.
 * `reserved` : hauteur occupée par l'en-tête, la barre d'outils et la légende. */
export function useFitRows(
  ref: RefObject<HTMLElement | null>,
  { rowHeight, reserved, fallback }: { rowHeight: number; reserved: number; fallback: number },
) {
  const [rows, setRows] = useState(fallback)
  useEffect(() => {
    const element = ref.current
    if (!element || typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(([entry]) => {
      const height = entry.contentRect.height
      // Bloc qui n'est pas contraint en hauteur (téléphone, petite fenêtre) : valeur par défaut.
      if (height <= reserved) return setRows(fallback)
      setRows(Math.max(3, Math.floor((height - reserved) / rowHeight)))
    })
    observer.observe(element)
    return () => observer.disconnect()
  }, [ref, rowHeight, reserved, fallback])
  return rows
}
