import { EVIDENCE, LEVEL_LABEL, LEVEL_STEPS, POPULATION, type EvidenceLevel } from '../evidence'
import { Card, CardTitle } from './ui'

/** Three steps filled left to right (none fills nothing). The level is also written out, so the
 *  meaning never depends on colour or fill alone. */
function Meter({ level }: { level: EvidenceLevel }) {
  const filled = level === 'none' ? 0 : LEVEL_STEPS.findIndex((s) => s.key === level) + 1
  return (
    <div>
      <div role="img" aria-label={`Evidence level: ${LEVEL_LABEL[level]}`} className="flex gap-0.5">
        {LEVEL_STEPS.map((s, i) => (
          <div key={s.key} className="h-2 flex-1 rounded-[3px]" style={{ background: i < filled ? 'var(--series-1)' : 'var(--line)' }} />
        ))}
      </div>
      <div className="mt-1 flex text-[11px] text-muted">
        {LEVEL_STEPS.map((s) => (
          <span key={s.key} className="flex-1">
            {s.label}
          </span>
        ))}
      </div>
      <div className="mt-1 text-sm font-medium text-ink">{LEVEL_LABEL[level]}</div>
    </div>
  )
}

export function EvidenceMeter() {
  return (
    <Card>
      <CardTitle hint="what the research says">Does slouching cause pain?</CardTitle>
      <p className="mb-4 text-sm text-ink-2">
        Short answer: nobody has shown that it does. Here is how strong the evidence is for each outcome, with the studies it comes from.
      </p>
      <ul className="space-y-5">
        {EVIDENCE.map((e) => (
          <li key={e.outcome}>
            <div className="mb-1.5 font-medium text-ink">{e.outcome}</div>
            <Meter level={e.level} />
            <p className="mt-2 text-sm text-ink-2">{e.summary}</p>
            {e.sources.length > 0 && (
              <p className="mt-1 text-xs text-ink-2">
                Source:{' '}
                {e.sources.map((s, i) => (
                  <span key={s.url}>
                    {i > 0 && ', '}
                    <a className="underline" href={s.url} target="_blank" rel="noreferrer">
                      {s.label}
                    </a>
                  </span>
                ))}
              </p>
            )}
          </li>
        ))}
      </ul>
      <p className="mt-4 border-t border-line pt-3 text-xs text-ink-2">
        Illustrative and educational only. Not medical advice. Talk to a clinician about pain or health concerns.
      </p>
    </Card>
  )
}

export function PopulationContext() {
  const { lowBack, neck, toolUrl } = POPULATION
  return (
    <Card>
      <CardTitle hint="population context, not your risk">How common are back and neck pain?</CardTitle>
      <dl className="grid gap-3 sm:grid-cols-2">
        <div className="rounded-xl bg-line/40 p-3">
          <dt className="text-sm text-ink-2">Low back pain, worldwide in 2020</dt>
          <dd className="mt-1 text-2xl font-semibold tracking-tight text-ink">{lowBack.now} people</dd>
          <dd className="mt-1 text-xs text-ink-2">
            95% uncertainty interval {lowBack.nowRange}. Projected {lowBack.projected}.
          </dd>
        </div>
        <div className="rounded-xl bg-line/40 p-3">
          <dt className="text-sm text-ink-2">Neck pain, worldwide in 2020</dt>
          <dd className="mt-1 text-2xl font-semibold tracking-tight text-ink">{neck.now} people</dd>
          <dd className="mt-1 text-xs text-ink-2">
            95% uncertainty interval {neck.nowRange}. Most common between ages {neck.peakAges}.
          </dd>
        </div>
      </dl>
      <p className="mt-3 text-sm text-ink-2">
        These are global estimates from the Global Burden of Disease 2021 study (
        <a className="underline" href={lowBack.source.url} target="_blank" rel="noreferrer">
          low back pain
        </a>
        ,{' '}
        <a className="underline" href={neck.source.url} target="_blank" rel="noreferrer">
          neck pain
        </a>
        ). They show how widespread the problems are, not how likely <em>you</em> are to get them, and they don’t separate out posture. For figures by age and region, see the{' '}
        <a className="underline" href={toolUrl} target="_blank" rel="noreferrer">
          IHME GBD Results Tool
        </a>
        .
      </p>
    </Card>
  )
}
