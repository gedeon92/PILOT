import { useSyncExternalStore } from 'react'

/** Deux modes d'affichage : sombre (par défaut) et clair. Le choix est gardé sur l'appareil. */
export type Theme = 'dark' | 'light'

const KEY = 'pilot-theme'
const PAGE = { dark: '#05060b', light: '#f6f7fb' }
const listeners = new Set<() => void>()

export function getTheme(): Theme {
  return document.documentElement.dataset.theme === 'light' ? 'light' : 'dark'
}

export function applyTheme(theme: Theme) {
  document.documentElement.dataset.theme = theme
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', PAGE[theme])
  document.querySelector('meta[name="color-scheme"]')?.setAttribute('content', theme)
}

export function setTheme(theme: Theme) {
  applyTheme(theme)
  try {
    localStorage.setItem(KEY, theme)
  } catch {
    // Stockage indisponible (navigation privée) : le choix vaut pour cette visite.
  }
  listeners.forEach((listener) => listener())
}

function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function useTheme(): [Theme, (theme: Theme) => void] {
  return [useSyncExternalStore(subscribe, getTheme), setTheme]
}
