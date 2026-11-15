import { useState } from 'react'
import { api } from '../../api'
import type { CoachPack, Suggestion } from '../../types'
import { Banner, Button } from '../ui'
import { RecoveryChart, ResponseBars } from './charts'
import NudgeStyleCard from './NudgeStyle'
import { Fact, NotEnough, num, Section } from './shared'

const LEVEL = ['First nudge', 'Repeat nudge', 'Break prompt']
const PART_LABEL = { morning: 'Morning', afternoon: 'Afternoon', evening: 'Evening' } as const

const FATIGUE_TEXT = {
  ok: 'Your response to nudges is holding steady.',
  watch: "You're responding to nudges a little less than you used to. Worth watching.",
  fatigued: "You're responding to nudges noticeably less than before. That's common: people get used to alerts. Try a different wording or a longer cooldown.",
  insufficient: 'Not enough nudges yet to tell whether you are getting used to them.',
} as const

function SuggestionCard({ s, onApply }: { s: Suggestion; onApply: (s: Suggestion) => Promise<void> }) {
  const [state, setState] = useState<'idle' | 'busy' | 'done'>('idle')
  return (
    <li className="rounded-xl border border-line p-3 text-sm">
      <div className="font-medium text-ink">{s.title}</div>
      <div className="mt-0.5 text-ink-2">{s.why}</div>
      <div className="mt-2">
        {state === 'done' ? (
          <span className="text-good-ink" role="status">Applied</span>
        ) : (
          <Button
            variant="secondary"
            disabled={state === 'busy'}
            onClick={async () => {
              setState('busy')
              try {
                await onApply(s)
                setState('done')
              } catch {
                setState('idle')
              }
            }}
          >
            {state === 'busy' ? 'Applying…' : 'Apply this change'}
          </Button>
        )}
      </div>
    </li>
  )
}

export default function CoachingPanel({ pack, onChanged }: { pack: CoachPack; onChanged: () => void }) {
  const co = pack.coaching
  const r = co.response
  const [err, setErr] = useState<string | null>(null)

  async function apply(s: Suggestion) {
    setErr(null)
    try {
      await api('/settings', { method: 'PUT', body: s.patch })
      onChanged()
    } catch (e) {
      setErr((e as Error).message)
      throw e
    }
  }

  return (
    <div className="space-y-4">
      <Section title="How you respond to nudges" hint={`${r.nudges} nudges`}>
        {r.nudges < 3 ? (
          <NotEnough>Not enough nudges yet. Once you've had a few, this shows how quickly you sit back up and what helps.</NotEnough>
        ) : (
          <div className="space-y-5">
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <Fact label="Sat up within 30 s" value={num(r.within30Pct, '%')} />
              <Fact label="Within 60 s" value={num(r.within60Pct, '%')} />
              <Fact label="Median time" value={r.medianRecoverySec != null ? `${Math.round(r.medianRecoverySec)} s` : '–'} />
              <Fact label="Left instead" value={r.leftAfterNudge} hint="walked away after a nudge" />
            </div>
            <ResponseBars title="By nudge type" rows={r.byLevel.map((l) => ({ label: LEVEL[l.level - 1] ?? `Level ${l.level}`, n: l.n, pct: l.n >= 3 ? l.within30Pct : null }))} />
            <ResponseBars title="By time of day" rows={r.byPartOfDay.map((p) => ({ label: PART_LABEL[p.part], n: p.n, pct: p.n >= 3 ? p.within30Pct : null }))} />
            <p className="text-xs text-ink-2">Bars show the share of nudges you fixed within 30 seconds. Groups with fewer than 3 nudges are left blank rather than guessed.</p>
          </div>
        )}
      </Section>

      <Section title="Are you getting faster?" hint="seconds to sit back up, by week">
        <RecoveryChart trend={co.recoveryTrend} />
      </Section>

      <Section title="Nudge fatigue">
        <p className="text-sm text-ink-2">{FATIGUE_TEXT[co.alertFatigue.status]}</p>
        {co.alertFatigue.firstHalfPct != null && co.alertFatigue.secondHalfPct != null && (
          <p className="mt-2 text-xs text-ink-2">
            Earlier half: {Math.round(co.alertFatigue.firstHalfPct)}% fixed within 30 s. Recent half: {Math.round(co.alertFatigue.secondHalfPct)}% ({co.alertFatigue.n} nudges).
          </p>
        )}
      </Section>

      <Section title="Changes worth trying" hint="based on your numbers">
        {err && <div className="mb-3"><Banner tone="error">{err}</Banner></div>}
        {co.suggestions.length === 0 ? (
          <NotEnough>No changes suggested right now. Your current settings look like a good fit for how you respond.</NotEnough>
        ) : (
          <ul className="space-y-2">
            {co.suggestions.map((s) => (
              <SuggestionCard key={s.id} s={s} onApply={apply} />
            ))}
          </ul>
        )}
        <p className="mt-3 text-xs text-ink-2">Nothing changes until you press Apply. These are suggestions from your own data, not an automatic adjustment.</p>
      </Section>

      <NudgeStyleCard onChanged={onChanged} />
    </div>
  )
}
