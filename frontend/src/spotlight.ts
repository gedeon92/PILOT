/** Lueur qui suit la souris sur les cartes (PILOT 2040). Un seul écouteur pour toute
 * l'application : la position est écrite dans les variables CSS --mx et --my de la carte
 * survolée. Rien n'est fait si l'utilisateur a demandé de réduire les animations. */
export function installSpotlight() {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
  if (!window.matchMedia('(pointer: fine)').matches) return
  let frame = 0
  window.addEventListener(
    'pointermove',
    (event) => {
      if (frame) return
      frame = requestAnimationFrame(() => {
        frame = 0
        const target = event.target as Element | null
        const card = target?.closest?.('.card-panel, .stat-card') as HTMLElement | null
        if (!card) return
        const box = card.getBoundingClientRect()
        card.style.setProperty('--mx', `${event.clientX - box.left}px`)
        card.style.setProperty('--my', `${event.clientY - box.top}px`)
      })
    },
    { passive: true },
  )
}
