import { useState } from 'react'
import { api } from '../api'
import { usePoll } from '../hooks'
import { Banner, Card, CardTitle } from './ui'

export default function DataConsent({ onChange }: { onChange?: (allowed: boolean) => void }) {
  const consent = usePoll(() => api<{ settings: { dataCollectionConsent: boolean } }>('/settings'), 0)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState<boolean | null>(null)
  const allowed = saved ?? consent.data?.settings.dataCollectionConsent ?? false

  async function change(value: boolean) {
    setBusy(true)
    setError(null)
    try {
      await api('/settings', { method: 'PUT', body: { dataCollectionConsent: value } })
      setSaved(value)
      onChange?.(value)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return <Card>
    <CardTitle>Consent to data collection</CardTitle>
    <p className="mb-3 text-sm text-ink-2">
      Sitwise collects and stores posture measurements, timestamps, session activity and alert history on its server to provide live status, analytics and coaching. Camera images are processed by your device or local model and are not stored with these readings.
    </p>
    <label className="flex min-h-11 items-start gap-3 text-sm text-ink">
      <input type="checkbox" className="mt-1 h-4 w-4" checked={allowed} disabled={busy || !consent.data}
        onChange={(e) => void change(e.target.checked)} />
      <span>I agree to collection and storage of my posture data for these features.</span>
    </label>
    <p className="mt-2 text-xs text-ink-2">Optional. Uncheck this here or in Settings to stop accepting new readings from all paired devices. Previously collected data remains stored. Sharing with Google's Gemini requires a separate agreement each time.</p>
    <p role="status" className="mt-2 text-xs text-ink-2">{busy ? 'Saving…' : allowed ? 'Data collection allowed.' : 'Data collection is off.'}</p>
    {(error || consent.error) && <Banner tone="error">{error || consent.error?.message}</Banner>}
  </Card>
}
