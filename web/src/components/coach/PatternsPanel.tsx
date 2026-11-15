import type { CoachPack, Exercise } from '../../types'
import { FatigueChart, FingerprintBar } from './charts'
import { ExerciseCard } from './ProfilePanel'
import { dayName, Fact, hour12, NotEnough, num, Section } from './shared'

const SIGNATURE_TEXT = {
  headForward: 'Mostly your head drifting forward',
  trunkLean: 'Mostly your upper body leaning forward',
  mixed: 'A mix of head-forward and leaning',
} as const

export default function PatternsPanel({ pack, library }: { pack: CoachPack; library: Exercise[] }) {
  const p = pack.patterns
  const f = p.fingerprint
  const drift = p.drift
  const matched = pack.exercises.map((e) => library.find((l) => l.id === e.id)).filter((e): e is Exercise => !!e)

  return (
    <div className="space-y-4">
      <Section title="How you slouch" hint={f ? `${f.samples} readings` : undefined}>
        {f ? (
          <>
            <p className="mb-3 text-sm text-ink-2">{SIGNATURE_TEXT[f.signature]}. Compared with your own good posture, each slouching reading is sorted by what moved most.</p>
            <FingerprintBar f={f} />
          </>
        ) : (
          <NotEnough>Not enough posture readings yet to tell how you slouch. This fills in after a few days of use.</NotEnough>
        )}
      </Section>

      <Section title="When your posture slips" hint="by minutes since you sat down">
        <FatigueChart buckets={p.fatigue.buckets} onsetMin={p.fatigue.onsetMin} />
        <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3">
          <Fact label="Slips after" value={p.fatigue.onsetMin != null ? `~${p.fatigue.onsetMin} min` : '–'} hint={p.fatigue.onsetMin == null ? 'No clear slip point yet' : 'of sitting'} />
          <Fact label="Typical first slouch" value={p.onsetLatency.medianSec != null ? `${Math.round(p.onsetLatency.medianSec / 60)} min` : '–'} hint={`across ${p.onsetLatency.runs} sits`} />
          <Fact label="Sits that include a slouch" value={num(p.onsetLatency.runsWithSlouchPct, '%')} />
        </div>
      </Section>

      <Section title="Your weakest times">
        {p.dangerHours.length === 0 ? (
          <NotEnough>No clear weak spot yet.</NotEnough>
        ) : (
          <ul className="divide-y divide-line rounded-xl border border-line text-sm">
            {p.dangerHours.map((d) => (
              <li key={`${d.day}-${d.hour}`} className="flex items-center justify-between gap-3 px-3 py-2">
                <span className="text-ink">{dayName(d.day)} around {hour12(d.hour)}</span>
                <span className="tabular-nums text-ink-2">{Math.round(d.slouchPct)}% slouching <span className="text-xs">({Math.round(d.seatedMin)} min of data)</span></span>
              </li>
            ))}
          </ul>
        )}
        {p.triggers.length > 0 && (
          <div className="mt-4">
            <h3 className="text-sm font-semibold text-ink">What tends to set it off</h3>
            <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-ink-2">
              {p.triggers.map((t) => (
                <li key={t.kind}>{t.label}</li>
              ))}
            </ul>
          </div>
        )}
        {pack.workHours && (
          <p className="mt-4 text-sm text-ink-2">
            You usually sit between {hour12(pack.workHours.startHour)} and {hour12(pack.workHours.endHour)} (from {pack.workHours.days} days of data).
          </p>
        )}
      </Section>

      <Section title="Has your good posture drifted?">
        {drift.weekly.length < 2 ? (
          <NotEnough>Needs a few weeks of data to compare.</NotEnough>
        ) : drift.drifting ? (
          <p className="text-sm text-ink">
            Even when Sitwise calls your posture good, it's sitting a little further from the upright reference than it used to. That can mean your sitting habits have changed.
          </p>
        ) : (
          <p className="text-sm text-ink-2">Your "good" posture is holding steady against the upright reference.</p>
        )}
      </Section>

      {p.setupHints.length > 0 && (
        <Section title="Your setup" hint="worth a look">
          <ul className="space-y-2">
            {p.setupHints.map((h) => (
              <li key={h.id} className="rounded-xl border border-line p-3 text-sm">
                <div className="font-medium text-ink">{h.title}</div>
                <div className="mt-0.5 text-ink-2">{h.detail}</div>
                <div className="mt-1 text-xs text-ink-2">Why: {h.because}</div>
              </li>
            ))}
          </ul>
        </Section>
      )}

      {matched.length > 0 && (
        <Section title="Exercises matched to you">
          <div className="space-y-2">
            {matched.map((e) => (
              <ExerciseCard key={e.id} ex={e} />
            ))}
          </div>
        </Section>
      )}
    </div>
  )
}
