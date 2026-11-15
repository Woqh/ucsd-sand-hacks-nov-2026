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
}

export interface Settings {
  schema: 1
  slouchThresholdSec: number
  sensitivity: number
  alertChannels: { phone: boolean; desktop: boolean }
  cooldownSec: number
  quietHours: { enabled: boolean; start: string; end: string }
  tzOffsetMin: number
}

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
  sample: { t: number; label: PostureLabel; deviation: number | null; confidence: number; features: PostureFeatures } | null
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
