import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError } from './api'
import { getToken, onAuthChange } from './auth'

export function useToken(): string | null {
  const [token, setTok] = useState<string | null>(getToken)
  useEffect(() => onAuthChange(() => setTok(getToken())), [])
  return token
}

export interface Polled<T> {
  data: T | null
  error: ApiError | null
  loading: boolean
  refresh: () => void
}

/** Fetch now and then every `ms`. Keeps the previous data while refetching (no flash), pauses
 *  while the tab is hidden, and re-runs when `deps` change. */
export function usePoll<T>(fn: () => Promise<T>, ms: number, deps: unknown[] = []): Polled<T> {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [loading, setLoading] = useState(true)
  const fnRef = useRef(fn)
  fnRef.current = fn
  const [tick, setTick] = useState(0)

  useEffect(() => {
    let alive = true
    let timer: ReturnType<typeof setTimeout> | undefined
    const run = async () => {
      if (!document.hidden) {
        try {
          const d = await fnRef.current()
          if (alive) {
            setData(d)
            setError(null)
          }
        } catch (e) {
          if (alive) setError(e instanceof ApiError ? e : new ApiError(0, 'error', String(e)))
        } finally {
          if (alive) setLoading(false)
        }
      }
      if (alive && ms > 0) timer = setTimeout(run, ms)
    }
    setLoading(true)
    run()
    return () => {
      alive = false
      if (timer) clearTimeout(timer)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ms, tick, ...deps])

  const refresh = useCallback(() => setTick((t) => t + 1), [])
  return { data, error, loading, refresh }
}
