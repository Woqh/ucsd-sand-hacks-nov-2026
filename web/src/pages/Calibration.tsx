import { useEffect, useRef, useState } from 'react'
import { api, ApiError } from '../api'
import { Banner, Button, Card, CardTitle } from '../components/ui'
import { usePoll } from '../hooks'
import type { CalibrationBaseline, Health } from '../types'

const COUNTDOWN_SEC = 10
type Phase = 'idle' | 'counting' | 'saving' | 'done' | 'rejected'

/** Guided "sit comfortably" flow. The interface owns the flow and stores the result; the model does
 *  the math AND judges whether the captured posture is a good goal posture (the calibration gate:
 *  `accepted: false` + `issues` means "try again", and the server refuses to store it either way).
 *  Until the on-device model lands this runs against the server's model STUBS. */
export default function Calibration() {
  const current = usePoll(() => api<{ calibrated: boolean; baseline: CalibrationBaseline | null }>('/calibration'), 0)
  const health = usePoll(() => api<Health>('/health', { auth: false }), 0)
  const [phase, setPhase] = useState<Phase>('idle')
  const [left, setLeft] = useState(COUNTDOWN_SEC)
  const [error, setError] = useState<string | null>(null)
  const [issues, setIssues] = useState<string[]>([])
  const [saved, setSaved] = useState<CalibrationBaseline | null>(null)
  const timer = useRef<ReturnType<typeof setInterval> | undefined>(undefined)

  useEffect(() => () => clearInterval(timer.current), [])

  /** `demoBad` (dev builds only) asks the model stub to reject the posture, to show the gate working. */
  async function begin(demoBad = false) {
    setError(null)
    setIssues([])
    try {
      await api('/model/calibrate/start', { method: 'POST' })
    } catch (e) {
      setError((e as Error).message)
      return
    }
    setPhase('counting')
    setLeft(COUNTDOWN_SEC)
    let n = COUNTDOWN_SEC
    timer.current = setInterval(() => {
      n -= 1
      setLeft(n)
      if (n <= 0) {
        clearInterval(timer.current)
        void finish(demoBad)
      }
    }, 1000)
  }

  async function finish(demoBad: boolean) {
    setPhase('saving')
    try {
      const baseline = await api<CalibrationBaseline>(`/model/calibrate/finish${demoBad ? '?force=bad' : ''}`, { method: 'POST' })
      if (baseline.accepted === false) return reject(baseline.issues ?? [])
      // accepted: store it (the server re-checks `accepted`, so a rejected posture can never be saved)
      const stored = await api<{ baseline: CalibrationBaseline }>('/calibration', { method: 'PUT', body: baseline })
      setSaved({ ...stored.baseline, stub: baseline.stub })
      setPhase('done')
      current.refresh()
    } catch (e) {
      if (e instanceof ApiError && e.code === 'posture_not_good') return reject(e.issues ?? [e.message])
      setError((e as Error).message)
      setPhase('idle')
    }
  }

  function reject(list: string[]) {
    setIssues(list)
    setPhase('rejected')
  }

  function cancel() {
    clearInterval(timer.current)
    setPhase('idle')
  }

  const baseline = saved ?? current.data?.baseline ?? null

  return (
    <div className="mx-auto max-w-xl space-y-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-ink">Your goal posture</h1>
        <p className="mt-1 text-ink-2">
          Sitwise learns <em>your</em> comfortable, healthy posture, then nudges you when you drift from it. Redo this any time.
        </p>
      </div>

      {error && <Banner tone="error">{error}</Banner>}

      {phase === 'idle' && (
        <Card>
          <CardTitle>{baseline ? 'Recalibrate' : 'Set your goal posture'}</CardTitle>
          <ol className="mb-4 list-decimal space-y-1 pl-5 text-sm text-ink-2">
            <li>Make sure the camera (your phone, or a webcam running the model bridge) is on the side of your chair and can see you.</li>
            <li>Sit the way you want to sit: back supported, shoulders relaxed, ears over shoulders.</li>
            <li>Hold still while the countdown runs.</li>
          </ol>
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => begin()}>{baseline ? 'Start again' : "I'm sitting comfortably. Start"}</Button>
            {health.data?.devRoutes && (
              <Button variant="ghost" onClick={() => begin(true)}>
                Demo: simulate a slouched posture
              </Button>
            )}
          </div>
        </Card>
      )}

      {phase === 'counting' && (
        <Card className="text-center">
          <div className="text-sm text-ink-2">Hold your best posture</div>
          <div className="my-3 text-8xl font-semibold tracking-tight text-ink" aria-live="polite">
            {Math.max(0, left)}
          </div>
          <div className="mx-auto mb-4 max-w-xs">
            <div className="h-2 overflow-hidden rounded-full" style={{ background: 'var(--seq-1)' }}>
              <div className="h-full rounded-full bg-accent transition-[width] duration-1000 ease-linear" style={{ width: `${((COUNTDOWN_SEC - left) / COUNTDOWN_SEC) * 100}%` }} />
            </div>
          </div>
          <Button variant="ghost" onClick={cancel}>
            Cancel
          </Button>
        </Card>
      )}

      {phase === 'saving' && (
        <Card className="text-center">
          <p className="py-6 text-ink-2">Checking your posture…</p>
        </Card>
      )}

      {phase === 'rejected' && (
        <Card>
          <div role="alert">
            <CardTitle>That wasn't your best posture</CardTitle>
            <p className="mb-2 text-sm text-ink-2">
              Sitwise only saves a goal posture that's healthy to aim for, so nothing was saved. Here's what it noticed:
            </p>
            <ul className="mb-3 list-disc space-y-1 pl-5 text-sm text-ink">
              {(issues.length ? issues : ['Your posture looked slouched.']).map((i) => (
                <li key={i}>{i}</li>
              ))}
            </ul>
            <p className="mb-4 text-sm text-ink-2">
              Sit tall with your lower back supported, let your shoulders drop, and bring your ears over your shoulders. It should feel comfortable, not stiff. Then try again.
            </p>
          </div>
          <Button onClick={() => setPhase('idle')}>Try again</Button>
        </Card>
      )}

      {phase === 'done' && saved && (
        <Banner tone="info">
          <strong>Saved.</strong> Your goal posture is set. Slouch alerts now measure against it.
        </Banner>
      )}

      {baseline && phase !== 'counting' && phase !== 'rejected' && (
        <Card>
          <CardTitle hint={`captured ${new Date(baseline.capturedAt).toLocaleString()}`}>Saved goal posture</CardTitle>
          <dl className="grid grid-cols-3 gap-2 text-center">
            {Object.entries(baseline.goal).map(([k, v]) => (
              <div key={k} className="rounded-xl bg-line/40 px-2 py-3">
                <dt className="text-xs text-ink-2">{labelFor(k)}</dt>
                <dd className="text-lg font-semibold text-ink">{v}</dd>
              </div>
            ))}
          </dl>
          <p className="mt-3 text-xs text-ink-2">
            Tolerance ±{baseline.tolerance}. {baseline.stub && 'These are placeholder values from the model stub. Start the model bridge (or the phone app) first to measure your real posture.'}
          </p>
        </Card>
      )}
    </div>
  )
}

const labelFor = (k: string) => ({ neckAngle: 'Neck angle (°)', torsoAngle: 'Torso angle (°)', headForwardOffset: 'Head forward' })[k] ?? k
