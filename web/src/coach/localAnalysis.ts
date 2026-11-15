import type { Analysis, CoachPack, Exercise, Tone } from '../types'

// The on-device coaching profile: the same shape Gemini returns, built from the user's own numbers with
// plain rules. Nothing leaves the browser to make it, and it is the fallback whenever Gemini isn't
// configured, isn't consented to, or fails. Each string stays inside the same length limits as the
// server's Gemini schema, so the two are interchangeable.

const DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
export const dayName = (d: number): string => DAYS[d] ?? ''
export const hour12 = (h: number): string => `${h % 12 || 12} ${h < 12 ? 'AM' : 'PM'}`
const pct = (v: number | null | undefined): string => (v == null ? '–' : `${Math.round(v)}%`)
const clip = (s: string, n: number): string => (s.length <= n ? s : `${s.slice(0, n - 1).trimEnd()}…`)

export function buildLocalAnalysis(pack: CoachPack, library: Exercise[]): Analysis {
  const { window: w, patterns: pat, coaching: co, habits } = pack
  const r = co.response
  const hours = w.seatedHours
  const confidence: Analysis['confidence'] = hours < 20 ? 'low' : hours < 60 ? 'medium' : 'high'

  const caveats: string[] = []
  if (hours < 20) caveats.push(`Only ${Math.round(hours)} seated hours so far, so treat these as early signs.`)
  if (r.nudges < 10) caveats.push('Not many nudges yet, so how you respond to coaching is still unclear.')
  if (!pat.fingerprint) caveats.push('Not enough posture readings yet to tell how you slouch.')

  // ------------------------------------------------------------------ summary
  const parts: string[] = []
  parts.push(
    hours > 0
      ? `Over the last ${w.days} days you sat about ${Math.round(hours)} hours${w.slouchPct != null ? ` and slouched around ${Math.round(w.slouchPct)}% of that` : ''}.`
      : "There isn't enough sitting data yet to describe your habits.",
  )
  const f = pat.fingerprint
  if (f?.signature === 'headForward') parts.push(`When you slouch, it's mostly your head drifting forward (${Math.round(f.headForwardPct)}% of slouching).`)
  else if (f?.signature === 'trunkLean') parts.push(`When you slouch, it's mostly your upper body leaning forward (${Math.round(f.trunkLeanPct)}% of slouching).`)
  else if (f) parts.push(`You slouch in a mix of ways: head forward ${Math.round(f.headForwardPct)}%, upper body ${Math.round(f.trunkLeanPct)}%.`)
  if (pat.fatigue.onsetMin != null) parts.push(`Your posture tends to slip after about ${pat.fatigue.onsetMin} minutes of sitting.`)
  if (pat.dangerHours[0]) parts.push(`${dayName(pat.dangerHours[0].day)} around ${hour12(pat.dangerHours[0].hour)} is your weakest time.`)

  // ------------------------------------------------------------------ how you respond
  const withRate = r.byPartOfDay.filter((p) => p.within30Pct != null && p.n >= 3)
  const best = [...withRate].sort((a, b) => (b.within30Pct as number) - (a.within30Pct as number))[0]
  const worst = [...withRate].sort((a, b) => (a.within30Pct as number) - (b.within30Pct as number))[0]
  const respond: string[] = []
  if (r.nudges < 5) respond.push("You haven't had enough nudges yet to see how you respond.")
  else {
    respond.push(`${pct(r.within30Pct)} of your nudges are followed by sitting up within 30 seconds${r.medianRecoverySec != null ? ` (typically ${Math.round(r.medianRecoverySec)}s)` : ''}.`)
    if (best && worst && best.part !== worst.part && (best.within30Pct as number) - (worst.within30Pct as number) >= 15)
      respond.push(`You respond best in the ${best.part} (${pct(best.within30Pct)}) and least in the ${worst.part} (${pct(worst.within30Pct)}).`)
    if (co.alertFatigue.status === 'fatigued') respond.push(`You've been responding to fewer nudges lately (${pct(co.alertFatigue.secondHalfPct)}, down from ${pct(co.alertFatigue.firstHalfPct)}).`)
  }

  // ------------------------------------------------------------------ what works for you
  const whatWorks: Analysis['whatWorks'] = []
  const l1 = r.byLevel.find((l) => l.level === 1)
  const l2 = r.byLevel.find((l) => l.level === 2)
  if (l1 && l1.within30Pct != null && l1.within30Pct >= 70)
    whatWorks.push({ insight: 'A single nudge is usually enough for you', evidence: `${pct(l1.within30Pct)} of first nudges are followed by sitting up within 30 s` })
  if (l1?.within30Pct != null && l2?.within30Pct != null && l2.within30Pct < l1.within30Pct - 10)
    whatWorks.push({ insight: 'Repeat nudges work less well than the first', evidence: `${pct(l2.within30Pct)} for the second nudge vs ${pct(l1.within30Pct)} for the first` })
  // only when the gap between parts of the day is big enough to mean something (same bar as the sentence above)
  if (best && worst && best.part !== worst.part && (best.within30Pct as number) - (worst.within30Pct as number) >= 15) whatWorks.push({ insight: `Nudges land best in the ${best.part}`, evidence: `${pct(best.within30Pct)} fixed within 30 s` })
  const trend = co.recoveryTrend
  if (trend.length >= 2 && trend[trend.length - 1].avgRecoverySec <= trend[0].avgRecoverySec * 0.9)
    whatWorks.push({ insight: "You're getting faster at fixing your posture", evidence: `${Math.round(trend[0].avgRecoverySec)}s on average ${trend[0].weeksAgo} weeks ago, ${Math.round(trend[trend.length - 1].avgRecoverySec)}s lately` })

  // ------------------------------------------------------------------ strengths
  const strengths: string[] = []
  if ((habits.strength.consistencyPct ?? 0) >= 70) strengths.push(`Consistent: ${pct(habits.strength.consistencyPct)} of recent days on target`)
  if (habits.bests.longestGoodStretchMin >= 30) strengths.push(`Your longest good stretch is ${habits.bests.longestGoodStretchMin} minutes`)
  if (r.medianRecoverySec != null && r.medianRecoverySec <= 20) strengths.push(`Quick to recover: about ${Math.round(r.medianRecoverySec)}s after a nudge`)

  // ------------------------------------------------------------------ exercises, focus, plan
  const exIds = pack.exercises.map((e) => e.id).filter((id) => library.some((l) => l.id === id))
  const firstEx = library.find((l) => l.id === exIds[0])
  const focusAreas: Analysis['focusAreas'] = []
  if (pat.dangerHours[0]) {
    const d = pat.dangerHours[0]
    focusAreas.push({ title: `${dayName(d.day)} around ${hour12(d.hour)}`, why: `${Math.round(d.slouchPct)}% slouching then, well above your average.`, action: 'Set a reminder a few minutes before and stand up for a minute.' })
  }
  if (pat.fatigue.onsetMin != null)
    focusAreas.push({ title: 'Long sits', why: `Your posture slips after about ${pat.fatigue.onsetMin} minutes.`, action: `Stand up for a minute around the ${Math.max(10, pat.fatigue.onsetMin - 10)}-minute mark.` })
  if (f && firstEx) focusAreas.push({ title: 'How you slouch', why: `It's mostly ${f.signature === 'headForward' ? 'head-forward' : f.signature === 'trunkLean' ? 'upper-body lean' : 'a mix'}.`, action: `Try ${firstEx.title.toLowerCase()} once a day.` })
  if (focusAreas.length === 0) focusAreas.push({ title: 'Build up some history', why: "There isn't enough data to pick out a pattern yet.", action: 'Keep Sitwise running through a few workdays.' })

  const plan: Analysis['weeklyPlan'] = []
  if (firstEx) plan.push({ when: 'Daily', action: `${firstEx.title}: ${firstEx.steps[0] ?? ''}`.trim() })
  if (pat.setupHints[0]) plan.push({ when: 'Monday', action: pat.setupHints[0].title })
  if (pat.fatigue.onsetMin != null) plan.push({ when: 'Each long sit', action: `Stand up a few minutes before the ${pat.fatigue.onsetMin}-minute mark.` })
  plan.push({ when: 'This week', action: habits.challenge.title })
  for (const filler of [
    { when: 'Daily', action: 'Check your posture once after lunch.' },
    { when: 'Daily', action: 'Take a short stand-and-walk break every hour or so.' },
    { when: 'Friday', action: "Look at this week's score and pick one thing to improve." },
  ])
    if (plan.length < 3) plan.push(filler)

  // ------------------------------------------------------------------ tone
  const current: Tone = co.currentSettings.nudgeTone ?? 'gentle'
  let suggestedTone: Tone = current
  let toneWhy = 'Not enough response data yet to suggest a change.'
  if (co.alertFatigue.status === 'fatigued') {
    suggestedTone = 'neutral'
    toneWhy = "You're responding to fewer nudges lately, so plainer, less repetitive wording may land better."
  } else if (r.within30Pct != null && r.nudges >= 10 && r.within30Pct >= 75) {
    suggestedTone = 'gentle'
    toneWhy = 'You respond quickly even to gentle nudges.'
  } else if (r.within30Pct != null && r.nudges >= 10 && r.within30Pct < 40) {
    suggestedTone = 'direct'
    toneWhy = "Gentle nudges aren't being followed quickly, so clearer wording may help."
  }

  const headline = pat.dangerHours[0] && (r.within30Pct ?? 0) >= 60
    ? `You respond well to nudges; ${dayName(pat.dangerHours[0].day)} ${hour12(pat.dangerHours[0].hour)} is your weak spot`
    : f?.signature === 'headForward' ? 'You mostly slouch by letting your head drift forward'
    : f?.signature === 'trunkLean' ? 'You mostly slouch by leaning your upper body forward'
    : hours >= 5 ? 'Your sitting profile is taking shape' : 'Your sitting profile is just getting started'

  return {
    headline: clip(headline, 140),
    summary: clip(parts.join(' '), 700),
    howYouRespond: clip(respond.join(' '), 500),
    whatWorks: whatWorks.slice(0, 4).map((x) => ({ insight: clip(x.insight, 200), evidence: clip(x.evidence, 200) })),
    strengths: strengths.slice(0, 3).map((s) => clip(s, 160)),
    focusAreas: focusAreas.slice(0, 3).map((x) => ({ title: clip(x.title, 80), why: clip(x.why, 240), action: clip(x.action, 240) })),
    weeklyPlan: plan.slice(0, 5).map((x) => ({ when: clip(x.when, 30), action: clip(x.action, 160) })),
    recommendedExerciseIds: exIds.slice(0, 3),
    suggestedTone,
    toneWhy,
    confidence,
    caveats: caveats.slice(0, 3).map((c) => clip(c, 200)),
  }
}
