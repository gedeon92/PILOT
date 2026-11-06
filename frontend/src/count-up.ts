import { useEffect, useState } from 'react'

/** Fait défiler un nombre de 0 jusqu'à sa valeur (environ 0,7 s). Sans animation si
 * l'utilisateur a demandé de réduire les animations. */
export function useCountUp(value: number, duration = 700): number {
  const [shown, setShown] = useState(value)
  useEffect(() => {
    const reduce =
      typeof window.matchMedia === 'function' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches
    if (reduce || value === 0 || typeof requestAnimationFrame !== 'function') {
      setShown(value)
      return
    }
    let frame = 0
    const start = performance.now()
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / duration)
      setShown(Math.round(value * (1 - (1 - t) ** 3)))
      if (t < 1) frame = requestAnimationFrame(tick)
    }
    setShown(0)
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [value, duration])
  return shown
}
