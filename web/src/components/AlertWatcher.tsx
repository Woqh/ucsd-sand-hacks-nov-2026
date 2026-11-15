import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { detectAlert, messageFor, type Watched } from '../alertRules'
import { ALERTS_EVENT, canAskForAlerts, disableLocalAlerts, enableLocalAlerts, localAlertState, showAlert, type LocalAlertState } from '../alerts'
import { getPushState } from '../push'
import type { Settings, Status } from '../types'
import { Button, StateIcon } from './ui'

const POLL_MS = 3000
const SETTINGS_EVERY = 10 // re-read tone and channel settings every this many polls
const TOAST_MS = 12_000

/** The state of "notify me in this tab", kept in step across components (and tabs) via an event. */
export function useLocalAlerts() {
  const [state, setState] = useState<LocalAlertState>(localAlertState)
  const [canAsk, setCanAsk] = useState(canAskForAlerts)
  useEffect(() => {
    const sync = () => {
      setState(localAlertState())
      setCanAsk(canAskForAlerts())
    }
    window.addEventListener(ALERTS_EVENT, sync)
    window.addEventListener('storage', sync)
    return () => {
      window.removeEventListener(ALERTS_EVENT, sync)
      window.removeEventListener('storage', sync)
    }
  }, [])
  const enable = useCallback(() => enableLocalAlerts(), [])
  const disable = useCallback(() => disableLocalAlerts(), [])
  return { state, canAsk, enable, disable }
}

/** Mounted once for a signed-in dashboard. While "notify me" is on it watches the status and, the moment the
 *  server sends a slouch nudge, shows a browser notification and an in-page banner. */
export function AlertWatcher() {
  const { state } = useLocalAlerts()
  const [toast, setToast] = useState<{ id: number; title: string; body: string } | null>(null)

  useEffect(() => {
    if (state !== 'on') return
    let alive = true
    let busy = false
    let polls = 0
    let prev: Watched | null = null
    let tone: Settings['nudgeTone'] | undefined
    let desktopOn = true

    const run = async () => {
      if (busy) return
      busy = true
      try {
        if (polls++ % SETTINGS_EVERY === 0) {
          const { settings } = await api<{ settings: Settings }>('/settings')
          tone = settings.nudgeTone
          desktopOn = settings.alertChannels.desktop // the "This computer" switch in Settings governs this too
        }
        const s = await api<Status>('/status')
        const cur: Watched = { state: s.state, alertsSent: s.alertsSent }
        const level = detectAlert(prev, cur)
        prev = cur
        if (level && desktopOn && alive) {
          const m = messageFor(tone, level)
          setToast({ id: Date.now(), ...m })
          // If this browser already gets the same nudge as a Web Push, let that one show: no double buzz.
          const pushOn = await getPushState().then((p) => p === 'on', () => false)
          if (!pushOn) await showAlert(m.title, m.body)
        }
      } catch {
        /* offline or signed out: try again next time */
      } finally {
        busy = false
      }
    }
    void run()
    const id = setInterval(run, POLL_MS)
    return () => {
      alive = false
      clearInterval(id)
    }
  }, [state])

  const toastId = toast?.id
  useEffect(() => {
    if (toastId == null) return
    const t = setTimeout(() => setToast(null), TOAST_MS)
    return () => clearTimeout(t)
  }, [toastId])

  if (!toast) return null
  return (
    <div role="alert" className="fixed right-3 top-[4.5rem] z-30 w-[min(24rem,calc(100vw-1.5rem))] rounded-2xl border border-crit/40 bg-surface p-4 shadow-lg print:hidden">
      <div className="flex items-start gap-3">
        <span className="mt-0.5 text-crit">
          <StateIcon state="SLOUCHING" className="h-6 w-6" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="font-semibold text-ink">{toast.title}</div>
          <div className="mt-0.5 text-sm text-ink-2">{toast.body}</div>
        </div>
        <button type="button" onClick={() => setToast(null)} aria-label="Dismiss" className="-m-1 rounded-lg p-2 text-ink-2 hover:bg-line/50">
          ✕
        </button>
      </div>
    </div>
  )
}

/** A one-line prompt for the Live page, shown only while the browser has not been asked yet. */
export function EnableAlertsBanner() {
  const { canAsk, enable } = useLocalAlerts()
  const [hidden, setHidden] = useState(() => {
    try {
      return sessionStorage.getItem('sitwise.alertsPromptHidden') === '1'
    } catch {
      return false
    }
  })
  const [error, setError] = useState<string | null>(null)
  const asked = useRef(false)

  if (!canAsk || hidden) return null
  const dismiss = () => {
    setHidden(true)
    try {
      sessionStorage.setItem('sitwise.alertsPromptHidden', '1')
    } catch {
      /* ignore */
    }
  }
  return (
    <div role="status" className="rounded-xl bg-accent/10 px-4 py-3 text-sm text-ink">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <span>Get a browser notification the moment you slouch, while this dashboard is open.</span>
        <span className="flex gap-2">
          <Button
            variant="secondary"
            onClick={async () => {
              if (asked.current) return
              asked.current = true
              try {
                await enable()
              } catch (e) {
                setError((e as Error).message)
              } finally {
                asked.current = false
              }
            }}
          >
            Turn on alerts
          </Button>
          <Button variant="ghost" onClick={dismiss}>
            Not now
          </Button>
        </span>
      </div>
      {error && <div className="mt-2 text-crit">{error}</div>}
    </div>
  )
}
