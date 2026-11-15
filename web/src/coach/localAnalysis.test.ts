import { describe, expect, it } from 'vitest'
import type { CoachPack, Exercise } from '../types'
import { buildLocalAnalysis } from './localAnalysis'

const LIB: Exercise[] = [
  { id: 'chin_tuck', title: 'Chin tucks', for: ['headForward'], steps: ['Sit tall.', 'Glide your head back.'] },
  { id: 'shoulder_blade_squeeze', title: 'Shoulder-blade squeezes', for: ['headForward'], steps: ['Squeeze gently.'] },
]

const rich: CoachPack = {
  schema: 1,
  window: { days: 42, seatedHours: 120, slouchPct: 18 },
  habits: {
    strength: { targetPct: 70, daysWithData: 12, daysAtTarget: 10, consistencyPct: 83.3, forgivingStreak: 9, strictStreak: 4 },
    bests: { bestDayScore: 92, bestWeekScore: 88, longestDayStreak: 6, longestGoodStretchMin: 55 },
    relapse: { active: false },
    challenge: { title: 'Cut your Tuesday 3 PM slouch by 5 points', detail: "It's currently 41%, your weakest hour." },
  },
  patterns: {
    fatigue: { buckets: [], baselinePct: 5, onsetMin: 40 },
    onsetLatency: { medianSec: 1200, runs: 30, runsWithSlouchPct: 80 },
    dangerHours: [{ day: 1, hour: 15, slouchPct: 41, seatedMin: 90 }],
    weekdays: [],
    triggers: [],
    fingerprint: { headForwardPct: 70, trunkLeanPct: 25, otherPct: 5, samples: 400, signature: 'headForward' },
    drift: { weekly: [], drifting: false, deltaDeviation: null, calibrationAgeDays: 10, recalibrateSuggested: false },
    setupHints: [{ id: 'screen', title: 'Check your screen height and distance', detail: 'Raise the screen.', because: 'Head drifts forward.' }],
  },
  coaching: {
    response: {
      nudges: 60, recovered: 55, leftAfterNudge: 5, within15Pct: 50, within30Pct: 82, within60Pct: 92, medianRecoverySec: 14,
      byLevel: [{ level: 1, n: 50, within30Pct: 88, medianSec: 12 }, { level: 2, n: 8, within30Pct: 50, medianSec: 40 }, { level: 3, n: 0, within30Pct: null, medianSec: null }],
      byPartOfDay: [{ part: 'morning', n: 20, within30Pct: 95, medianSec: 10 }, { part: 'afternoon', n: 30, within30Pct: 70, medianSec: 20 }, { part: 'evening', n: 5, within30Pct: null, medianSec: null }],
    },
    recoveryTrend: [{ weeksAgo: 5, avgRecoverySec: 60, n: 8 }, { weeksAgo: 0, avgRecoverySec: 20, n: 10 }],
    alertFatigue: { status: 'ok', firstHalfPct: 85, secondHalfPct: 80, n: 50 },
    suggestions: [],
    currentSettings: { slouchThresholdSec: 30, sensitivity: 0.5, cooldownSec: 120, nudgeTone: 'gentle' },
  },
  breaks: { targetMin: 45, runs: 40, longestSitMin: 110, avgSitMin: 50, runsOverTargetPct: 40, breaksPerDay: 3, microBreaksPerDay: 1 },
  workHours: { startHour: 9, endHour: 17, days: 20 },
  exercises: [
    { ...LIB[0], safety: 'Stop if anything hurts.' },
    { ...LIB[1], safety: 'Stop if anything hurts.' },
  ],
}

const empty: CoachPack = {
  ...rich,
  window: { days: 42, seatedHours: 0, slouchPct: null },
  habits: { ...rich.habits, strength: { ...rich.habits.strength, consistencyPct: null, forgivingStreak: 0 }, bests: { bestDayScore: null, bestWeekScore: null, longestDayStreak: 0, longestGoodStretchMin: 0 } },
  patterns: { ...rich.patterns, fatigue: { buckets: [], baselinePct: null, onsetMin: null }, dangerHours: [], fingerprint: null, setupHints: [] },
  coaching: { ...rich.coaching, response: { nudges: 0, recovered: 0, leftAfterNudge: 0, within15Pct: null, within30Pct: null, within60Pct: null, medianRecoverySec: null, byLevel: [], byPartOfDay: [] }, recoveryTrend: [], alertFatigue: { status: 'insufficient', firstHalfPct: null, secondHalfPct: null, n: 0 } },
  exercises: [],
}

describe('buildLocalAnalysis: a person with plenty of data', () => {
  const a = buildLocalAnalysis(rich, LIB)

  it('describes habits and how they slouch, using their own numbers', () => {
    expect(a.headline).toContain('Tuesday 3 PM')
    expect(a.summary).toContain('120 hours')
    expect(a.summary).toContain('18%')
    expect(a.summary).toContain('head drifting forward')
    expect(a.summary).toContain('40 minutes')
  })

  it('works out how they respond to coaching and what works for them', () => {
    expect(a.howYouRespond).toContain('82%')
    expect(a.howYouRespond).toMatch(/best in the morning \(95%\) and least in the afternoon \(70%\)/)
    const insights = a.whatWorks.map((w) => w.insight).join('|')
    expect(insights).toContain('single nudge')
    expect(insights).toContain('Repeat nudges')
    expect(insights).toContain('faster')
  })

  it('recommends matched exercises, a plan, and a tone', () => {
    expect(a.recommendedExerciseIds).toEqual(['chin_tuck', 'shoulder_blade_squeeze'])
    expect(a.weeklyPlan.length).toBeGreaterThanOrEqual(3)
    expect(a.weeklyPlan[0].action).toContain('Chin tucks')
    expect(a.suggestedTone).toBe('gentle')
    expect(a.toneWhy).toContain('quickly')
    expect(a.confidence).toBe('high')
    expect(a.strengths.length).toBeGreaterThan(0)
  })
})

describe('buildLocalAnalysis: honesty about thin data', () => {
  const a = buildLocalAnalysis(empty, LIB)

  it('says what it does not know instead of guessing', () => {
    expect(a.confidence).toBe('low')
    expect(a.caveats.length).toBeGreaterThan(0)
    expect(a.howYouRespond).toContain("haven't had enough nudges")
    expect(a.focusAreas).toHaveLength(1)
    expect(a.focusAreas[0].title).toContain('Build up some history')
    expect(a.whatWorks).toEqual([])
    expect(a.recommendedExerciseIds).toEqual([])
    expect(a.suggestedTone).toBe('gentle')
    expect(a.weeklyPlan.length).toBeGreaterThanOrEqual(3)
  })

  it('never leaks undefined, NaN or null into the text', () => {
    for (const pack of [rich, empty]) {
      const text = JSON.stringify(buildLocalAnalysis(pack, LIB))
      expect(text).not.toMatch(/undefined|NaN|null|\[object/)
    }
  })
})

describe('buildLocalAnalysis: tone follows how the person responds', () => {
  const withResponse = (within30Pct: number, status: CoachPack['coaching']['alertFatigue']['status'] = 'ok'): CoachPack => ({
    ...rich,
    coaching: { ...rich.coaching, alertFatigue: { ...rich.coaching.alertFatigue, status }, response: { ...rich.coaching.response, nudges: 30, within30Pct } },
  })
  it('suggests plainer wording when they have gone numb to nudges', () => {
    expect(buildLocalAnalysis(withResponse(60, 'fatigued'), LIB).suggestedTone).toBe('neutral')
  })
  it('suggests clearer wording when gentle nudges are not followed', () => {
    expect(buildLocalAnalysis(withResponse(30), LIB).suggestedTone).toBe('direct')
  })
  it('keeps the current tone when the evidence is mixed', () => {
    const mixed = withResponse(55)
    mixed.coaching.currentSettings.nudgeTone = 'neutral'
    expect(buildLocalAnalysis(mixed, LIB).suggestedTone).toBe('neutral')
  })
})

describe('buildLocalAnalysis: output fits the same limits as the server schema', () => {
  it('stays inside length and count limits, even for long inputs', () => {
    const long: CoachPack = { ...rich, habits: { ...rich.habits, challenge: { title: 'x'.repeat(500), detail: 'y' } } }
    const a = buildLocalAnalysis(long, LIB)
    expect(a.headline.length).toBeLessThanOrEqual(140)
    expect(a.summary.length).toBeLessThanOrEqual(700)
    expect(a.howYouRespond.length).toBeLessThanOrEqual(500)
    expect(a.whatWorks.length).toBeLessThanOrEqual(4)
    expect(a.focusAreas.length).toBeGreaterThanOrEqual(1)
    expect(a.focusAreas.length).toBeLessThanOrEqual(3)
    expect(a.weeklyPlan.length).toBeGreaterThanOrEqual(3)
    expect(a.weeklyPlan.length).toBeLessThanOrEqual(5)
    expect(a.weeklyPlan.every((p) => p.action.length <= 160 && p.when.length <= 30)).toBe(true)
    expect(a.recommendedExerciseIds.length).toBeLessThanOrEqual(3)
    expect(a.caveats.length).toBeLessThanOrEqual(3)
  })

  it('only recommends exercises that exist in the library', () => {
    const odd: CoachPack = { ...rich, exercises: [{ id: 'not_in_library', title: 'x', for: [], steps: [] }, { ...LIB[0] }] }
    expect(buildLocalAnalysis(odd, LIB).recommendedExerciseIds).toEqual(['chin_tuck'])
  })
})
