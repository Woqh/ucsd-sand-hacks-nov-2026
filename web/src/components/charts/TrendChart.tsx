import { Area, AreaChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { DailyPoint } from '../../types'
import { TableView } from '../ui'

interface Row {
  label: string
  full: string
  score: number | null
  seated: number
}

const parse = (d: string) => new Date(`${d}T00:00:00`)

/** One series (good-posture score per day), so: slot-1 color, no legend box (the title names it),
 *  2px line, ~10% area wash, hairline solid grid, a ringed end-dot labeled with the latest value. */
export default function TrendChart({ daily, goal }: { daily: DailyPoint[]; goal: number }) {
  const rows: Row[] = daily.map((d) => ({
    label: daily.length <= 7 ? parse(d.date).toLocaleDateString([], { weekday: 'short' }) : parse(d.date).toLocaleDateString([], { month: 'numeric', day: 'numeric' }),
    full: parse(d.date).toLocaleDateString([], { weekday: 'long', month: 'short', day: 'numeric' }),
    score: d.score,
    seated: d.seatedSec,
  }))
  const lastIdx = rows.reduce((acc, r, i) => (r.score != null ? i : acc), -1)
  const have = rows.filter((r) => r.score != null).length

  if (have < 2) {
    return <p className="py-10 text-center text-sm text-ink-2">Not enough days of data yet. Sit with Sitwise running and a trend will appear here.</p>
  }

  const first = rows.find((r) => r.score != null)!
  const last = rows[lastIdx]
  const summary = `Posture score by day, from ${first.score} on ${first.full} to ${last.score} on ${last.full}.`

  return (
    <div>
      <div role="img" aria-label={summary}>
        <ResponsiveContainer width="100%" height={240}>
          <AreaChart data={rows} margin={{ top: 22, right: 20, bottom: 4, left: 0 }}>
            <CartesianGrid vertical={false} stroke="var(--line)" strokeWidth={1} />
            <XAxis dataKey="label" tickLine={false} axisLine={{ stroke: 'var(--axis)' }} tick={{ fill: 'var(--muted)', fontSize: 12 }} interval="preserveStartEnd" minTickGap={20} />
            <YAxis domain={[0, 100]} ticks={[0, 25, 50, 75, 100]} tickFormatter={(v: number) => `${v}%`} tickLine={false} axisLine={false} width={44} tick={{ fill: 'var(--muted)', fontSize: 12 }} />
            <ReferenceLine y={goal} stroke="var(--axis)" strokeWidth={1} label={{ value: `on track ${goal}%`, position: 'insideBottomRight', fill: 'var(--muted)', fontSize: 11 }} />
            <Tooltip
              cursor={{ stroke: 'var(--axis)', strokeWidth: 1 }}
              content={(p) => {
                const row = p.payload?.[0]?.payload as Row | undefined
                if (!p.active || !row) return null
                return (
                  <div className="rounded-lg border border-line bg-surface px-3 py-2 text-sm shadow-md">
                    <div className="text-xs text-ink-2">{row.full}</div>
                    <div className="mt-1 flex items-center gap-2">
                      <span className="inline-block h-0.5 w-3 rounded" style={{ background: 'var(--series-1)' }} />
                      <span className="font-semibold text-ink">{row.score == null ? 'No data' : `${row.score}%`}</span>
                      <span className="text-ink-2">posture score</span>
                    </div>
                  </div>
                )
              }}
            />
            <Area
              type="monotone"
              dataKey="score"
              stroke="var(--series-1)"
              strokeWidth={2}
              strokeLinejoin="round"
              strokeLinecap="round"
              fill="var(--series-1)"
              fillOpacity={0.1}
              connectNulls
              isAnimationActive={false}
              // eslint-disable-next-line @typescript-eslint/no-explicit-any
              dot={(p: any) =>
                p.index === lastIdx ? (
                  <g key="end">
                    <circle cx={p.cx} cy={p.cy} r={6} fill="var(--surface)" />
                    <circle cx={p.cx} cy={p.cy} r={4} fill="var(--series-1)" />
                    <text x={p.cx} y={p.cy - 12} textAnchor="middle" fontSize={12} fontWeight={600} fill="var(--ink)">
                      {p.payload.score}%
                    </text>
                  </g>
                ) : (
                  <g key={`d${p.index}`} />
                )
              }
              activeDot={{ r: 4, fill: 'var(--series-1)', stroke: 'var(--surface)', strokeWidth: 2 }}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
      <TableView
        caption="Posture score per day"
        head={['Day', 'Score', 'Seated']}
        rows={rows.map((r) => [r.full, r.score == null ? '–' : `${r.score}%`, r.seated ? `${Math.round(r.seated / 60)} min` : '–'])}
      />
    </div>
  )
}
