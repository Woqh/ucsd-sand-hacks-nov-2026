import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, tzOffsetMin } from '../api'
import { clearToken, setToken } from '../auth'
import { Banner, Button, Card, CardTitle } from '../components/ui'
import { usePoll, useToken } from '../hooks'
import type { Health, PairCreateResponse, Status } from '../types'

export default function Pair() {
  const token = useToken()
  const [code, setCode] = useState<{ value: string; expiresAt: number } | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [now, setNow] = useState(() => Date.now())

  const status = usePoll(async () => (token ? api<Status>('/status') : null), 2500, [token])
  const health = usePoll(() => api<Health>('/health', { auth: false }), 0)
  const paired = !!status.data?.paired

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [])

  async function createDashboard() {
    setBusy(true)
    setError(null)
    try {
      const r = await api<PairCreateResponse>('/pair/create', { method: 'POST', auth: false })
      if (r.dashboardToken) setToken(r.dashboardToken)
      setCode({ value: r.pairingCode, expiresAt: r.expiresAt })
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  async function newCode() {
    setBusy(true)
    setError(null)
    try {
      const r = await api<PairCreateResponse>('/pair/create', { method: 'POST' })
      setCode({ value: r.pairingCode, expiresAt: r.expiresAt })
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  async function loadDemo() {
    setBusy(true)
    setError(null)
    try {
      if (token) {
        await api('/dev/seed', { method: 'POST', body: { days: 42, tzOffsetMin: tzOffsetMin() } })
      } else {
        const r = await api<{ dashboardToken: string }>('/dev/seed', { method: 'POST', auth: false, body: { days: 42, tzOffsetMin: tzOffsetMin() } })
        setToken(r.dashboardToken)
      }
      status.refresh()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const secondsLeft = code ? Math.max(0, Math.round((code.expiresAt - now) / 1000)) : 0

  return (
    <div className="mx-auto max-w-xl space-y-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-ink">Pair your phone</h1>
        <p className="mt-1 text-ink-2">
          Mount your iPhone on the side of your chair so it sees your profile, then connect it to this dashboard. Only numbers
          leave the phone, never video or photos.
        </p>
      </div>

      {error && <Banner tone="error">{error}</Banner>}

      {!token && (
        <Card>
          <CardTitle>Get started</CardTitle>
          <p className="mb-4 text-sm text-ink-2">No account needed. This browser gets its own private dashboard and a short code to pair your phone.</p>
          <Button onClick={createDashboard} disabled={busy}>
            Create my dashboard
          </Button>
        </Card>
      )}

      {token && paired && (
        <Card>
          <div className="flex items-center gap-3">
            <span className="grid h-10 w-10 place-items-center rounded-full bg-good/15 text-good-ink" aria-hidden>
              ✓
            </span>
            <div>
              <div className="font-semibold text-ink">Phone connected</div>
              <div className="text-sm text-ink-2">
                {status.data?.device.online ? 'Sending posture data now.' : 'Waiting for the app to start monitoring.'}
              </div>
            </div>
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            <Link to="/" className="inline-flex min-h-11 items-center rounded-xl bg-ink px-4 text-sm font-medium text-surface">
              Go to live status
            </Link>
            <Button variant="secondary" onClick={newCode} disabled={busy}>
              Pair a different phone
            </Button>
          </div>
        </Card>
      )}

      {token && !paired && (
        <Card>
          <CardTitle>Enter this code in the Sitwise app</CardTitle>
          {code && secondsLeft > 0 ? (
            <>
              <div className="my-4 text-center font-mono text-5xl font-semibold tracking-[0.3em] text-ink" aria-label={`Pairing code ${code.value.split('').join(' ')}`}>
                {code.value}
              </div>
              <p className="text-center text-sm text-ink-2">
                Expires in {Math.floor(secondsLeft / 60)}:{String(secondsLeft % 60).padStart(2, '0')}. This page updates when the phone connects.
              </p>
            </>
          ) : (
            <p className="mb-4 text-sm text-ink-2">{code ? 'That code expired.' : 'Generate a code, then enter it on your phone.'}</p>
          )}
          <div className="mt-4">
            <Button onClick={newCode} disabled={busy} variant={code && secondsLeft > 0 ? 'secondary' : 'primary'}>
              {code ? 'New code' : 'Show pairing code'}
            </Button>
          </div>
        </Card>
      )}

      {health.data?.devRoutes && (
        <Card>
          <CardTitle hint={`dev · ${health.data.store} store`}>No phone handy?</CardTitle>
          <p className="mb-3 text-sm text-ink-2">
            Load six weeks of realistic sample data to explore the dashboard, or run <code className="rounded bg-line/60 px-1">python scripts/simulate.py</code> to
            act as the phone.
          </p>
          <Button variant="secondary" onClick={loadDemo} disabled={busy}>
            Load demo data
          </Button>
        </Card>
      )}

      {token && (
        <div className="text-center">
          <Button variant="ghost" onClick={clearToken}>
            Forget this browser
          </Button>
        </div>
      )}
    </div>
  )
}
