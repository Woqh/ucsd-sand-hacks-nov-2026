import { useEffect, useState, type FormEvent } from 'react'
import { api } from '../api'
import { Banner, Button, Card, CardTitle } from '../components/ui'
import { disableReceiverPush, enableReceiverPush, getPushState, type PushState } from '../push'

const TOKEN_KEY = 'sitwise.pushReceiverToken'

export default function Receive() {
  const [token, setToken] = useState<string | null>(null)
  const [code, setCode] = useState('')
  const [pushState, setPushState] = useState<PushState | 'loading' | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  useEffect(() => {
    try {
      const saved = localStorage.getItem(TOKEN_KEY)
      setToken(saved)
      if (saved) getPushState().then(setPushState, () => setPushState('unsupported'))
    } catch {
      setError('This browser blocked local storage. Allow site data to keep this phone connected.')
    }
  }, [])

  async function pair(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    setMessage(null)
    try {
      const result = await api<{ receiverToken: string }>('/push/web/receiver/claim', {
        method: 'POST',
        auth: false,
        body: { code: code.replace(/[\s-]/g, '').toUpperCase() },
      })
      setToken(result.receiverToken)
      setCode('')
      try {
        localStorage.setItem(TOKEN_KEY, result.receiverToken)
      } catch {
        setError('This browser blocked local storage. Keep this page open or allow site data before leaving.')
      }
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  async function enable() {
    if (!token) return
    setBusy(true)
    setError(null)
    setMessage(null)
    try {
      await enableReceiverPush(token)
      setPushState('on')
      setMessage('This phone is connected and will receive posture alerts.')
    } catch (e) {
      setError((e as Error).message)
      getPushState().then(setPushState, () => setPushState('unsupported'))
    } finally {
      setBusy(false)
    }
  }

  async function disconnect() {
    if (!token) return
    setBusy(true)
    setError(null)
    setMessage(null)
    try {
      await disableReceiverPush(token)
      localStorage.removeItem(TOKEN_KEY)
      setToken(null)
      setPushState(null)
      setMessage('This phone is disconnected.')
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="mx-auto max-w-xl space-y-4 p-4 sm:p-8">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight text-ink">Phone alert receiver</h1>
        <p className="mt-1 text-sm text-ink-2">
          Connect this iPhone to receive posture alerts from your Sitwise sensor over Wi-Fi or the internet.
          This phone won’t replace or control the sensor.
        </p>
      </header>

      {error && <Banner tone="error">{error}</Banner>}
      {message && <Banner tone="info">{message}</Banner>}

      {!token ? (
        <Card>
          <CardTitle>Connect to your Sitwise dashboard</CardTitle>
          <ol className="mb-4 list-decimal space-y-1 pl-5 text-sm text-ink-2">
            <li>On your dashboard, open Settings and generate a phone setup code.</li>
            <li>Enter that code here. It expires after 10 minutes and can only be used once.</li>
          </ol>
          <form onSubmit={pair} className="flex flex-wrap gap-2">
            <label className="sr-only" htmlFor="receiver-code">Phone setup code</label>
            <input
              id="receiver-code"
              autoComplete="one-time-code"
              value={code}
              onChange={(e) => setCode(e.target.value.toUpperCase())}
              placeholder="8-character code"
              maxLength={10}
              className="min-h-11 min-w-48 flex-1 rounded-xl border border-axis bg-surface px-3 font-mono tracking-widest text-ink"
            />
            <Button type="submit" disabled={busy || code.replace(/[\s-]/g, '').length !== 8}>
              Connect phone
            </Button>
          </form>
        </Card>
      ) : (
        <Card>
          <CardTitle hint={pushState === 'on' ? 'connected' : undefined}>Enable posture alerts</CardTitle>
          <p className="mb-4 text-sm text-ink-2">
            Allow notifications when prompted. On iPhone, web push requires iOS 16.4 or later and this page opened
            from its Home Screen icon (Safari Share → Add to Home Screen).
          </p>
          {pushState === 'unsupported' && (
            <p className="mb-3 text-sm text-crit">Web push isn’t available in this browser. Open the installed Sitwise Home Screen app on a supported iPhone.</p>
          )}
          {pushState === 'denied' && (
            <p className="mb-3 text-sm text-crit">Notifications are blocked. Allow them for Sitwise in iPhone Settings → Notifications.</p>
          )}
          {pushState === 'on' && (
            <p className="mb-3 text-sm text-ink-2">Notifications are enabled. iPhone notification settings control their sound and vibration.</p>
          )}
          <div className="flex flex-wrap gap-2">
            <Button onClick={enable} disabled={busy || pushState === 'loading'}>
              {pushState === 'on' ? 'Refresh connection' : 'Enable alerts on this phone'}
            </Button>
            <Button variant="secondary" onClick={disconnect} disabled={busy}>
              Disconnect this phone
            </Button>
          </div>
        </Card>
      )}
    </main>
  )
}
