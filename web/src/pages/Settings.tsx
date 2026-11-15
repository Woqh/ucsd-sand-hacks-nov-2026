import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { clearToken } from '../auth'
import { Banner, Button, Card, CardTitle, Toggle } from '../components/ui'
import { formatDuration } from '../format'
import { usePoll } from '../hooks'
import { enableDesktopPush, getPushState, type PushState } from '../push'
import type { ChannelResult, Settings } from '../types'

type Patch = Partial<Omit<Settings, 'alertChannels' | 'quietHours'>> & {
  alertChannels?: Partial<Settings['alertChannels']>
  quietHours?: Partial<Settings['quietHours']>
}

export default function SettingsPage() {
  const loaded = usePoll(() => api<{ settings: Settings }>('/settings'), 0)
  const [s, setS] = useState<Settings | null>(null)
  const [save, setSave] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')
  const [error, setError] = useState<string | null>(null)
  const pending = useRef<Patch>({})
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)

  useEffect(() => {
    if (loaded.data && !s) setS(loaded.data.settings)
  }, [loaded.data, s])

  /** Apply instantly, then save (debounced) so dragging a slider doesn't spam the API. */
  function change(p: Patch) {
    setS((cur) =>
      cur && {
        ...cur,
        ...p,
        alertChannels: { ...cur.alertChannels, ...p.alertChannels },
        quietHours: { ...cur.quietHours, ...p.quietHours },
      },
    )
    pending.current = {
      ...pending.current,
      ...p,
      alertChannels: { ...pending.current.alertChannels, ...p.alertChannels },
      quietHours: { ...pending.current.quietHours, ...p.quietHours },
    }
    setSave('saving')
    clearTimeout(timer.current)
    timer.current = setTimeout(async () => {
      const body = pending.current
      pending.current = {}
      try {
        await api('/settings', { method: 'PUT', body })
        setSave('saved')
        setError(null)
      } catch (e) {
        setSave('error')
        setError((e as Error).message)
      }
    }, 500)
  }

  if (!s) return loaded.error ? <Banner tone="error">{loaded.error.message}</Banner> : <p className="text-ink-2">Loading…</p>

  return (
    <div className="mx-auto max-w-xl space-y-4">
      <div className="flex items-baseline justify-between">
        <h1 className="text-2xl font-semibold tracking-tight text-ink">Settings</h1>
        <span className="text-sm text-ink-2" aria-live="polite">
          {save === 'saving' ? 'Saving…' : save === 'saved' ? 'Saved' : ''}
        </span>
      </div>
      {error && <Banner tone="error">{error}</Banner>}

      <Card>
        <CardTitle>When to nudge me</CardTitle>
        <div className="space-y-6">
          <Slider
            label="Slouch threshold"
            help="How long you can be off your goal posture before you get a nudge."
            value={s.slouchThresholdSec}
            min={5}
            max={300}
            step={5}
            display={formatDuration(s.slouchThresholdSec)}
            onChange={(v) => change({ slouchThresholdSec: v })}
          />
          <Slider
            label="Sensitivity"
            help="Strict catches small slouches. Forgiving only reacts to bigger ones."
            value={s.sensitivity}
            min={0}
            max={1}
            step={0.05}
            display={s.sensitivity < 0.34 ? 'Forgiving' : s.sensitivity > 0.66 ? 'Strict' : 'Balanced'}
            onChange={(v) => change({ sensitivity: v })}
          />
          <Slider
            label="Cooldown between nudges"
            help="Minimum gap between alerts so Sitwise never nags."
            value={s.cooldownSec}
            min={15}
            max={900}
            step={15}
            display={formatDuration(s.cooldownSec)}
            onChange={(v) => change({ cooldownSec: v })}
          />
        </div>
      </Card>

      <Card>
        <CardTitle>How to nudge me</CardTitle>
        <div className="space-y-4">
          <Row title="iPhone" sub="Push notification: your phone vibrates" right={<Toggle label="iPhone alerts" checked={s.alertChannels.phone} onChange={(v) => change({ alertChannels: { phone: v } })} />} />
          <Row title="This computer" sub="Browser notification" right={<Toggle label="Desktop alerts" checked={s.alertChannels.desktop} onChange={(v) => change({ alertChannels: { desktop: v } })} />} />
          <DesktopPush />
          <TestButtons />
        </div>
      </Card>

      <Card>
        <CardTitle>Quiet hours</CardTitle>
        <Row title="Don't send alerts during quiet hours" sub="Posture is still tracked." right={<Toggle label="Quiet hours" checked={s.quietHours.enabled} onChange={(v) => change({ quietHours: { enabled: v } })} />} />
        {s.quietHours.enabled && (
          <div className="mt-4 flex flex-wrap items-center gap-3 text-sm text-ink-2">
            <label className="flex items-center gap-2">
              From
              <input type="time" value={s.quietHours.start} onChange={(e) => e.target.value && change({ quietHours: { start: e.target.value } })} className="min-h-11 rounded-lg border border-axis bg-surface px-3 text-ink" />
            </label>
            <label className="flex items-center gap-2">
              to
              <input type="time" value={s.quietHours.end} onChange={(e) => e.target.value && change({ quietHours: { end: e.target.value } })} className="min-h-11 rounded-lg border border-axis bg-surface px-3 text-ink" />
            </label>
          </div>
        )}
      </Card>

      <Card>
        <CardTitle>Goal posture</CardTitle>
        <p className="mb-3 text-sm text-ink-2">Change how you like to sit? Redo your goal posture any time.</p>
        <Link to="/calibration" className="inline-flex min-h-11 items-center rounded-xl border border-axis px-4 text-sm font-medium text-ink hover:bg-line/50">
          Recalibrate
        </Link>
      </Card>

      <div className="text-center">
        <Button variant="ghost" onClick={clearToken}>
          Forget this browser
        </Button>
      </div>
    </div>
  )
}

function Row({ title, sub, right }: { title: string; sub?: string; right: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <div>
        <div className="font-medium text-ink">{title}</div>
        {sub && <div className="text-sm text-ink-2">{sub}</div>}
      </div>
      {right}
    </div>
  )
}

function Slider({ label, help, value, min, max, step, display, onChange }: { label: string; help: string; value: number; min: number; max: number; step: number; display: string; onChange: (v: number) => void }) {
  return (
    <label className="block">
      <div className="flex items-baseline justify-between">
        <span className="font-medium text-ink">{label}</span>
        <span className="text-sm font-medium text-ink">{display}</span>
      </div>
      <input type="range" min={min} max={max} step={step} value={value} onChange={(e) => onChange(Number(e.target.value))} className="mt-2 h-8 w-full" />
      <span className="text-sm text-ink-2">{help}</span>
    </label>
  )
}

function DesktopPush() {
  const [state, setState] = useState<PushState | 'loading'>('loading')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<string | null>(null)
  useEffect(() => {
    getPushState().then(setState, () => setState('unsupported'))
  }, [])

  async function enable() {
    setBusy(true)
    setMsg(null)
    try {
      await enableDesktopPush()
      setState('on')
    } catch (e) {
      setMsg((e as Error).message)
      getPushState().then(setState, () => {})
    } finally {
      setBusy(false)
    }
  }

  if (state === 'loading') return null
  return (
    <div className="rounded-xl bg-line/40 p-3 text-sm">
      {state === 'on' && <span className="text-ink">Browser notifications are on for this device.</span>}
      {state === 'unsupported' && <span className="text-ink-2">This browser doesn't support web push. Try Chrome, Edge or Firefox.</span>}
      {state === 'denied' && <span className="text-ink-2">Notifications are blocked for this site. Allow them in your browser's site settings.</span>}
      {state === 'off' && (
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="text-ink-2">Browser notifications aren't enabled yet.</span>
          <Button variant="secondary" onClick={enable} disabled={busy}>
            Enable on this computer
          </Button>
        </div>
      )}
      {msg && <div className="mt-2 text-crit">{msg}</div>}
    </div>
  )
}

function TestButtons() {
  const [out, setOut] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function test(channel: 'phone' | 'desktop') {
    setBusy(true)
    try {
      const r = await api<{ result: ChannelResult }>('/push/test', { method: 'POST', body: { channel } })
      const x = r.result
      setOut(x.sent > 0 ? `Sent to ${x.sent} ${channel === 'phone' ? 'device' : 'browser'}${x.sent > 1 ? 's' : ''}.` : `Not sent: ${explain(x.skipped) ?? (x.failed ? 'the push service rejected it' : 'unknown')}.`)
    } catch (e) {
      setOut((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <div className="flex flex-wrap gap-2">
        <Button variant="secondary" onClick={() => test('desktop')} disabled={busy}>
          Test desktop alert
        </Button>
        <Button variant="secondary" onClick={() => test('phone')} disabled={busy}>
          Test iPhone alert
        </Button>
      </div>
      {out && (
        <p className="mt-2 text-sm text-ink-2" role="status">
          {out}
        </p>
      )}
    </div>
  )
}

const explain = (k: string | null) =>
  k && (({
    no_device_registered: 'no iPhone has registered for notifications yet',
    no_browser_subscribed: 'this browser has not subscribed (enable it above)',
    apns_not_configured: 'the server has no APNs key configured',
    vapid_not_configured: 'the server has no VAPID keys configured',
  } as Record<string, string>)[k] ?? k)
