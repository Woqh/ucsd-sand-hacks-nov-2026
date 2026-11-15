import { useState } from 'react'
import { CartesianGrid, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '../api'
import { formatAgo } from '../format'
import { usePoll } from '../hooks'
import type { PainInsight, PainPoint } from '../types'
import { Banner, Button, Card, CardTitle, TableView } from './ui'

const AREAS: { value: string; label: string }[] = [
  { value: '', label: 'Not specific' },
  { value: 'neck', label: 'Neck' },
  { value: 'upper_back', label: 'Upper back' },
  { value: 'lower_back', label: 'Lower back' },
  { value: 'shoulders', label: 'Shoulders' },
  { value: 'other', label: 'Somewhere else' },
]
const EARLY_WEEKS = 8 // below this many weeks, describe any pattern as tentative
const areaLabel = (a: string | null) => AREAS.find((x) => x.value === (a ?? ''))?.label ?? '–'
const day = (t: number) => new Date(t).toLocaleDateString([], { month: 'short', day: 'numeric' })

/** "Pain vs slouching": the honest version of a consequence outlook. We don't predict anything. We
 *  show whether, in THIS person's own weeks, more slouching lined up with more pain, with plain
 *  hedging that it's a pattern and not a cause. */
export default function PainInsights() {
  const insight = usePoll(() => api<PainInsight>('/insights/pain'), 0)
  const d = insight.data

  return (
    <div className="space-y-4">
      <CheckIn insight={d} onSaved={insight.refresh} />
      {insight.error && <Banner tone="error">{insight.error.message}</Banner>}
      {d && <Comparison insight={d} />}
    </div>
  )
}

function CheckIn({ insight, onSaved }: { insight: PainInsight | null; onSaved: () => void }) {
  const [pain, setPain] = useState(3)
  const [area, setArea] = useState('')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<string | null>(null)
  const [err, setErr] = useState<string | null>(null)

  async function save() {
    setBusy(true)
    setErr(null)
    setMsg(null)
    try {
      await api('/checkins', { method: 'POST', body: { pain, area: area || undefined } })
      setMsg('Saved. Thanks for checking in.')
      onSaved()
    } catch (e) {
      setErr((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const last = insight?.lastCheckinAt
  const ageSec = last ? (Date.now() - last) / 1000 : null
  return (
    <Card>
      <CardTitle hint={last ? `last check-in ${formatAgo(ageSec)}` : 'about 10 seconds, once a week'}>Weekly check-in</CardTitle>
      <label className="block">
        <span className="font-medium text-ink">How have your neck and back felt over the past 7 days?</span>
        <div className="mt-3 flex items-center gap-3">
          <span className="w-16 text-xs text-ink-2">0 · no pain</span>
          <input type="range" min={0} max={10} step={1} value={pain} onChange={(e) => setPain(Number(e.target.value))} className="h-8 flex-1" aria-valuetext={`${pain} out of 10`} />
          <span className="w-20 text-right text-xs text-ink-2">10 · worst</span>
        </div>
        <div className="mt-1 text-center text-3xl font-semibold tracking-tight text-ink">{pain}</div>
      </label>
      <label className="mt-3 flex flex-wrap items-center gap-3 text-sm text-ink-2">
        Where?
        <select value={area} onChange={(e) => setArea(e.target.value)} className="min-h-11 rounded-lg border border-axis bg-surface px-3 text-ink">
          {AREAS.map((a) => (
            <option key={a.value} value={a.value}>
              {a.label}
            </option>
          ))}
        </select>
      </label>
      <div className="mt-4 flex flex-wrap items-center gap-3">
        <Button onClick={save} disabled={busy}>
          Save check-in
        </Button>
        {msg && (
          <span className="text-sm text-good-ink" role="status">
            {msg}
          </span>
        )}
      </div>
      {err && <div className="mt-3"><Banner tone="error">{err}</Banner></div>}
    </Card>
  )
}

function copyFor(c: PainInsight['correlation']): string {
  if (!c.enough) return `You have ${c.n} of the ${c.needed} weekly check-ins needed to compare your pain with your slouching. Keep checking in once a week.`
  if (c.strength === 'none') return `So far, ${c.n} weeks of your data show no clear pattern between how much you slouched and how your neck and back felt.`
  // With only a handful of weeks even a strong-looking pattern is shaky, so say so up front.
  const early = c.n < EARLY_WEEKS
  const size = early ? 'tentative' : c.strength === 'stronger' ? 'fairly clear' : 'modest'
  if (c.direction === 'positive')
    return `In your ${c.n} weeks of data, weeks with more slouching tended to be weeks with more pain (a ${size} pattern${early ? `; with under ${EARLY_WEEKS} weeks it's too early to be sure` : ''}).`
  return `In your ${c.n} weeks of data, weeks with more slouching tended to have less pain. That's the opposite of what you might expect, and with this little data it's most likely chance.`
}

function Comparison({ insight }: { insight: PainInsight }) {
  const used = insight.points.filter((p) => p.used && p.slouchPct != null)
  const c = insight.correlation
  const xMax = Math.max(20, Math.ceil(Math.max(0, ...used.map((p) => p.slouchPct ?? 0)) / 10) * 10)

  if (insight.points.length === 0) {
    return (
      <Card>
        <CardTitle>Your pain vs your slouching</CardTitle>
        <p className="text-sm text-ink-2">Once you've checked in, this compares each week's rating with how much you slouched that week, using only your own data.</p>
      </Card>
    )
  }

  return (
    <Card>
      <CardTitle hint="your own data only">Your pain vs your slouching</CardTitle>
      <p className="mb-3 text-ink">{copyFor(c)}</p>
      {used.length >= 3 && <Scatter3 points={used} xMax={xMax} />}
      <div className="mt-3 rounded-xl bg-line/40 p-3 text-sm text-ink-2">
        <strong className="text-ink">Read this carefully.</strong> It's a pattern in your own weeks, not proof that slouching causes pain. With only {c.n} {c.n === 1 ? 'week' : 'weeks'} it could easily be coincidence, and pain has many causes. If pain is ongoing or worrying, talk to a clinician.
        {c.rho != null && <span className="block pt-1 text-xs">Rank correlation (Spearman): {c.rho}, from {c.n} weeks.</span>}
      </div>
      <TableView
        caption="Weekly pain check-ins and slouching in the 7 days before each"
        head={['Check-in', 'Pain (0–10)', 'Where', 'Slouching that week', 'In comparison']}
        rows={[...insight.points].reverse().map((p) => [day(p.t), p.pain, areaLabel(p.area), p.slouchPct == null ? 'not enough data' : `${Math.round(p.slouchPct)}%`, p.used ? 'yes' : 'no'])}
      />
    </Card>
  )
}

/** One series, so slot-1 colour and no legend box (the card title names it). 8px dots with a 2px
 *  surface ring inside a 28px transparent hit target, a hairline grid, and a table twin below. */
function Scatter3({ points, xMax }: { points: PainPoint[]; xMax: number }) {
  const data = points.map((p) => ({ ...p, x: p.slouchPct as number }))
  return (
    <div role="img" aria-label={`Scatter plot of weekly pain (0 to 10) against the percentage of seated time slouching, ${points.length} weeks`}>
      <ResponsiveContainer width="100%" height={260}>
        <ScatterChart margin={{ top: 12, right: 20, bottom: 28, left: 0 }}>
          <CartesianGrid stroke="var(--line)" strokeWidth={1} />
          <XAxis
            type="number"
            dataKey="x"
            domain={[0, xMax]}
            tickFormatter={(v: number) => `${v}%`}
            tickLine={false}
            axisLine={{ stroke: 'var(--axis)' }}
            tick={{ fill: 'var(--muted)', fontSize: 12 }}
            label={{ value: 'Share of seated time slouching (past 7 days)', position: 'insideBottom', offset: -16, fill: 'var(--muted)', fontSize: 12 }}
          />
          <YAxis
            type="number"
            dataKey="pain"
            domain={[0, 10]}
            ticks={[0, 2, 4, 6, 8, 10]}
            width={40}
            tickLine={false}
            axisLine={false}
            tick={{ fill: 'var(--muted)', fontSize: 12 }}
            label={{ value: 'Pain', angle: -90, position: 'insideLeft', fill: 'var(--muted)', fontSize: 12 }}
          />
          <Tooltip
            cursor={{ stroke: 'var(--axis)', strokeWidth: 1 }}
            content={(p) => {
              const row = p.payload?.[0]?.payload as (PainPoint & { x: number }) | undefined
              if (!p.active || !row) return null
              return (
                <div className="rounded-lg border border-line bg-surface px-3 py-2 text-sm shadow-md">
                  <div className="text-xs text-ink-2">Week ending {day(row.t)}</div>
                  <div className="mt-1 flex items-center gap-2">
                    <span className="inline-block h-0.5 w-3 rounded" style={{ background: 'var(--series-1)' }} />
                    <span className="font-semibold text-ink">pain {row.pain}</span>
                    <span className="text-ink-2">· {Math.round(row.x)}% slouching</span>
                  </div>
                </div>
              )
            }}
          />
          <Scatter
            data={data}
            isAnimationActive={false}
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            shape={(p: any) => (
              <g>
                <circle cx={p.cx} cy={p.cy} r={14} fill="transparent" />
                <circle cx={p.cx} cy={p.cy} r={6} fill="var(--surface)" />
                <circle cx={p.cx} cy={p.cy} r={4} fill="var(--series-1)" />
              </g>
            )}
          />
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  )
}
