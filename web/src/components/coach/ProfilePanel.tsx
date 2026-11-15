import { useEffect, useRef, useState } from 'react'
import { api } from '../../api'
import { buildLocalAnalysis } from '../../coach/localAnalysis'
import { clearProfile, loadProfile, saveProfile, type StoredProfile } from '../../coach/profile'
import type { Analysis, CoachInsights, CoachPreview, Exercise, Settings, Tone } from '../../types'
import { Banner, Button, Card, CardTitle, cx } from '../ui'
import { ConsentBox } from './shared'

const TONE_LABEL: Record<Tone, string> = { gentle: 'Gentle', neutral: 'Neutral', direct: 'Direct' }
const CONF_LABEL = { low: 'Early signs', medium: 'Fairly steady', high: 'Well supported' } as const

export function ExerciseCard({ ex }: { ex: Exercise }) {
  return (
    <details className="rounded-xl border border-line p-3">
      <summary className="cursor-pointer text-sm font-medium text-ink">{ex.title}</summary>
      <ol className="mt-2 list-decimal space-y-1 pl-5 text-sm text-ink-2">
        {ex.steps.map((s, i) => (
          <li key={i}>{s}</li>
        ))}
      </ol>
      {ex.safety && <p className="mt-2 text-xs text-ink-2">{ex.safety}</p>}
    </details>
  )
}

/** Renders a coaching profile (from Gemini or from the on-device rules; the shape is the same). */
export function AnalysisView({ a, library, current, onApplyTone }: { a: Analysis; library: Exercise[]; current: Tone; onApplyTone?: (t: Tone) => void }) {
  const exercises = a.recommendedExerciseIds.map((id) => library.find((e) => e.id === id)).filter((e): e is Exercise => !!e)
  return (
    <div className="space-y-5">
      <div>
        <h3 className="text-xl font-semibold leading-snug tracking-tight text-ink">{a.headline}</h3>
        <p className="mt-2 text-sm text-ink-2">{a.summary}</p>
        <p className="mt-2 text-xs text-ink-2">Confidence: {CONF_LABEL[a.confidence]}</p>
      </div>

      <div>
        <h4 className="text-sm font-semibold text-ink">How you respond to coaching</h4>
        <p className="mt-1 text-sm text-ink-2">{a.howYouRespond}</p>
        {a.whatWorks.length > 0 && (
          <ul className="mt-3 space-y-2">
            {a.whatWorks.map((w, i) => (
              <li key={i} className="rounded-xl bg-line/40 p-3 text-sm">
                <div className="font-medium text-ink">{w.insight}</div>
                <div className="mt-0.5 text-xs text-ink-2">{w.evidence}</div>
              </li>
            ))}
          </ul>
        )}
      </div>

      {a.strengths.length > 0 && (
        <div>
          <h4 className="text-sm font-semibold text-ink">What you're doing well</h4>
          <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-ink-2">
            {a.strengths.map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ul>
        </div>
      )}

      <div>
        <h4 className="text-sm font-semibold text-ink">Where to focus</h4>
        <ul className="mt-2 space-y-2">
          {a.focusAreas.map((f, i) => (
            <li key={i} className="rounded-xl border border-line p-3 text-sm">
              <div className="font-medium text-ink">{f.title}</div>
              <div className="mt-0.5 text-ink-2">{f.why}</div>
              <div className="mt-1 text-ink">Try: {f.action}</div>
            </li>
          ))}
        </ul>
      </div>

      <div>
        <h4 className="text-sm font-semibold text-ink">Your plan for this week</h4>
        <ul className="mt-2 divide-y divide-line rounded-xl border border-line text-sm">
          {a.weeklyPlan.map((p, i) => (
            <li key={i} className="grid grid-cols-[6.5rem_1fr] gap-3 px-3 py-2">
              <span className="text-ink-2">{p.when}</span>
              <span className="text-ink">{p.action}</span>
            </li>
          ))}
        </ul>
      </div>

      {exercises.length > 0 && (
        <div>
          <h4 className="text-sm font-semibold text-ink">Exercises that fit how you slouch</h4>
          <div className="mt-2 space-y-2">
            {exercises.map((e) => (
              <ExerciseCard key={e.id} ex={e} />
            ))}
          </div>
        </div>
      )}

      <div className="rounded-xl bg-line/40 p-3 text-sm">
        <div className="text-ink">
          Suggested nudge style: <span className="font-semibold">{TONE_LABEL[a.suggestedTone]}</span>
          {a.suggestedTone === current && <span className="text-ink-2"> (already your setting)</span>}
        </div>
        <div className="mt-0.5 text-ink-2">{a.toneWhy}</div>
        {onApplyTone && a.suggestedTone !== current && (
          <Button variant="secondary" className="mt-2" onClick={() => onApplyTone(a.suggestedTone)}>
            Use {TONE_LABEL[a.suggestedTone].toLowerCase()} wording
          </Button>
        )}
      </div>

      {a.caveats.length > 0 && (
        <ul className="space-y-1 text-xs text-ink-2">
          {a.caveats.map((c, i) => (
            <li key={i}>• {c}</li>
          ))}
        </ul>
      )}
    </div>
  )
}

type Phase = 'idle' | 'previewing' | 'sending'

/** The coaching profile. It is stored ONLY in this browser; the server keeps nothing from it. The on-device
 *  version needs no consent because nothing leaves the page. "Improve with Gemini" is opt-in, shows exactly
 *  what would be sent, and falls back to the on-device profile if anything goes wrong. */
export default function ProfilePanel({ insights, onToneApplied }: { insights: CoachInsights; onToneApplied: () => void }) {
  const [stored, setStored] = useState<StoredProfile | null>(() => loadProfile())
  const [phase, setPhase] = useState<Phase>('idle')
  const [consent, setConsent] = useState(false)
  const [preview, setPreview] = useState<CoachPreview | null>(null)
  const [message, setMessage] = useState<{ tone: 'info' | 'warn' | 'error'; text: string } | null>(null)
  const [saveFailed, setSaveFailed] = useState(false)
  const built = useRef(false)
  const { pack, library, ai } = insights

  // First visit: build the on-device profile automatically (it never leaves this page).
  useEffect(() => {
    if (stored || built.current) return
    built.current = true
    const p: StoredProfile = { savedAt: Date.now(), source: 'on-device', analysis: buildLocalAnalysis(pack, library) }
    setSaveFailed(!saveProfile(p))
    setStored(p)
  }, [stored, pack, library])

  function rebuildLocal() {
    const p: StoredProfile = { savedAt: Date.now(), source: 'on-device', analysis: buildLocalAnalysis(pack, library) }
    setSaveFailed(!saveProfile(p))
    setStored(p)
    setMessage({ tone: 'info', text: 'Rebuilt on this device from your latest numbers.' })
  }

  async function openPreview() {
    setMessage(null)
    setPhase('previewing')
    try {
      setPreview(await api<CoachPreview>('/coach/preview'))
    } catch (e) {
      setPhase('idle')
      setMessage({ tone: 'error', text: (e as Error).message })
    }
  }

  async function sendToGemini() {
    setPhase('sending')
    setMessage(null)
    try {
      const res = await api<{ analysis: Analysis; model: string }>('/coach/analyze', { method: 'POST', body: { consent: true } })
      const p: StoredProfile = { savedAt: Date.now(), source: 'gemini', model: res.model, analysis: res.analysis }
      setSaveFailed(!saveProfile(p))
      setStored(p)
      setMessage({ tone: 'info', text: 'Done. The result is saved only in this browser.' })
    } catch (e) {
      // Whatever went wrong, the on-device profile is still there.
      setMessage({ tone: 'warn', text: `${(e as Error).message} Your on-device profile still works.` })
    } finally {
      setPhase('idle')
      setPreview(null)
      setConsent(false)
    }
  }

  function forget() {
    clearProfile()
    built.current = true // don't silently rebuild right after an explicit delete
    setStored(null)
    setMessage({ tone: 'info', text: 'Profile deleted from this browser.' })
  }

  async function applyTone(tone: Tone) {
    try {
      await api<{ settings: Settings }>('/settings', { method: 'PUT', body: { nudgeTone: tone } })
      onToneApplied()
    } catch (e) {
      setMessage({ tone: 'error', text: (e as Error).message })
    }
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardTitle hint={stored ? (stored.source === 'gemini' ? `Gemini · ${stored.model ?? ''}` : 'Built on this device') : undefined}>Your coaching profile</CardTitle>
        <p className="mb-4 rounded-xl bg-accent/10 px-3 py-2 text-sm text-ink">
          <strong>Private to this browser.</strong> This profile is saved only here. Sitwise's server never stores it, and it never includes your pain check-ins or any picture.
        </p>
        {message && <div className="mb-3"><Banner tone={message.tone}>{message.text}</Banner></div>}
        {saveFailed && <div className="mb-3"><Banner tone="warn">This browser wouldn't save the profile (private window?). It will be rebuilt each visit.</Banner></div>}
        {stored ? (
          <AnalysisView a={stored.analysis} library={library} current={pack.coaching.currentSettings.nudgeTone} onApplyTone={applyTone} />
        ) : (
          <p className="text-sm text-ink-2">No profile saved in this browser. Build one from your numbers; it takes a moment and stays on this device.</p>
        )}
        <div className="mt-5 flex flex-wrap gap-2">
          <Button variant="secondary" onClick={rebuildLocal}>{stored ? 'Rebuild on this device' : 'Build on this device'}</Button>
          {stored && <Button variant="ghost" onClick={forget}>Delete profile</Button>}
        </div>
        {stored && <p className="mt-2 text-xs text-ink-2">Last updated {new Date(stored.savedAt).toLocaleString()}</p>}
      </Card>

      <Card>
        <CardTitle>Go deeper with Gemini (optional)</CardTitle>
        <p className="text-sm text-ink-2">
          Gemini can write a more tailored read on how you respond to coaching. It works only from de-identified habit numbers, and only if you say yes each time.
        </p>

        {!ai.configured ? (
          <p className="mt-3 rounded-xl bg-line/40 p-3 text-sm text-ink-2">
            Gemini isn't switched on for this server, so the on-device profile above is what you get. Nothing is missing: it uses the same numbers.
          </p>
        ) : phase === 'idle' ? (
          <div className="mt-3">
            <Button variant="secondary" onClick={openPreview}>See what would be sent</Button>
          </div>
        ) : preview ? (
          <div className="mt-4 space-y-3">
            <ul className="space-y-1.5 rounded-xl border border-line p-3 text-sm text-ink-2">
              {preview.disclosure.map((d, i) => (
                <li key={i}>• {d}</li>
              ))}
            </ul>
            <details className="rounded-xl border border-line p-3 text-sm">
              <summary className="cursor-pointer text-ink">The exact data that would be sent ({preview.bytes.toLocaleString()} bytes)</summary>
              <pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap break-words text-xs text-ink-2" data-testid="preview-json">{JSON.stringify(preview.payload, null, 2)}</pre>
            </details>
            <ConsentBox checked={consent} onChange={setConsent}>
              I've seen what's sent and I'm happy for Google's Gemini ({ai.model}) to process it once, to write my profile.
            </ConsentBox>
            <div className="flex flex-wrap gap-2">
              <Button disabled={!consent || phase === 'sending'} onClick={sendToGemini}>
                {phase === 'sending' ? 'Asking Gemini…' : 'Send and build my profile'}
              </Button>
              <Button variant="ghost" disabled={phase === 'sending'} onClick={() => { setPhase('idle'); setPreview(null); setConsent(false) }}>Cancel</Button>
            </div>
          </div>
        ) : (
          <p className={cx('mt-3 text-sm text-ink-2')}>Loading the preview…</p>
        )}
      </Card>
    </div>
  )
}
