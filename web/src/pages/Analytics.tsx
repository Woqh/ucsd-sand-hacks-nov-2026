import { useState } from 'react'
import { api, tzOffsetMin } from '../api'
import Heatmap from '../components/charts/Heatmap'
import { EvidenceMeter, PopulationContext } from '../components/Evidence'
import PainInsights from '../components/PainInsights'
import Timeline from '../components/charts/Timeline'
import TrendChart from '../components/charts/TrendChart'
import { Banner, Card, CardTitle, Meter, Segmented, Stat, StateIcon, cx } from '../components/ui'
import { formatDuration, formatMinutes, pct } from '../format'
import { usePoll } from '../hooks'
import type { Metrics } from '../types'

type Range = Metrics['range']
type View = 'posture' | 'pain'
const VIEWS: { value: View; label: string }[] = [
  { value: 'posture', label: 'Posture' },
  { value: 'pain', label: 'Pain & evidence' },
]
const RANGES: { value: Range; label: string }[] = [
  { value: 'day', label: 'Today' },
  { value: 'week', label: 'Week' },
  { value: 'month', label: 'Month' },
]
const PERIOD: Record<Range, { now: string; prev: string }> = {
  day: { now: 'today', prev: 'yesterday' },
  week: { now: 'this week', prev: 'last week' },
  month: { now: 'this month', prev: 'last month' },
}

// Coaching content: instructions and suggestions only. No health statistics (see docs/health-claims.md).
const TIPS = [
  { title: 'Chin tucks', body: 'Sit tall, glide your head straight back as if making a double chin, hold for 5 seconds, then release. Repeat 5 times.' },
  { title: 'Doorway chest stretch', body: 'Rest your forearm on a doorframe, step through gently until you feel a stretch across your chest, and hold 20–30 seconds each side.' },
  { title: 'Stand up regularly', body: 'A common suggestion is to stand and move every 30–45 minutes. Sitwise nudges you when you have been seated a while.' },
]

export default function Analytics() {
  const [view, setView] = useState<View>('posture')
  const [range, setRange] = useState<Range>('week')
  const m = usePoll(() => api<Metrics>(`/metrics?range=${range}&tzOffsetMin=${tzOffsetMin()}`), 15000, [range])
  const d = m.data
  const stale = !d || d.range !== range // hold the previous render, dimmed, while refetching

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold tracking-tight text-ink">Analytics</h1>
        {/* one filter row above everything it scopes */}
        <div className="flex flex-wrap gap-2">
          <Segmented label="View" value={view} options={VIEWS} onChange={setView} />
          {view === 'posture' && <Segmented label="Time range" value={range} options={RANGES} onChange={setRange} />}
        </div>
      </div>

      {view === 'pain' && (
        <div className="space-y-4">
          <PainInsights />
          <EvidenceMeter />
          <PopulationContext />
        </div>
      )}

      {view === 'posture' && m.error && <Banner tone="error">{m.error.message}</Banner>}
      {view === 'posture' && !d && !m.error && <p className="text-ink-2">Loading…</p>}

      {view === 'posture' && d && (
        <div className={cx('space-y-4 transition-opacity', stale && 'opacity-60')}>
          <div className="grid gap-4 md:grid-cols-5">
            <ScoreCard d={d} range={range} className="md:col-span-3" />
            <OutlookCard d={d} className="md:col-span-2" onEvidence={() => setView('pain')} />
          </div>

          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Stat label="Seated time" value={formatMinutes(d.summary.seatedSec)} hint={`${pct(d.summary.goodPct)} not slouching`} />
            <Stat label="Slouch alerts" value={d.summary.slouchEvents} hint={d.summary.slouchEventsPerHour != null ? `${d.summary.slouchEventsPerHour} per seated hour` : undefined} />
            <Stat label="Longest good streak" value={formatMinutes(d.summary.longestGoodStreakSec)} hint="without slouching" />
            <Stat label="Time to recover" value={d.summary.avgRecoverySec != null ? formatDuration(d.summary.avgRecoverySec) : '–'} hint="average, after a nudge" />
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <GoalCard d={d} range={range} />
            <StreakCard d={d} />
          </div>

          {range === 'day' ? (
            <Card>
              <CardTitle hint="today">Session timeline</CardTitle>
              <Timeline segments={d.timeline} />
            </Card>
          ) : (
            <Card>
              <CardTitle hint="posture score per day">Trend</CardTitle>
              <TrendChart daily={d.daily} goal={d.outlook.thresholdPct} />
            </Card>
          )}

          <Card>
            <CardTitle hint="by weekday and hour">When you slouch</CardTitle>
            <Heatmap cells={d.heatmap} />
          </Card>

          <section aria-labelledby="tips">
            <h2 id="tips" className="mb-2 text-base font-semibold text-ink">
              Coaching tips
            </h2>
            <div className="grid gap-3 md:grid-cols-3">
              {TIPS.map((t) => (
                <div key={t.title} className="rounded-2xl border border-line bg-surface p-4">
                  <div className="font-medium text-ink">{t.title}</div>
                  <p className="mt-1 text-sm text-ink-2">{t.body}</p>
                </div>
              ))}
            </div>
          </section>
        </div>
      )}
    </div>
  )
}

function ScoreCard({ d, range, className }: { d: Metrics; range: Range; className?: string }) {
  const score = d.summary.score
  const prev = d.previous.score
  const delta = score != null && prev != null ? score - prev : null
  return (
    <Card className={className}>
      <div className="text-sm text-ink-2">Posture score · {PERIOD[range].now}</div>
      <div className="mt-1 flex items-baseline gap-2">
        {/* the hero figure: one per view, same sans, proportional figures */}
        <span className="text-7xl font-semibold tracking-tight text-ink">{score ?? '–'}</span>
        <span className="text-xl text-ink-2">/ 100</span>
      </div>
      {delta != null && (
        <div className={cx('mt-1 flex items-center gap-1 text-sm font-medium', delta >= 0 ? 'text-good-ink' : 'text-ink-2')}>
          <span aria-hidden>{delta >= 0 ? '▲' : '▼'}</span>
          {Math.abs(delta)} {delta >= 0 ? 'up' : 'down'} vs {PERIOD[range].prev}
        </div>
      )}
      <p className="mt-3 text-xs text-ink-2">
        How it's scored: the share of your seated time that you weren't slouching. Short lapses inside your grace period aren't penalised, and time away from the desk doesn't count.
      </p>
    </Card>
  )
}

function OutlookCard({ d, className, onEvidence }: { d: Metrics; className?: string; onEvidence: () => void }) {
  const s = d.outlook.status
  return (
    <Card className={className}>
      <CardTitle>Outlook</CardTitle>
      {s === 'on_track' && (
        <div className="flex gap-3">
          <span className="text-good-ink"><StateIcon state="GOOD" className="h-6 w-6" /></span>
          <div>
            <div className="font-semibold text-ink">You're on track to be healthy!</div>
            <p className="mt-1 text-sm text-ink-2">Your score is at or above {d.outlook.thresholdPct}. Keep up the habit.</p>
          </div>
        </div>
      )}
      {s === 'at_risk' && (
        <div className="flex gap-3">
          <span className="text-ink"><StateIcon state="DEVIATING" className="h-6 w-6" /></span>
          <div>
            <div className="font-semibold text-ink">Room to improve</div>
            <p className="mt-1 text-sm text-ink-2">
              Poor sitting posture is linked with neck discomfort in some studies, but research hasn't shown that it causes pain. Moving regularly is still a good habit.
            </p>
          </div>
        </div>
      )}
      {s === 'no_data' && <p className="text-sm text-ink-2">Sit with Sitwise running for a bit and your outlook will show up here.</p>}
      {s !== 'no_data' && (
        <button type="button" onClick={onEvidence} className="mt-3 text-sm font-medium text-accent underline">
          What does the research say?
        </button>
      )}
      <p className="mt-3 border-t border-line pt-3 text-xs text-ink-2">
        Illustrative and educational only. Not medical advice. Talk to a clinician about pain or health concerns.
      </p>
    </Card>
  )
}

function GoalCard({ d, range }: { d: Metrics; range: Range }) {
  const { currentPct, previousPct, targetPct } = d.goal
  return (
    <Card>
      <CardTitle>Your goal</CardTitle>
      <div className="text-ink">
        <span className="font-medium capitalize">{PERIOD[range].now}</span>:{' '}
        {previousPct != null ? (
          <>
            {Math.round(previousPct)}% → <span className="font-semibold">{targetPct}%</span> not slouching
          </>
        ) : (
          <>
            aim for <span className="font-semibold">{targetPct}%</span> not slouching
          </>
        )}
      </div>
      <div className="mt-3">
        <Meter value={currentPct ?? 0} max={targetPct} label={`Progress toward ${targetPct}% good posture`} />
      </div>
      <p className="mt-2 text-sm text-ink-2">
        {currentPct == null ? 'No seated time yet.' : currentPct >= targetPct ? `Goal reached at ${Math.round(currentPct)}%. Nice work.` : `${Math.round(currentPct)}% so far. ${Math.ceil(targetPct - currentPct)} points to go.`}
      </p>
    </Card>
  )
}

function StreakCard({ d }: { d: Metrics }) {
  const n = d.dayStreak
  return (
    <Card>
      <CardTitle>Streak</CardTitle>
      <div className="flex items-baseline gap-2">
        <span className="text-5xl font-semibold tracking-tight text-ink">{n}</span>
        <span className="text-ink-2">{n === 1 ? 'day' : 'days'} at {d.outlook.thresholdPct}%+</span>
      </div>
      <p className="mt-2 text-sm text-ink-2">
        {n === 0 ? `Finish a day at ${d.outlook.thresholdPct}% or better to start a streak.` : n < 3 ? 'Nice start. Keep it going.' : n < 7 ? 'You are building a real habit.' : 'A full week of good habits.'}
      </p>
    </Card>
  )
}
