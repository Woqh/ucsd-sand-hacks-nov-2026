// Hand-written mirrors of the API contract (docs/openapi.yaml). Keep in sync with api/ and the
// Swift Codable structs in ios/. Don't over-engineer type generation for a hackathon.

export type PostureState = 'AWAY' | 'GOOD' | 'DEVIATING' | 'SLOUCHING'
export type PostureLabel = 'GOOD' | 'SLOUCHING' | 'AWAY' | 'UNKNOWN'

export interface PostureFeatures {
  neckAngle?: number
  torsoAngle?: number
  headForwardOffset?: number
  [k: string]: number | undefined
}

export interface PostureSample {
  schema: 1
  sessionId: string
  t: number
  label: PostureLabel
  deviation: number
  confidence: number
  features: PostureFeatures
}

export interface CalibrationBaseline {
  schema: 1
  goal: PostureFeatures
  tolerance: number
  capturedAt: number
  /** The model's verdict (calibration gate). Absent = accepted. `false` => never stored; show `issues`. */
  accepted?: boolean
  issues?: string[]
  stub?: boolean
  /** The live model that measured it (when not a stub). */
  source?: string
}

export interface Settings {
  schema: 1
  slouchThresholdSec: number
  sensitivity: number
  alertChannels: { phone: boolean; desktop: boolean }
  cooldownSec: number
  quietHours: { enabled: boolean; start: string; end: string }
  tzOffsetMin: number
  nudgeTone: Tone
  /** Focus mode: with onlyDuringFocus on, nudges fire only while a session started via POST /focus is running. */
  focus: { onlyDuringFocus: boolean; untilMs: number }
}

export type Tone = 'gentle' | 'neutral' | 'direct'

export interface DaySummary {
  score: number | null
  goodPct: number | null
  seatedSec: number
  goodSec: number
  graceSec: number
  slouchSec: number
  awaySec: number
  slouchEvents: number
  slouchEventsPerHour: number | null
  longestGoodStreakSec: number
  avgRecoverySec: number | null
  sittingSec?: number
}

export interface Status {
  schema: 1
  paired: boolean
  calibrated: boolean
  serverTime: number
  thresholdSec: number
  device: { lastSeenMs: number | null; ageSec: number | null; online: boolean }
  state: PostureState
  rawState: PostureState
  stale: boolean
  timeInStateSec: number
  deviatingForSec: number | null
  inCooldown: boolean
  alertsSent: number
  sample: { t: number; label: PostureLabel; deviation: number | null; confidence: number; features: PostureFeatures; /** which model produced it, if it said */ source?: string } | null
  today: DaySummary
}

export interface DailyPoint {
  date: string
  dayIndex: number
  seatedSec: number
  goodPct: number | null
  score: number | null
}

export interface HeatCell {
  day: number // 0 = Monday
  hour: number
  seatedSec: number
  goodPct: number | null
}

export interface TimelineSegment {
  state: PostureState
  start: number
  end: number
}

export type OutlookStatus = 'on_track' | 'at_risk' | 'no_data'

export interface Metrics {
  schema: 1
  range: 'day' | 'week' | 'month'
  since: number
  until: number
  tzOffsetMin: number
  summary: DaySummary
  previous: { score: number | null; goodPct: number | null; seatedSec: number }
  daily: DailyPoint[]
  heatmap: HeatCell[]
  timeline: TimelineSegment[]
  dayStreak: number
  goal: { previousPct: number | null; currentPct: number | null; targetPct: number }
  outlook: { status: OutlookStatus; thresholdPct: number }
  sittingSec: number
}

export interface PairCreateResponse {
  schema: 1
  dashboardToken?: string
  pairingCode: string
  expiresAt: number
}

export interface Health {
  ok: boolean
  devRoutes: boolean
  store: 'postgres' | 'memory' | string
  db?: { ok: boolean; problem: 'schema_missing' | 'connect_failed' | 'error' | null }
}

export interface ChannelResult {
  sent: number
  failed: number
  skipped: string | null
}

export interface PainPoint {
  t: number
  pain: number
  area: string | null
  /** Share of seated time slouching in the 7 days before this check-in (null = too little data). */
  slouchPct: number | null
  seatedSec: number
  /** Included in the comparison (points are kept 6+ days apart so windows don't overlap). */
  used: boolean
}

export interface PainInsight {
  schema: 1
  points: PainPoint[]
  lastCheckinAt: number | null
  nextSuggestedAt: number | null
  correlation: {
    enough: boolean
    n: number
    needed: number
    rho: number | null
    strength: 'none' | 'modest' | 'stronger' | null
    direction: 'positive' | 'negative' | null
  }
}

// ---------------------------------------------------------------- coach (mirrors api/core/coach_pack.py)
export interface Exercise {
  id: string
  title: string
  for: string[]
  steps: string[]
  safety?: string
}

export interface FatigueBucket {
  minFrom: number
  minTo: number | null
  slouchPct: number | null
  seatedMin: number
  runs: number
}

export interface NudgeGroup {
  n: number
  within30Pct: number | null
  medianSec: number | null
}

export interface Suggestion {
  id: string
  title: string
  why: string
  /** A valid partial settings update: apply with PUT /settings after the user confirms. */
  patch: Record<string, unknown>
}

export interface CoachPack {
  schema: 1
  window: { days: number; seatedHours: number; slouchPct: number | null }
  habits: {
    strength: { targetPct: number; daysWithData: number; daysAtTarget: number; consistencyPct: number | null; forgivingStreak: number; strictStreak: number }
    bests: { bestDayScore: number | null; bestWeekScore: number | null; longestDayStreak: number; longestGoodStretchMin: number }
    relapse: { active: boolean; message?: string; smallerGoalPct?: number }
    challenge: { title: string; detail: string }
  }
  patterns: {
    fatigue: { buckets: FatigueBucket[]; baselinePct: number | null; onsetMin: number | null }
    onsetLatency: { medianSec: number | null; runs: number; runsWithSlouchPct: number | null }
    dangerHours: { day: number; hour: number; slouchPct: number; seatedMin: number }[]
    weekdays: { day: number; slouchPct: number; seatedMin: number }[]
    triggers: { kind: string; label: string }[]
    fingerprint: { headForwardPct: number; trunkLeanPct: number; otherPct: number; samples: number; signature: 'headForward' | 'trunkLean' | 'mixed' } | null
    drift: { weekly: { weeksAgo: number; avgDeviation: number; n: number }[]; drifting: boolean; deltaDeviation: number | null; calibrationAgeDays: number | null; recalibrateSuggested: boolean }
    setupHints: { id: string; title: string; detail: string; because: string }[]
  }
  coaching: {
    response: {
      nudges: number
      recovered: number
      leftAfterNudge: number
      within15Pct: number | null
      within30Pct: number | null
      within60Pct: number | null
      medianRecoverySec: number | null
      byLevel: ({ level: number } & NudgeGroup)[]
      byPartOfDay: ({ part: 'morning' | 'afternoon' | 'evening' } & NudgeGroup)[]
    }
    recoveryTrend: { weeksAgo: number; avgRecoverySec: number; n: number }[]
    alertFatigue: { status: 'ok' | 'watch' | 'fatigued' | 'insufficient'; firstHalfPct: number | null; secondHalfPct: number | null; n: number }
    suggestions: Suggestion[]
    currentSettings: { slouchThresholdSec: number; sensitivity: number; cooldownSec: number; nudgeTone: Tone }
  }
  breaks: { targetMin: number; runs: number; longestSitMin: number | null; avgSitMin: number | null; runsOverTargetPct: number | null; breaksPerDay: number; microBreaksPerDay: number }
  workHours: { startHour: number; endHour: number; days: number } | null
  exercises: Exercise[]
}

export interface CoachInsights {
  schema: 1
  pack: CoachPack
  library: Exercise[]
  ai: { configured: boolean; model: string | null }
}

export interface CoachPreview {
  schema: 1
  payload: Record<string, unknown>
  bytes: number
  disclosure: string[]
  ai: { configured: boolean; model: string | null }
}

/** The coaching profile (Gemini's output, or the on-device equivalent). Stored ONLY in this browser. */
export interface Analysis {
  headline: string
  summary: string
  howYouRespond: string
  whatWorks: { insight: string; evidence: string }[]
  strengths: string[]
  focusAreas: { title: string; why: string; action: string }[]
  weeklyPlan: { when: string; action: string }[]
  recommendedExerciseIds: string[]
  suggestedTone: Tone
  toneWhy: string
  confidence: 'low' | 'medium' | 'high'
  caveats: string[]
}

export interface SettingsProposal {
  schema: 1
  explanation: string
  patch: Record<string, unknown>
  changes: { field: string; from: unknown; to: unknown }[]
}

export interface SegmentsResponse {
  schema: 1
  since: number
  until: number
  /** [startMs, endMs, code]: G good, D drifting, S slouching, A away. */
  segments: [number, number, 'G' | 'D' | 'S' | 'A'][]
}
