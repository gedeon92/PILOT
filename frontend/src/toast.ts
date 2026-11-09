import { useSyncExternalStore } from 'react'

/** Confirmations animées (« ✓ Tâche terminée »…) : l'application répond visiblement à chaque
 * action réussie. Une action déclare son message dans `meta.success` (voir query-client.ts). */

export type Toast = { id: number; text: string }

let toasts: Toast[] = []
let next = 1
const listeners = new Set<() => void>()
const emit = () => listeners.forEach((listener) => listener())

export function toast(text: string, duration = 2600) {
  const id = next++
  // Une seule confirmation identique à la fois (deux clics rapides n'en empilent pas deux).
  toasts = [...toasts.filter((t) => t.text !== text), { id, text }].slice(-3)
  emit()
  setTimeout(() => {
    toasts = toasts.filter((t) => t.id !== id)
    emit()
  }, duration)
}

export function useToasts(): Toast[] {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener)
      return () => listeners.delete(listener)
    },
    () => toasts,
  )
}
