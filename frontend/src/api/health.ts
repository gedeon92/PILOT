import type { components } from './schema'

export type Health = components['schemas']['Health']

const ATTEMPT_TIMEOUT_MS = 10_000
const RETRY_DELAY_MS = 3_000
// L'offre gratuite de Render met l'API en veille : le réveil peut prendre jusqu'à une minute.
const WAKE_UP_BUDGET_MS = 90_000

export async function fetchHealth(signal?: AbortSignal): Promise<Health> {
  const deadline = Date.now() + WAKE_UP_BUDGET_MS
  let lastError: unknown

  while (Date.now() < deadline) {
    try {
      const response = await fetch('/api/health', {
        signal: signal
          ? AbortSignal.any([signal, AbortSignal.timeout(ATTEMPT_TIMEOUT_MS)])
          : AbortSignal.timeout(ATTEMPT_TIMEOUT_MS),
      })
      if (response.ok) {
        return (await response.json()) as Health
      }
      lastError = new Error(`HTTP ${response.status}`)
    } catch (error) {
      if (signal?.aborted) throw error
      lastError = error
    }
    await new Promise((resolve) => setTimeout(resolve, RETRY_DELAY_MS))
  }
  throw lastError ?? new Error('API injoignable')
}
