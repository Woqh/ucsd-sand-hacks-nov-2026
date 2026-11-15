import type { Analysis } from '../types'

// The coaching profile lives ONLY in this browser (localStorage). The server never stores it, so it can't be
// read, backed up or leaked from there. Every access is wrapped: storage can throw or come back empty
// (private windows, blocked site data), and the app must still work without it.
const KEY = 'sitwise.profile.v1'

export interface StoredProfile {
  savedAt: number
  /** Where the analysis came from: our own rules on this device, or Gemini after an explicit opt-in. */
  source: 'on-device' | 'gemini'
  model?: string
  analysis: Analysis
}

export function loadProfile(): StoredProfile | null {
  try {
    const raw = localStorage.getItem(KEY)
    if (!raw) return null
    const p = JSON.parse(raw) as StoredProfile
    return p && p.analysis && typeof p.savedAt === 'number' ? p : null
  } catch {
    return null
  }
}

export function saveProfile(p: StoredProfile): boolean {
  try {
    localStorage.setItem(KEY, JSON.stringify(p))
    return true
  } catch {
    return false
  }
}

export function clearProfile(): void {
  try {
    localStorage.removeItem(KEY)
  } catch {
    /* ignore */
  }
}
