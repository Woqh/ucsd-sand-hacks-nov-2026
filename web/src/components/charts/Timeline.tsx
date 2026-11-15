import { useRef, useState } from 'react'
import { formatClock, formatDuration } from '../../format'
import type { PostureState, TimelineSegment } from '../../types'
import { STATE_META, StateIcon, TableView } from '../ui'

const FILL: Record<PostureState, string> = {
  GOOD: 'var(--st-good)',
  DEVIATING: 'var(--st-warn)',
  SLOUCHING: 'var(--st-crit)',
  AWAY: 'var(--away)',
}
const BAR_H = 24 // tall segmented bars cap at 28px

/** Today as one strip: status-colored segments (icon + label legend, hover/readout, table view),
 *  1px surface gaps between touching segments, AWAY drawn as a thin rule (no posture data). */
export default function Timeline({ segments }: { segments: TimelineSegment[] }) {
  const ref = useRef<HTMLDivElement>(null)
  const [hover, setHover] = useState<{ seg: TimelineSegment; x: number } | null>(null)

  const seated = segments.filter((s) => s.state !== 'AWAY')
  if (!seated.length) return <p className="py-8 text-center text-sm text-ink-2">No seated time recorded today yet.</p>

  const start = seated[0].start
  const end = seated[seated.length - 1].end
  const span = Math.max(1, end - start)
  const win = segments.filter((s) => s.end > start && s.start < end)
  const pos = (t: number) => ((t - start) / span) * 100

  // hour ticks in local time (every 2h when the window is long)
  const stepH = span > 8 * 3600_000 ? 2 : 1
  const ticks: number[] = []
  const d = new Date(start)
  d.setMinutes(0, 0, 0)
  if (d.getTime() < start) d.setHours(d.getHours() + 1)
  for (; d.getTime() < end; d.setHours(d.getHours() + stepH)) ticks.push(d.getTime())

  function onMove(e: React.PointerEvent) {
    const r = ref.current!.getBoundingClientRect()
    const x = Math.min(Math.max(e.clientX - r.left, 0), r.width)
    const t = start + (x / r.width) * span
    // nearest seated segment: the crosshair finds the X, so tiny segments stay reachable
    const seg = seated.reduce((best, s) => {
      const dist = t < s.start ? s.start - t : t > s.end ? t - s.end : 0
      const bd = t < best.start ? best.start - t : t > best.end ? t - best.end : 0
      return dist < bd ? s : best
    }, seated[0])
    setHover({ seg, x })
  }

  const rows = seated.filter((s) => s.end - s.start >= 10_000)

  return (
    <div>
      <div
        ref={ref}
        className="relative touch-pan-y"
        onPointerMove={onMove}
        onPointerLeave={() => setHover(null)}
        role="img"
        aria-label={`Posture timeline from ${formatClock(start)} to ${formatClock(end)}. Use the table view for exact values.`}
      >
        <div className="relative" style={{ height: BAR_H }}>
          {win.map((s, i) => {
            const left = pos(Math.max(s.start, start))
            const width = pos(Math.min(s.end, end)) - left
            const away = s.state === 'AWAY'
            const active = hover?.seg === s
            return (
              <div
                key={i}
                className="absolute rounded-[4px]"
                style={{
                  left: `calc(${left}% + 0.5px)`,
                  width: `max(1.5px, calc(${width}% - 1px))`,
                  top: away ? BAR_H / 2 - 2 : 0,
                  height: away ? 4 : BAR_H,
                  background: FILL[s.state],
                  outline: active ? '2px solid var(--ink)' : undefined,
                  outlineOffset: 1,
                }}
              />
            )
          })}
        </div>
        <div className="relative mt-1 h-5 border-t border-axis">
          {ticks.map((t) => (
            <span key={t} className="absolute -translate-x-1/2 pt-1 text-[11px] text-muted" style={{ left: `${pos(t)}%` }}>
              {new Date(t).toLocaleTimeString([], { hour: 'numeric' })}
            </span>
          ))}
        </div>

        {hover && (
          <div
            className="pointer-events-none absolute -top-2 z-10 -translate-y-full whitespace-nowrap rounded-lg border border-line bg-surface px-3 py-2 text-sm shadow-md"
            style={{ left: `clamp(70px, ${hover.x}px, calc(100% - 70px))`, transform: 'translate(-50%, -100%)' }}
          >
            <div className="font-semibold text-ink">{STATE_META[hover.seg.state].label}</div>
            <div className="text-xs text-ink-2">
              {formatClock(hover.seg.start)} – {formatClock(hover.seg.end)} · {formatDuration((hover.seg.end - hover.seg.start) / 1000)}
            </div>
          </div>
        )}
      </div>

      <ul className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-sm text-ink-2">
        {(['GOOD', 'DEVIATING', 'SLOUCHING', 'AWAY'] as PostureState[]).map((st) => (
          <li key={st} className="flex items-center gap-1.5">
            <span className="inline-block h-3 w-3 rounded-[3px]" style={{ background: FILL[st] }} aria-hidden />
            <StateIcon state={st} className="h-3.5 w-3.5" />
            {STATE_META[st].label}
          </li>
        ))}
      </ul>

      <TableView
        caption="Posture states today (segments of 10 seconds or more)"
        head={['From', 'To', 'State', 'Length']}
        rows={rows.map((s) => [formatClock(s.start), formatClock(s.end), STATE_META[s.state].label, formatDuration((s.end - s.start) / 1000)])}
      />
    </div>
  )
}
