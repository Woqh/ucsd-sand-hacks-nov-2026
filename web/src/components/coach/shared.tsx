import type { ReactNode } from 'react'
import { Card, CardTitle } from '../ui'

export { dayName, hour12 } from '../../coach/localAnalysis'

export function Section({ title, hint, children }: { title: string; hint?: ReactNode; children: ReactNode }) {
  return (
    <Card>
      <CardTitle hint={hint}>{title}</CardTitle>
      {children}
    </Card>
  )
}

export function Fact({ label, value, hint }: { label: string; value: ReactNode; hint?: ReactNode }) {
  return (
    <div className="rounded-xl bg-line/40 p-3">
      <div className="text-xs text-ink-2">{label}</div>
      <div className="mt-0.5 text-xl font-semibold tracking-tight text-ink">{value}</div>
      {hint && <div className="mt-0.5 text-xs text-ink-2">{hint}</div>}
    </div>
  )
}

export const num = (v: number | null | undefined, unit = ''): string => (v == null ? '–' : `${Math.round(v)}${unit}`)

/** Exactly what the person is agreeing to before anything is sent to Gemini. */
export function ConsentBox({ checked, onChange, children }: { checked: boolean; onChange: (v: boolean) => void; children: ReactNode }) {
  return (
    <label className="flex items-start gap-3 rounded-xl border border-line p-3 text-sm text-ink-2">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} className="mt-1 h-5 w-5 shrink-0" />
      <span>{children}</span>
    </label>
  )
}

export function NotEnough({ children }: { children: ReactNode }) {
  return <p className="rounded-xl bg-line/40 p-3 text-sm text-ink-2">{children}</p>
}
