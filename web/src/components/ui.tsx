import type { ReactNode } from 'react'
import type { PostureState } from '../types'

export const cx = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(' ')

/* ---------- posture state: color + icon + label, never color alone ---------- */

export const STATE_META: Record<PostureState, { label: string; blurb: string; text: string; bg: string; dot: string }> = {
  GOOD: { label: 'Good posture', blurb: 'Matching your goal posture', text: 'text-good-ink', bg: 'bg-good/10', dot: 'bg-good' },
  DEVIATING: { label: 'Drifting', blurb: 'Off your goal posture, within your grace period', text: 'text-ink', bg: 'bg-warn/15', dot: 'bg-warn' },
  SLOUCHING: { label: 'Slouching', blurb: 'Past your threshold. Time to sit up', text: 'text-crit', bg: 'bg-crit/10', dot: 'bg-crit' },
  AWAY: { label: 'Away', blurb: 'No one at the desk', text: 'text-ink-2', bg: 'bg-line/60', dot: 'bg-away' },
}

export function StateIcon({ state, className = 'h-6 w-6' }: { state: PostureState; className?: string }) {
  const common = { className, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 2, strokeLinecap: 'round', strokeLinejoin: 'round', 'aria-hidden': true } as const
  switch (state) {
    case 'GOOD':
      return (
        <svg {...common}>
          <circle cx="12" cy="12" r="9" />
          <path d="m8 12.500 2.800 2.800L16.500 9.500" />
        </svg>
      )
    case 'DEVIATING':
      return (
        <svg {...common}>
          <path d="M7 3h10M7 21h10M8 3c0 5 8 5 8 9s-8 4-8 9M16 3c0 5-8 5-8 9s8 4 8 9" />
        </svg>
      )
    case 'SLOUCHING':
      return (
        <svg {...common}>
          <path d="M12 3 2.500 20h19L12 3Z" />
          <path d="M12 10v4.500M12 17.500v.01" />
        </svg>
      )
    default:
      return (
        <svg {...common}>
          <path d="M20 14.500A8 8 0 0 1 9.500 4 8 8 0 1 0 20 14.500Z" />
        </svg>
      )
  }
}

export function StatePill({ state }: { state: PostureState }) {
  const m = STATE_META[state]
  return (
    <span className={cx('inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-sm font-medium', m.bg, m.text)}>
      <StateIcon state={state} className="h-4 w-4" />
      {m.label}
    </span>
  )
}

/* ---------- layout bits ---------- */

export function Card({ children, className }: { children: ReactNode; className?: string }) {
  return <section className={cx('rounded-2xl border border-line bg-surface p-4 sm:p-5', className)}>{children}</section>
}

export function CardTitle({ children, hint }: { children: ReactNode; hint?: ReactNode }) {
  return (
    <div className="mb-3 flex items-baseline justify-between gap-3">
      <h2 className="text-base font-semibold text-ink">{children}</h2>
      {hint && <span className="text-xs text-ink-2">{hint}</span>}
    </div>
  )
}

export function Button({
  children,
  onClick,
  variant = 'primary',
  disabled,
  type = 'button',
  className,
}: {
  children: ReactNode
  onClick?: () => void
  variant?: 'primary' | 'secondary' | 'ghost'
  disabled?: boolean
  type?: 'button' | 'submit'
  className?: string
}) {
  const styles = {
    primary: 'bg-ink text-surface hover:opacity-90',
    secondary: 'border border-axis bg-surface text-ink hover:bg-line/50',
    ghost: 'text-ink-2 hover:bg-line/50',
  }[variant]
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={cx('inline-flex min-h-11 items-center justify-center gap-2 rounded-xl px-4 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-50', styles, className)}
    >
      {children}
    </button>
  )
}

export function Banner({ tone = 'info', children }: { tone?: 'info' | 'warn' | 'error'; children: ReactNode }) {
  const t = { info: 'bg-accent/10', warn: 'bg-warn/15', error: 'bg-crit/10' }[tone]
  return (
    <div role={tone === 'error' ? 'alert' : 'status'} className={cx('rounded-xl px-4 py-3 text-sm text-ink', t)}>
      {children}
    </div>
  )
}

/* ---------- numbers ---------- */

export function Stat({ label, value, hint }: { label: string; value: ReactNode; hint?: ReactNode }) {
  return (
    <div className="rounded-2xl border border-line bg-surface p-4">
      <div className="text-sm text-ink-2">{label}</div>
      {/* proportional figures for big standalone numbers (tabular-nums is for aligned columns) */}
      <div className="mt-1 text-3xl font-semibold tracking-tight text-ink">{value}</div>
      {hint && <div className="mt-1 text-xs text-ink-2">{hint}</div>}
    </div>
  )
}

/** Meter: the unfilled track is a lighter step of the same ramp. */
export function Meter({ value, max = 100, label }: { value: number; max?: number; label: string }) {
  const w = Math.max(0, Math.min(100, (value / max) * 100))
  return (
    <div
      role="meter"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={max}
      aria-valuenow={Math.round(value)}
      className="h-2 w-full overflow-hidden rounded-full"
      style={{ background: 'var(--seq-1)' }}
    >
      <div className="h-full rounded-full bg-accent transition-[width] duration-500" style={{ width: `${w}%` }} />
    </div>
  )
}

/* ---------- controls ---------- */

export function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={() => onChange(!checked)}
      className={cx('relative h-7 w-12 shrink-0 rounded-full transition', checked ? 'bg-accent' : 'bg-axis')}
    >
      <span className={cx('absolute top-0.5 h-6 w-6 rounded-full bg-white shadow transition-all', checked ? 'left-[22px]' : 'left-0.5')} />
    </button>
  )
}

export function Segmented<T extends string>({
  value,
  options,
  onChange,
  label,
}: {
  value: T
  options: { value: T; label: string }[]
  onChange: (v: T) => void
  label: string
}) {
  return (
    <div role="group" aria-label={label} className="inline-flex rounded-xl border border-line bg-surface p-1">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          aria-pressed={o.value === value}
          onClick={() => onChange(o.value)}
          className={cx('min-h-9 rounded-lg px-4 text-sm font-medium transition', o.value === value ? 'bg-ink text-surface' : 'text-ink-2 hover:bg-line/50')}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

/** Every chart has a table-view twin so no value is reachable only through a tooltip or color. */
export function TableView({ caption, head, rows }: { caption: string; head: string[]; rows: (string | number)[][] }) {
  return (
    <details className="mt-3 text-sm">
      <summary className="cursor-pointer text-ink-2 hover:text-ink">View as table</summary>
      <div className="mt-2 max-h-64 overflow-auto rounded-lg border border-line">
        <table className="w-full text-left text-xs">
          <caption className="sr-only">{caption}</caption>
          <thead className="sticky top-0 bg-surface text-ink-2">
            <tr>
              {head.map((h) => (
                <th key={h} scope="col" className="px-3 py-2 font-medium">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i} className="border-t border-line">
                {r.map((c, j) => (
                  <td key={j} className="px-3 py-1.5 tabular-nums text-ink">
                    {c}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  )
}
