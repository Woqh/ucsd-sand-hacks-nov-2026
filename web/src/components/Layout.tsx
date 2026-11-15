import { useEffect, type ReactNode } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { api, tzOffsetMin } from '../api'
import type { Settings } from '../types'
import { AlertWatcher } from './AlertWatcher'
import { cx } from './ui'

const icon = (d: ReactNode) => (
  <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    {d}
  </svg>
)

const NAV = [
  { to: '/', label: 'Live', end: true, icon: icon(<path d="M3 12h4l3-8 4 16 3-8h4" />) },
  { to: '/analytics', label: 'Analytics', icon: icon(<path d="M4 20V10M10 20V4M16 20v-8M22 20H2" />) },
  { to: '/coach', label: 'Coach', icon: icon(<><circle cx="12" cy="8" r="3.500" /><path d="M5 21c0-4 3-6.500 7-6.500s7 2.500 7 6.500" /></>) },
  { to: '/calibration', label: 'Calibrate', icon: icon(<><circle cx="12" cy="12" r="8" /><circle cx="12" cy="12" r="2.500" /></>) },
  { to: '/camera', label: 'Camera', icon: icon(<><path d="M4 8h3l2-3h6l2 3h3v11H4z" /><circle cx="12" cy="13" r="3.5" /></>) },
  { to: '/settings', label: 'Settings', icon: icon(<><path d="M4 7h10M18 7h2M4 17h2M10 17h10" /><circle cx="16" cy="7" r="2" /><circle cx="8" cy="17" r="2" /></>) },
  { to: '/pair', label: 'Pair', icon: icon(<path d="M10 14a4 4 0 0 0 5.700 0l3-3a4 4 0 0 0-5.700-5.700l-1 1M14 10a4 4 0 0 0-5.700 0l-3 3a4 4 0 0 0 5.700 5.700l1-1" />) },
]

/** The server buckets "today" in the user's local time, so keep its tz offset in step with the browser's. */
function useTimezoneSync(signedIn: boolean) {
  useEffect(() => {
    if (!signedIn) return
    api<{ settings: Settings }>('/settings')
      .then(({ settings }) => {
        const off = tzOffsetMin()
        if (settings.tzOffsetMin !== off) return api('/settings', { method: 'PUT', body: { tzOffsetMin: off } })
      })
      .catch(() => {})
  }, [signedIn])
}

export default function Layout({ signedIn }: { signedIn: boolean }) {
  useTimezoneSync(signedIn)
  const items = signedIn ? NAV : NAV.filter((n) => n.to === '/pair')
  return (
    <div className="min-h-dvh bg-page">
      <header className="border-b border-line bg-surface print:hidden">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-3">
          <div className="flex items-center gap-2.5">
            <img src={`${import.meta.env.BASE_URL}favicon.svg`} alt="" className="h-7 w-7" />
            <span className="text-lg font-semibold tracking-tight text-ink">Sitwise</span>
          </div>
          <nav className="hidden gap-1 sm:flex" aria-label="Main">
            {items.map((n) => (
              <NavLink
                key={n.to}
                to={n.to}
                end={n.end}
                className={({ isActive }) => cx('rounded-lg px-3 py-2 text-sm font-medium', isActive ? 'bg-ink text-surface' : 'text-ink-2 hover:bg-line/50')}
              >
                {n.label}
              </NavLink>
            ))}
          </nav>
        </div>
      </header>

      {signedIn && <AlertWatcher />}

      <main className="mx-auto max-w-5xl px-4 pb-28 pt-5 sm:pb-10">
        <Outlet />
      </main>

      {/* phone: bottom tab bar (judges may open the dashboard on a phone) */}
      <nav className="safe-bottom fixed inset-x-0 bottom-0 z-10 flex border-t border-line bg-surface sm:hidden print:hidden" aria-label="Main">
        {items.map((n) => (
          <NavLink
            key={n.to}
            to={n.to}
            end={n.end}
            className={({ isActive }) => cx('flex min-h-14 flex-1 flex-col items-center justify-center gap-0.5 text-[11px] font-medium', isActive ? 'text-accent' : 'text-ink-2')}
          >
            {n.icon}
            {n.label}
          </NavLink>
        ))}
      </nav>
    </div>
  )
}
