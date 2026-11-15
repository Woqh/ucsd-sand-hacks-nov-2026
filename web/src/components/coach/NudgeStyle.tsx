import { useEffect, useState } from 'react'
import { api } from '../../api'
import { messageFor } from '../../alertRules'
import { usePoll } from '../../hooks'
import type { Settings, Tone } from '../../types'
import { Banner, Button, Card, CardTitle, Segmented, Toggle } from '../ui'

// What each tone sounds like: the first-level nudge (the wording lives in alertRules.ts, mirroring the server).
const SAMPLE = (tone: Tone) => messageFor(tone, 1)

const DURATIONS = [25, 45, 90]

/** Nudge wording and focus mode. Self-contained (loads and saves its own settings) so it can sit on the
 *  Settings page and in Coach alike. Every change is a small partial PUT, so it can't clobber other settings. */
export default function NudgeStyleCard({ onChanged }: { onChanged?: () => void }) {
  const loaded = usePoll(() => api<{ settings: Settings }>('/settings'), 0)
  const [s, setS] = useState<Settings | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    if (loaded.data) setS(loaded.data.settings)
  }, [loaded.data])

  // tick once a second only while a focus session is running, so the countdown is live
  const running = !!s && s.focus.untilMs > now
  useEffect(() => {
    if (!running) return
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [running])

  async function put(body: Record<string, unknown>) {
    setErr(null)
    try {
      const r = await api<{ settings: Settings }>('/settings', { method: 'PUT', body })
      setS(r.settings)
      onChanged?.()
    } catch (e) {
      setErr((e as Error).message)
    }
  }

  async function focus(minutes: number) {
    setErr(null)
    try {
      const r = await api<{ settings: Settings }>('/focus', { method: 'POST', body: { minutes } })
      setS(r.settings)
      setNow(Date.now())
      onChanged?.()
    } catch (e) {
      setErr((e as Error).message)
    }
  }

  if (!s) return loaded.error ? <Banner tone="error">{loaded.error.message}</Banner> : null
  const left = Math.max(0, s.focus.untilMs - now)
  const sample = SAMPLE(s.nudgeTone)

  return (
    <Card>
      <CardTitle>Nudge style</CardTitle>
      {err && <div className="mb-3"><Banner tone="error">{err}</Banner></div>}
      <div className="space-y-5">
        <div>
          <div className="mb-2 font-medium text-ink">Wording</div>
          <Segmented<Tone>
            label="Nudge wording"
            value={s.nudgeTone}
            onChange={(v) => put({ nudgeTone: v })}
            options={[{ value: 'gentle', label: 'Gentle' }, { value: 'neutral', label: 'Neutral' }, { value: 'direct', label: 'Direct' }]}
          />
          <div className="mt-3 rounded-xl bg-line/40 p-3 text-sm" aria-label="Example notification">
            <div className="font-medium text-ink">{sample.title}</div>
            <div className="text-ink-2">{sample.body}</div>
          </div>
        </div>

        <div>
          <div className="flex items-center justify-between gap-4">
            <div>
              <div className="font-medium text-ink">Only nudge me during focus sessions</div>
              <div className="text-sm text-ink-2">Posture is still tracked the rest of the time, just without alerts.</div>
            </div>
            <Toggle label="Only nudge during focus sessions" checked={s.focus.onlyDuringFocus} onChange={(v) => put({ focus: { onlyDuringFocus: v } })} />
          </div>
          {s.focus.onlyDuringFocus && (
            <div className="mt-3">
              {running ? (
                <div className="flex flex-wrap items-center gap-3 text-sm">
                  <span className="text-ink" role="status">Focus session: {Math.ceil(left / 60_000)} min left</span>
                  <Button variant="secondary" onClick={() => focus(0)}>Stop</Button>
                </div>
              ) : (
                <div className="flex flex-wrap items-center gap-2 text-sm">
                  <span className="text-ink-2">No session running. Start one:</span>
                  {DURATIONS.map((m) => (
                    <Button key={m} variant="secondary" onClick={() => focus(m)}>{m} min</Button>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </Card>
  )
}
