import { Link } from 'react-router-dom'
import type { CoachPack } from '../../types'
import { Meter } from '../ui'
import { Fact, NotEnough, num, Section } from './shared'
import ShareCard from './ShareCard'

export default function HabitsPanel({ pack }: { pack: CoachPack }) {
  const h = pack.habits
  const s = h.strength
  const b = pack.breaks

  return (
    <div className="space-y-4">
      <Section title="Habit strength" hint={`last ${pack.window.days} days`}>
        {s.consistencyPct == null ? (
          <NotEnough>Not enough days of data yet. Keep sitting with Sitwise and this builds up.</NotEnough>
        ) : (
          <>
            <div className="flex items-baseline gap-2">
              <span className="text-4xl font-semibold tracking-tight text-ink">{Math.round(s.consistencyPct)}%</span>
              <span className="text-sm text-ink-2">of recent days at your {s.targetPct}% goal ({s.daysAtTarget} of {s.daysWithData})</span>
            </div>
            <div className="mt-2"><Meter value={s.consistencyPct} label="Days at your goal" /></div>
          </>
        )}
        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Fact label="Day streak" value={s.forgivingStreak} hint="one missed day is forgiven per week" />
          <Fact label="Strict streak" value={s.strictStreak} hint="no misses allowed" />
          <Fact label="Best day" value={num(h.bests.bestDayScore)} hint="score" />
          <Fact label="Best week" value={num(h.bests.bestWeekScore)} hint="score" />
        </div>
      </Section>

      {h.relapse.active && h.relapse.message && (
        <Section title="A rough patch is normal">
          <p className="text-sm text-ink">{h.relapse.message}</p>
          {h.relapse.smallerGoalPct != null && <p className="mt-2 text-sm text-ink-2">A smaller goal for now: {h.relapse.smallerGoalPct}% good posture.</p>}
        </Section>
      )}

      <Section title="This week's challenge">
        <p className="font-medium text-ink">{h.challenge.title}</p>
        <p className="mt-1 text-sm text-ink-2">{h.challenge.detail}</p>
      </Section>

      <Section title="Breaks" hint={`target: stand up every ${b.targetMin} min`}>
        {b.runs === 0 ? (
          <NotEnough>No sitting sessions to analyse yet.</NotEnough>
        ) : (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Fact label="Longest sit" value={b.longestSitMin != null ? `${Math.round(b.longestSitMin)} min` : '–'} />
            <Fact label="Average sit" value={b.avgSitMin != null ? `${Math.round(b.avgSitMin)} min` : '–'} />
            <Fact label="Sits over target" value={num(b.runsOverTargetPct, '%')} />
            <Fact label="Breaks per day" value={b.breaksPerDay.toFixed(1)} hint={`+ ${b.microBreaksPerDay.toFixed(1)} short ones`} />
          </div>
        )}
      </Section>

      <Section title="Share your progress">
        <ShareCard pack={pack} />
      </Section>

      <Section title="Weekly report">
        <p className="mb-3 text-sm text-ink-2">A one-page summary you can print or save as a PDF.</p>
        <Link to="/report" className="inline-flex min-h-11 items-center rounded-xl border border-axis px-4 text-sm font-medium text-ink hover:bg-line/50">
          Open report
        </Link>
      </Section>
    </div>
  )
}
