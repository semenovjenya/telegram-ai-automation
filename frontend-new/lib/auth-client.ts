'use client'

const LEGACY_AUTH_KEYS = ['token', 'isAuthenticated', 'savedPassword'] as const

export function clearLegacyAuthStorage(): void {
  for (const key of LEGACY_AUTH_KEYS) {
    localStorage.removeItem(key)
    sessionStorage.removeItem(key)
  }
}
