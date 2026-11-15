import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { CoachPack, FatigueBucket } from '../../types'
import { TableView } from '../ui'

const axisTick = { fill: 'var(--muted)', fontSize: 12 }

function TipBox({ title, value, unit }: { title: string; value: string; unit: string }) {
  return (
    <div className="rounded-lg border border-line bg-surface px-3 py-2 text-sm shadow-md">
      <div className="text-xs text-ink-2">{title}</div>
      <div className="mt-1 flex items-center gap-2">
        <span className="inline-block h-0.5 w-3 rounded" style={{ background: 'var(--series-1)' }} />
        <span className="font-semibold text-ink">{value}</span>
        <span className="text-ink-2">{unit}</span>
      </div>
    </div>
  )
}

/** Slouch share by minutes since sitting down. One series (slot 1), 2px line, ringed dots, the person's own
 *  "slip point" marked with a hairline, a tooltip, and a table twin. */
export function FatigueChart({ buckets, onsetMin }: { buckets: FatigueBucket[]; onsetMin: number | null }) {
  const rows = buckets.map((b) => ({ label: b.minTo == null ? `${b.minFrom}+` : String(b.minFrom), from: b.minFrom, to: b.minTo, slouchPct: b.slouchPct, seatedMin: b.seatedMin }))
  if (rows.filter((r) => r.slouchPct != null).length < 3) return <p className="py-6 text-center text-sm text-ink-2">Not enough long sits yet to draw your fatigue curve.</p>
  return (
    <div>
      <div role="img" aria-label="Slouching share by minutes since you sat down">
        <ResponsiveContainer width="100%" height={230}>
          <LineChart data={rows} margin={{ top: 16, right: 20, bottom: 24, left: 0 }}>
            <CartesianGrid vertical={false} stroke="var(--line)" strokeWidth={1} />
            <XAxis dataKey="label" tickLine={false} axisLine={{ stroke: 'var(--axis)' }} tick={axisTick} label={{ value: 'Minutes since you sat down', position: 'insideBottom', offset: -14, fill: 'var(--muted)', fontSize: 12 }} />
            <YAxis tickFormatter={(v: number) => `${v}%`} tickLine={false} axisLine={false} width={44} tick={axisTick} domain={[0, 'auto']} />
            {onsetMin != null && (
              <ReferenceLine x={String(onsetMin)} stroke="var(--axis)" strokeWidth={1} label={{ value: `slips ~${onsetMin} min`, position: 'top', fill: 'var(--ink-2)', fontSize: 11 }} />
            )}
            <Tooltip
              cursor={{ stroke: 'var(--axis)', strokeWidth: 1 }}
              content={(p) => {
                const r = p.payload?.[0]?.payload as (typeof rows)[number] | undefined
                if (!p.active || !r) return null
                return <TipBox title={`${r.from}${r.to == null ? '+' : `–${r.to}`} minutes in · ${r.seatedMin} min of data`} value={r.slouchPct == null ? 'not enough data' : `${Math.round(r.slouchPct)}%`} unit="slouching" />
              }}
            />
            <Line type="monotone" dataKey="slouchPct" stroke="var(--series-1)" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" connectNulls isAnimationActive={false}
              dot={{ r: 4, fill: 'var(--series-1)', stroke: 'var(--surface)', strokeWidth: 2 }} activeDot={{ r: 5, fill: 'var(--series-1)', stroke: 'var(--surface)', strokeWidth: 2 }} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <TableView caption="Slouching share by minutes since sitting down" head={['Minutes in', 'Slouching', 'Data']}
        rows={rows.map((r) => [`${r.from}${r.to == null ? '+' : `–${r.to}`}`, r.slouchPct == null ? 'not enough data' : `${Math.round(r.slouchPct)}%`, `${r.seatedMin} min`])} />
    </div>
  )
}

/** Average seconds to sit back up after a nudge, per week (oldest first). */
export function RecoveryChart({ trend }: { trend: CoachPack['coaching']['recoveryTrend'] }) {
  if (trend.length < 2) return <p className="py-6 text-center text-sm text-ink-2">Not enough nudges across weeks yet to show a trend.</p>
  const rows = trend.map((t) => ({ label: t.weeksAgo === 0 ? 'this week' : `${t.weeksAgo}w ago`, sec: t.avgRecoverySec, n: t.n }))
  return (
    <div>
      <div role="img" aria-label="Average seconds to sit back up after a nudge, by week">
        <ResponsiveContainer width="100%" height={200}>
          <LineChart data={rows} margin={{ top: 12, right: 20, bottom: 4, left: 0 }}>
            <CartesianGrid vertical={false} stroke="var(--line)" strokeWidth={1} />
            <XAxis dataKey="label" tickLine={false} axisLine={{ stroke: 'var(--axis)' }} tick={axisTick} interval="preserveStartEnd" />
            <YAxis tickFormatter={(v: number) => `${v}s`} tickLine={false} axisLine={false} width={44} tick={axisTick} domain={[0, 'auto']} />
            <Tooltip cursor={{ stroke: 'var(--axis)', strokeWidth: 1 }} content={(p) => {
              const r = p.payload?.[0]?.payload as (typeof rows)[number] | undefined
              return p.active && r ? <TipBox title={`${r.label} · ${r.n} nudges`} value={`${Math.round(r.sec)}s`} unit="to sit back up" /> : null
            }} />
            <Line type="monotone" dataKey="sec" stroke="var(--series-1)" strokeWidth={2} isAnimationActive={false}
              dot={{ r: 4, fill: 'var(--series-1)', stroke: 'var(--surface)', strokeWidth: 2 }} activeDot={{ r: 5, fill: 'var(--series-1)', stroke: 'var(--surface)', strokeWidth: 2 }} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <TableView caption="Average recovery time after a nudge, by week" head={['Week', 'Seconds to sit up', 'Nudges']} rows={rows.map((r) => [r.label, Math.round(r.sec), r.n])} />
    </div>
  )
}

/** Thin horizontal bars (max 24px, 4px rounded data end, one baseline) for "fixed within 30 s", with the
 *  value at the tip. A group with too few nudges says so instead of drawing a misleading bar. */
export function ResponseBars({ title, rows }: { title: string; rows: { label: string; n: number; pct: number | null }[] }) {
  return (
    <div>
      <div className="mb-2 text-sm font-medium text-ink">{title}</div>
      <ul className="space-y-2">
        {rows.map((r) => (
          <li key={r.label} className="grid grid-cols-[5.5rem_1fr_auto] items-center gap-3 text-sm" title={r.pct == null ? `${r.label}: not enough nudges` : `${r.label}: ${Math.round(r.pct)}% within 30 s (${r.n} nudges)`}>
            <span className="text-ink-2">{r.label}</span>
            <span className="h-4 rounded-r-[4px]" style={{ background: 'var(--seq-1)' }}>
              {r.pct != null && <span className="block h-full rounded-r-[4px] bg-accent" style={{ width: `${Math.max(2, Math.min(100, r.pct))}%` }} />}
            </span>
            <span className="w-24 text-right tabular-nums text-ink">{r.pct == null ? <span className="text-ink-2">too few</span> : `${Math.round(r.pct)}%`} <span className="text-xs text-ink-2">n={r.n}</span></span>
          </li>
        ))}
      </ul>
    </div>
  )
}

const PARTS = [
  { key: 'headForward', label: 'Head forward', color: 'var(--series-1)' },
  { key: 'trunkLean', label: 'Upper body leaning', color: 'var(--series-2)' },
  { key: 'other', label: 'Neither clearly', color: 'var(--series-3)' },
] as const

/** One whole (all your slouching) split into its parts: a tall segmented bar with the share printed inside
 *  each block that has room, a legend that names the parts, and a table twin. 2px gaps, 4px corners. */
export function FingerprintBar({ f }: { f: NonNullable<CoachPack['patterns']['fingerprint']> }) {
  const vals = { headForward: f.headForwardPct, trunkLean: f.trunkLeanPct, other: f.otherPct }
  return (
    <div>
      <div role="img" aria-label={`How you slouch: ${PARTS.map((p) => `${p.label} ${Math.round(vals[p.key])}%`).join(', ')}`} className="flex h-7 gap-0.5">
        {PARTS.map((p) =>
          vals[p.key] > 0 ? (
            <div key={p.key} className="flex items-center overflow-hidden rounded-[4px] px-2 text-xs font-semibold text-white" style={{ width: `${vals[p.key]}%`, background: p.color }} title={`${p.label}: ${Math.round(vals[p.key])}%`}>
              {vals[p.key] >= 14 ? `${Math.round(vals[p.key])}%` : ''}
            </div>
          ) : null,
        )}
      </div>
      <ul className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-sm text-ink-2">
        {PARTS.map((p) => (
          <li key={p.key} className="flex items-center gap-1.5">
            <span className="inline-block h-3 w-3 rounded-[3px]" style={{ background: p.color }} aria-hidden />
            {p.label} <span className="text-ink">{Math.round(vals[p.key])}%</span>
          </li>
        ))}
      </ul>
      <TableView caption="Share of your slouching by type" head={['Type', 'Share of slouching']} rows={PARTS.map((p) => [p.label, `${Math.round(vals[p.key])}%`])} />
    </div>
  )
}
