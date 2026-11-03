export function detectedTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
  } catch {
    return 'UTC'
  }
}

/** Tous les fuseaux connus du navigateur, avec `current` en tête. */
export function allTimezones(current: string): string[] {
  const zones =
    typeof Intl.supportedValuesOf === 'function' ? Intl.supportedValuesOf('timeZone') : []
  return Array.from(new Set([current, 'UTC', ...zones]))
}
