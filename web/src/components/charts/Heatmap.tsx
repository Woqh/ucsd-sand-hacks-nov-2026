import { useMemo, useState } from 'react'
import { WEEKDAYS, formatHour, formatMinutes } from '../../format'
import type { HeatCell } from '../../types'
import { TableView } from '../ui'

// Sequential, one hue: the share of seated time spent slouching (darker = more).
// Six classes keep neighbouring steps distinct; the ramp flips its anchor in dark mode (index.css).
const BINS = [
  { max: 10, label: 'under 10%' },
  { max: 20, label: '10–20%' },
  { max: 30, label: '20–30%' },
  { max: 40, label: '30–40%' },
  { max: 55, label: '40–55%' },
  { max: Infinity, label: '55%+' },
]
const binOf = (slouch: number) => BINS.findIndex((b) => slouch < b.max)
const MIN_SEATED_SEC = 60 // fewer seconds than this in an hour-cell is noise

export default function Heatmap({ cells }: { cells: HeatCell[] }) {
  const [tip, setTip] = useState<{ cell: HeatCell; x: number; y: number } | null>(null)
  const byKey = useMemo(() => new Map(cells.filter((c) => c.goodPct != null && c.seatedSec >= MIN_SEATED_SEC).map((c) => [`${c.day}-${c.hour}`, c])), [cells])

  if (!byKey.size) return <p className="py-8 text-center text-sm text-ink-2">No hour-by-hour data in this period yet.</p>

  const hours = [...byKey.values()].map((c) => c.hour)
  const h0 = Math.min(8, ...hours)
  const h1 = Math.max(18, ...hours)
  const cols = Array.from({ length: h1 - h0 + 1 }, (_, i) => h0 + i)

  const show = (cell: HeatCell, el: HTMLElement) => {
    const wrap = el.closest('[data-heat]') as HTMLElement
    const a = el.getBoundingClientRect()
    const b = wrap.getBoundingClientRect()
    setTip({ cell, x: a.left - b.left + a.width / 2, y: a.top - b.top })
  }

  const slouch = (c: HeatCell) => 100 - (c.goodPct ?? 0)

  return (
    <div>
      <div data-heat className="relative" onPointerLeave={() => setTip(null)}>
        <div className="grid gap-[2px]" style={{ gridTemplateColumns: `2.25rem repeat(${cols.length}, minmax(0, 1fr))` }}>
          <div />
          {cols.map((h) => (
            <div key={h} className="text-center text-[10px] leading-4 text-muted">
              {(h - h0) % 2 === 0 ? formatHour(h).replace(' ', '').toLowerCase() : ''}
            </div>
          ))}
          {WEEKDAYS.map((name, day) => (
            <Row key={name} name={name}>
              {cols.map((h) => {
                const c = byKey.get(`${day}-${h}`)
                return c ? (
                  <button
                    key={h}
                    type="button"
                    aria-label={`${name} ${formatHour(h)}: ${Math.round(slouch(c))}% slouching`}
                    className="h-7 rounded-[4px] outline-offset-1 hover:outline-2 hover:outline-ink focus-visible:outline-2"
                    style={{ background: `var(--seq-${binOf(slouch(c)) + 1})` }}
                    onPointerEnter={(e) => show(c, e.currentTarget)}
                    onFocus={(e) => show(c, e.currentTarget)}
                    onBlur={() => setTip(null)}
                  />
                ) : (
                  <div key={h} className="h-7 rounded-[4px] bg-line/50" />
                )
              })}
            </Row>
          ))}
        </div>

        {tip && (
          <div
            className="pointer-events-none absolute z-10 whitespace-nowrap rounded-lg border border-line bg-surface px-3 py-2 text-sm shadow-md"
            style={{ left: `clamp(70px, ${tip.x}px, calc(100% - 70px))`, top: tip.y - 6, transform: 'translate(-50%, -100%)' }}
          >
            <div className="font-semibold text-ink">{Math.round(slouch(tip.cell))}% slouching</div>
            <div className="text-xs text-ink-2">
              {WEEKDAYS[tip.cell.day]} {formatHour(tip.cell.hour)} · {formatMinutes(tip.cell.seatedSec)} seated
            </div>
          </div>
        )}
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-ink-2">
        <span>Share of seated time slouching:</span>
        {BINS.map((b, i) => (
          <span key={b.label} className="flex items-center gap-1.5">
            <span className="inline-block h-3 w-3 rounded-[3px]" style={{ background: `var(--seq-${i + 1})` }} aria-hidden />
            {b.label}
          </span>
        ))}
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-3 w-3 rounded-[3px] bg-line/50" aria-hidden />
          no data
        </span>
      </div>

      <TableView
        caption="Slouching share by weekday and hour"
        head={['Day', 'Hour', 'Slouching', 'Seated']}
        rows={[...byKey.values()].map((c) => [WEEKDAYS[c.day], formatHour(c.hour), `${Math.round(slouch(c))}%`, formatMinutes(c.seatedSec)])}
      />
    </div>
  )
}

function Row({ name, children }: { name: string; children: React.ReactNode }) {
  return (
    <>
      <div className="flex items-center text-xs text-ink-2">{name}</div>
      {children}
    </>
  )
}
