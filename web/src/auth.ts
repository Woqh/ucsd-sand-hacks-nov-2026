// The dashboard token lives in localStorage. Every access is wrapped: storage can throw or come
// back empty (private windows, blocked site data), and the app must still render.
const KEY = 'sitwise.dashboardToken'
const EVENT = 'sitwise-auth'

export function getToken(): string | null {
  try {
    return localStorage.getItem(KEY)
  } catch {
    return null
  }
}

export function setToken(token: string): void {
  try {
    localStorage.setItem(KEY, token)
  } catch {
    /* storage blocked: the session just won't survive a reload */
  }
  window.dispatchEvent(new Event(EVENT))
}

export function clearToken(): void {
  try {
    localStorage.removeItem(KEY)
  } catch {
    /* ignore */
  }
  window.dispatchEvent(new Event(EVENT))
}

export function onAuthChange(fn: () => void): () => void {
  window.addEventListener(EVENT, fn)
  return () => window.removeEventListener(EVENT, fn)
}

/** Demo/dev convenience: `/?token=<dashboard token>` (printed by scripts/seed.py) signs in and
 *  is stripped from the address bar straight away. */
export function adoptTokenFromUrl(): void {
  try {
    const url = new URL(window.location.href)
    const t = url.searchParams.get('token')
    if (t) {
      localStorage.setItem(KEY, t)
      url.searchParams.delete('token')
      window.history.replaceState({}, '', url.pathname + url.search + url.hash)
    }
  } catch {
    /* ignore */
  }
}
