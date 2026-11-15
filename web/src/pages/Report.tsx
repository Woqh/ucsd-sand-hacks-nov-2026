import { Link } from 'react-router-dom'
import { api, tzOffsetMin } from '../api'
import { dayName, hour12 } from '../coach/localAnalysis'
import { loadProfile } from '../coach/profile'
import { Banner, Button } from '../components/ui'
import { formatDuration } from '../format'
import { usePoll } from '../hooks'
import type { CoachInsights, Metrics } from '../types'

const dash = (v: number | null | undefined, unit = ''): string => (v == null ? '–' : `${Math.round(v)}${unit}`)

/** A one-page summary meant for printing or "Save as PDF". Built in the browser from the person's own numbers;
 *  the coaching profile section comes from this browser's saved profile (never from the server). */
export default function Report() {
  const tz = tzOffsetMin()
  const ins = usePoll(() => api<CoachInsights>(`/coach/insights?tzOffsetMin=${tz}`), 0)
  const met = usePoll(() => api<Metrics>(`/metrics?range=week&tzOffsetMin=${tz}`), 0)
  const profile = loadProfile()

  if (ins.error || met.error) return <Banner tone="error">{(ins.error ?? met.error)!.message}</Banner>
  if (!ins.data || !met.data) return <p className="text-ink-2">Putting your report together…</p>

  const { pack } = ins.data
  const m = met.data
  const sum = m.summary
  const delta = sum.score != null && m.previous.score != null ? Math.round(sum.score - m.previous.score) : null

  return (
    <article className="mx-auto max-w-2xl space-y-6 text-ink">
      <div className="flex items-start justify-between gap-3 print:hidden">
        <Link to="/coach" className="text-sm text-ink-2 hover:text-ink">← Back to Coach</Link>
        <Button onClick={() => window.print()}>Print or save as PDF</Button>
      </div>

      <header className="border-b border-line pb-4">
        <h1 className="text-3xl font-semibold tracking-tight">My posture report</h1>
        <p className="mt-1 text-sm text-ink-2">Last 7 days, with a {pack.window.days}-day view of habits. Made on this device.</p>
      </header>

      <section>
        <h2 className="text-lg font-semibold">This week</h2>
        <dl className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
          {[
            ['Posture score', dash(sum.score), delta == null ? '' : `${delta >= 0 ? '+' : ''}${delta} vs last week`],
            ['Good posture', dash(sum.goodPct, '%'), ''],
            ['Time seated', formatDuration(sum.seatedSec), ''],
            ['Slouch events', String(sum.slouchEvents), sum.slouchEventsPerHour != null ? `${sum.slouchEventsPerHour.toFixed(1)} per hour` : ''],
          ].map(([k, v, h]) => (
            <div key={k} className="rounded-xl border border-line p-3">
              <dt className="text-xs text-ink-2">{k}</dt>
              <dd className="mt-0.5 text-2xl font-semibold">{v}</dd>
              {h && <div className="text-xs text-ink-2">{h}</div>}
            </div>
          ))}
        </dl>
        <p className="mt-3 text-sm text-ink-2">
          Longest good stretch: {formatDuration(sum.longestGoodStreakSec)}. Day streak: {pack.habits.strength.forgivingStreak}.
          {pack.habits.strength.consistencyPct != null && ` ${Math.round(pack.habits.strength.consistencyPct)}% of recent days reached the ${pack.habits.strength.targetPct}% goal.`}
        </p>
      </section>

      <section>
        <h2 className="text-lg font-semibold">Your patterns</h2>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-ink-2">
          {pack.patterns.fatigue.onsetMin != null && <li>Your posture tends to slip after about {pack.patterns.fatigue.onsetMin} minutes of sitting.</li>}
          {pack.patterns.dangerHours[0] && <li>Weakest time: {dayName(pack.patterns.dangerHours[0].day)} around {hour12(pack.patterns.dangerHours[0].hour)} ({Math.round(pack.patterns.dangerHours[0].slouchPct)}% slouching).</li>}
          {pack.coaching.response.within30Pct != null && <li>You sat back up within 30 seconds after {Math.round(pack.coaching.response.within30Pct)}% of nudges.</li>}
          {pack.breaks.longestSitMin != null && <li>Longest unbroken sit: {Math.round(pack.breaks.longestSitMin)} minutes.</li>}
          <li>{pack.habits.challenge.title}. {pack.habits.challenge.detail}</li>
        </ul>
      </section>

      {profile && (
        <section>
          <h2 className="text-lg font-semibold">My coaching profile</h2>
          <p className="mt-2 text-sm">{profile.analysis.headline}</p>
          <p className="mt-1 text-sm text-ink-2">{profile.analysis.summary}</p>
          <h3 className="mt-3 text-sm font-semibold">Plan for the week</h3>
          <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-ink-2">
            {profile.analysis.weeklyPlan.map((p, i) => (
              <li key={i}><span className="text-ink">{p.when}:</span> {p.action}</li>
            ))}
          </ul>
        </section>
      )}

      <footer className="border-t border-line pt-3 text-xs text-ink-2">
        Illustrative and educational only, not medical advice. Research links poor sitting posture with discomfort in some studies but hasn't shown that it causes pain; moving regularly is still a good habit. If you have pain, talk to a clinician.
      </footer>
    </article>
  )
}
