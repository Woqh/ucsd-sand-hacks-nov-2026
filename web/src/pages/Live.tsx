import { Link } from 'react-router-dom'
import { api } from '../api'
import { Banner, Card, CardTitle, Meter, Stat, STATE_META, StateIcon, cx } from '../components/ui'
import { formatAgo, formatDuration, formatMinutes, pct } from '../format'
import { usePoll } from '../hooks'
import type { Status } from '../types'

const BREAK_AFTER_SEC = 40 * 60 // suggestion: stand up every 30–45 min

export default function Live() {
  const { data: s, error, loading } = usePoll(() => api<Status>('/status'), 2000)

  if (!s) {
    return error ? <Banner tone="error">{error.message}</Banner> : <p className="text-ink-2">{loading ? 'Loading…' : ''}</p>
  }

  const meta = STATE_META[s.state]
  const remaining = s.state === 'DEVIATING' && s.deviatingForSec != null ? Math.max(0, s.thresholdSec - s.deviatingForSec) : null
  const sitting = s.today.sittingSec ?? 0

  return (
    <div className="space-y-4">
      {error && <Banner tone="warn">Connection hiccup: {error.message}. Retrying…</Banner>}
      {!s.paired && (
        <Banner tone="info">
          No phone is paired yet. <Link className="font-medium underline" to="/pair">Pair your phone</Link>, or load demo data from there.
        </Banner>
      )}
      {s.paired && s.stale && (
        <Banner tone="warn">
          The phone hasn't reported {s.device.ageSec == null ? 'yet' : formatAgo(s.device.ageSec)}. Is the app open and monitoring? Showing you as away.
        </Banner>
      )}
      {!s.calibrated && (
        <Banner tone="info">
          You haven't set your goal posture yet. <Link className="font-medium underline" to="/calibration">Calibrate now</Link>
        </Banner>
      )}

      {/* hero: the state, with icon + label so color is never the only signal */}
      <section className={cx('rounded-3xl p-6 sm:p-8', meta.bg)} aria-live="polite">
        <div className={cx('flex items-center gap-3', meta.text)}>
          <StateIcon state={s.state} className="h-9 w-9" />
          <h1 className="text-4xl font-semibold tracking-tight sm:text-5xl">{meta.label}</h1>
        </div>
        <p className="mt-2 text-ink-2">{meta.blurb}</p>

        <div className="mt-5 flex flex-wrap items-end gap-x-8 gap-y-3 text-ink">
          <div>
            <div className="text-xs uppercase tracking-wide text-ink-2">In this state</div>
            <div className="text-2xl font-semibold">{formatDuration(s.timeInStateSec)}</div>
          </div>
          {s.state === 'DEVIATING' && remaining != null && (
            <div className="min-w-48 flex-1">
              <div className="mb-1 flex justify-between text-xs text-ink-2">
                <span>Nudge in {Math.ceil(remaining)}s</span>
                <span>your threshold: {s.thresholdSec}s</span>
              </div>
              <Meter value={s.deviatingForSec ?? 0} max={s.thresholdSec} label="Time until the slouch alert" />
            </div>
          )}
          {s.state === 'SLOUCHING' && (
            <div className="text-sm text-ink-2">
              {s.alertsSent > 0 ? `${s.alertsSent} nudge${s.alertsSent > 1 ? 's' : ''} sent` : 'No nudge sent (quiet hours, cooldown or alerts off)'}
              {s.inCooldown ? ' · cooling down' : ''}
            </div>
          )}
        </div>
      </section>

      {sitting >= BREAK_AFTER_SEC && !s.stale && (
        <Banner tone="warn">
          You've been sitting for {formatMinutes(sitting)}. Stand up, walk around, and shake out your shoulders. It's a good time for a break.
        </Banner>
      )}

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="Posture score today" value={s.today.score ?? '–'} hint={s.today.score == null ? 'No seated time yet' : 'of 100'} />
        <Stat label="Seated today" value={formatMinutes(s.today.seatedSec)} hint={pct(s.today.goodPct) + ' not slouching'} />
        <Stat label="Slouch alerts" value={s.today.slouchEvents} hint={s.today.avgRecoverySec ? `avg ${formatDuration(s.today.avgRecoverySec)} to recover` : undefined} />
        <Stat label="Best streak" value={formatMinutes(s.today.longestGoodStreakSec)} hint="without slouching" />
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <Card>
          <CardTitle hint={s.device.online ? 'online' : 'offline'}>Phone</CardTitle>
          <dl className="space-y-1 text-sm">
            <Row k="Paired" v={s.paired ? 'Yes' : 'No'} />
            <Row k="Last heard from" v={formatAgo(s.device.ageSec)} />
            <Row k="Sitting since last break" v={s.stale ? '–' : formatMinutes(sitting)} />
          </dl>
        </Card>
        <Card>
          <CardTitle hint={s.sample ? `${Math.round(s.sample.confidence * 100)}% confidence` : undefined}>Latest reading</CardTitle>
          {s.sample && !s.stale ? (
            <div className="space-y-3 text-sm">
              <div>
                <div className="mb-1 flex justify-between text-ink-2">
                  <span>Deviation from your goal posture</span>
                  <span className="text-ink">{s.sample.deviation?.toFixed(2) ?? '–'}</span>
                </div>
                <Meter value={Math.min(1, s.sample.deviation ?? 0)} max={1} label="Deviation from goal posture" />
              </div>
              <dl className="grid grid-cols-3 gap-2 text-center">
                <Feature k="Neck" v={s.sample.features.neckAngle} unit="°" />
                <Feature k="Torso" v={s.sample.features.torsoAngle} unit="°" />
                <Feature k="Head fwd" v={s.sample.features.headForwardOffset} />
              </dl>
            </div>
          ) : (
            <p className="text-sm text-ink-2">Nothing live right now.</p>
          )}
        </Card>
      </div>
    </div>
  )
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex justify-between gap-3">
      <dt className="text-ink-2">{k}</dt>
      <dd className="font-medium text-ink">{v}</dd>
    </div>
  )
}

function Feature({ k, v, unit = '' }: { k: string; v: number | undefined; unit?: string }) {
  return (
    <div className="rounded-xl bg-line/40 px-2 py-2">
      <dt className="text-xs text-ink-2">{k}</dt>
      <dd className="font-medium text-ink">{v == null ? '–' : `${v}${unit}`}</dd>
    </div>
  )
}
