// Calendar overlay, entirely in the browser: the user picks an .ics file, we read ONLY meeting times
// (never titles, attendees or locations: SUMMARY and friends are not even parsed) and compare them
// with their own posture segments. The file is never uploaded.
//
// Supported: single events (UTC "Z", floating or TZID times), DAILY and WEEKLY recurrence (INTERVAL, BYDAY,
// COUNT, UNTIL, EXDATE), and RECURRENCE-ID overrides. Skipped: all-day events, cancelled or "free"
// (TRANSPARENT) events, and monthly/yearly recurrence (counted so the UI can say so). Times with a TZID
// are treated as local time, an approximation.

export interface Interval {
  start: number
  end: number
}

export interface ParsedMeetings {
  meetings: Interval[]
  skippedRecurring: number
  skippedAllDay: number
}

const DAY_MS = 86_400_000
const WEEKDAY_CODES = ['SU', 'MO', 'TU', 'WE', 'TH', 'FR', 'SA']

interface Prop {
  name: string
  params: string
  value: string
}

function unfold(text: string): string[] {
  return text.replace(/\r?\n[ \t]/g, '').split(/\r?\n/)
}

function parseProp(line: string): Prop | null {
  const colon = line.indexOf(':')
  if (colon < 0) return null
  const head = line.slice(0, colon)
  const semi = head.indexOf(';')
  return { name: (semi < 0 ? head : head.slice(0, semi)).toUpperCase(), params: semi < 0 ? '' : head.slice(semi + 1).toUpperCase(), value: line.slice(colon + 1).trim() }
}

/** 20241115T120000Z (UTC) | 20241115T120000 (local) | 20241115 (all-day). */
export function parseIcsDate(value: string, params = ''): { ms: number; allDay: boolean } | null {
  const m = /^(\d{4})(\d{2})(\d{2})(?:T(\d{2})(\d{2})(\d{2})(Z)?)?$/.exec(value.trim())
  if (!m) return null
  const [, y, mo, d, hh, mi, ss, z] = m
  if (hh === undefined || params.includes('VALUE=DATE')) return { ms: new Date(+y, +mo - 1, +d).getTime(), allDay: true }
  return { ms: z ? Date.UTC(+y, +mo - 1, +d, +hh, +mi, +ss) : new Date(+y, +mo - 1, +d, +hh, +mi, +ss).getTime(), allDay: false }
}

function parseDuration(v: string): number | null {
  const m = /^P(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$/.exec(v.trim())
  if (!m) return null
  const [, w, d, h, mi, s] = m
  return ((+(w ?? 0) * 7 + +(d ?? 0)) * 24 * 3600 + +(h ?? 0) * 3600 + +(mi ?? 0) * 60 + +(s ?? 0)) * 1000
}

interface Rule {
  freq: string
  interval: number
  count: number | null
  until: number | null
  byday: number[] | null
}

function parseRule(v: string): Rule {
  const kv = Object.fromEntries(v.split(';').map((p) => p.split('=') as [string, string]))
  const byday = kv.BYDAY ? kv.BYDAY.split(',').map((c) => WEEKDAY_CODES.indexOf(c.replace(/^[+-]?\d+/, ''))).filter((i) => i >= 0) : null
  return {
    freq: (kv.FREQ ?? '').toUpperCase(),
    interval: Math.max(1, parseInt(kv.INTERVAL ?? '1', 10) || 1),
    count: kv.COUNT ? parseInt(kv.COUNT, 10) : null,
    until: kv.UNTIL ? (parseIcsDate(kv.UNTIL)?.ms ?? null) : null,
    byday,
  }
}

function occurrences(start: number, dur: number, rule: Rule, exdates: Set<number>, from: number, to: number): Interval[] {
  const out: Interval[] = []
  const base = new Date(start)
  const mondayOffset = (base.getDay() + 6) % 7
  const days = base.getDay()
  const wanted = rule.byday && rule.byday.length ? rule.byday : [days]
  let emitted = 0
  for (let d = 0; d < 4000; d++) {
    // build in local wall-clock terms so a 9:00 meeting stays at 9:00 across daylight-saving changes
    const occ = new Date(base.getFullYear(), base.getMonth(), base.getDate() + d, base.getHours(), base.getMinutes(), base.getSeconds()).getTime()
    if (occ > to) break
    if (rule.until != null && occ > rule.until) break
    const day = new Date(occ).getDay()
    const match = rule.freq === 'DAILY' ? d % rule.interval === 0 : Math.floor((mondayOffset + d) / 7) % rule.interval === 0 && wanted.includes(day)
    if (!match) continue
    emitted++
    if (rule.count != null && emitted > rule.count) break
    if (!exdates.has(occ) && occ + dur > from) out.push({ start: occ, end: occ + dur })
  }
  return out
}

interface RawEvent {
  uid: string
  start: number | null
  end: number | null
  durMs: number | null
  allDay: boolean
  rrule: string | null
  exdates: Set<number>
  recurrenceId: number | null
  skip: boolean
}

export function parseMeetings(ics: string, from: number, to: number): ParsedMeetings {
  const events: RawEvent[] = []
  let cur: RawEvent | null = null
  for (const line of unfold(ics)) {
    const upper = line.trim().toUpperCase()
    if (upper === 'BEGIN:VEVENT') {
      cur = { uid: '', start: null, end: null, durMs: null, allDay: false, rrule: null, exdates: new Set(), recurrenceId: null, skip: false }
      continue
    }
    if (upper === 'END:VEVENT') {
      if (cur) events.push(cur)
      cur = null
      continue
    }
    if (!cur) continue
    const p = parseProp(line)
    if (!p) continue
    // Only time-related and status properties are read. SUMMARY, DESCRIPTION, LOCATION, ATTENDEE... never are.
    switch (p.name) {
      case 'UID': cur.uid = p.value; break
      case 'DTSTART': { const d = parseIcsDate(p.value, p.params); if (d) { cur.start = d.ms; cur.allDay = d.allDay } break }
      case 'DTEND': { const d = parseIcsDate(p.value, p.params); if (d) cur.end = d.ms; break }
      case 'DURATION': cur.durMs = parseDuration(p.value); break
      case 'RRULE': cur.rrule = p.value; break
      case 'EXDATE': for (const v of p.value.split(',')) { const d = parseIcsDate(v, p.params); if (d) cur.exdates.add(d.ms) } break
      case 'RECURRENCE-ID': cur.recurrenceId = parseIcsDate(p.value, p.params)?.ms ?? null; break
      case 'STATUS': if (p.value.toUpperCase() === 'CANCELLED') cur.skip = true; break
      case 'TRANSP': if (p.value.toUpperCase() === 'TRANSPARENT') cur.skip = true; break
    }
  }

  // an override (RECURRENCE-ID) replaces one occurrence of its series: drop that occurrence from the series
  const byUid = new Map<string, RawEvent[]>()
  for (const e of events) if (e.rrule) byUid.set(e.uid, [...(byUid.get(e.uid) ?? []), e])
  for (const e of events) if (e.recurrenceId != null) for (const s of byUid.get(e.uid) ?? []) s.exdates.add(e.recurrenceId)

  const meetings: Interval[] = []
  let skippedRecurring = 0
  let skippedAllDay = 0
  for (const e of events) {
    if (e.skip || e.start == null) continue
    if (e.allDay) { skippedAllDay++; continue }
    const dur = e.end != null ? e.end - e.start : e.durMs
    if (dur == null || dur <= 0) continue
    if (e.rrule && e.recurrenceId == null) {
      const rule = parseRule(e.rrule)
      if (rule.freq === 'DAILY' || rule.freq === 'WEEKLY') {
        meetings.push(...occurrences(e.start, dur, rule, e.exdates, from, to))
        continue
      }
      skippedRecurring++                               // monthly/yearly: only the first occurrence is counted
    }
    if (e.start + dur > from && e.start < to) meetings.push({ start: e.start, end: e.start + dur })
  }
  return { meetings: mergeIntervals(meetings.filter((m) => m.end > from && m.start < to)), skippedRecurring, skippedAllDay }
}

export function mergeIntervals(list: Interval[]): Interval[] {
  const sorted = [...list].sort((a, b) => a.start - b.start)
  const out: Interval[] = []
  for (const i of sorted) {
    const last = out[out.length - 1]
    if (last && i.start <= last.end) last.end = Math.max(last.end, i.end)
    else out.push({ ...i })
  }
  return out
}

export interface Overlap {
  meetingSeatedMin: number
  meetingSlouchPct: number | null
  otherSeatedMin: number
  otherSlouchPct: number | null
  /** meeting slouch % minus other slouch %, null until there are 60+ seated minutes in meetings. */
  diffPoints: number | null
}

const MIN_MEETING_MINUTES = 60

/** Slouch share of SEATED time during meetings vs outside them. `segments` are [start, end, code]; the
 *  grace window (D) counts as not slouching, as everywhere else in the app. */
export function overlapWithPosture(meetings: Interval[], segments: [number, number, string][]): Overlap {
  const merged = mergeIntervals(meetings)
  let inSeated = 0, inSlouch = 0, outSeated = 0, outSlouch = 0
  for (const [s, e, code] of segments) {
    if (code === 'A') continue
    let inside = 0
    for (const m of merged) {
      if (m.end <= s) continue
      if (m.start >= e) break
      inside += Math.min(e, m.end) - Math.max(s, m.start)
    }
    const outside = e - s - inside
    inSeated += inside
    outSeated += outside
    if (code === 'S') { inSlouch += inside; outSlouch += outside }
  }
  const rate = (a: number, b: number) => (b > 0 ? Math.round((1000 * a) / b) / 10 : null)
  const meetingMin = inSeated / 60_000
  const mp = meetingMin >= MIN_MEETING_MINUTES ? rate(inSlouch, inSeated) : null
  const op = rate(outSlouch, outSeated)
  return { meetingSeatedMin: Math.round(meetingMin), meetingSlouchPct: mp, otherSeatedMin: Math.round(outSeated / 60_000), otherSlouchPct: op,
           diffPoints: mp != null && op != null ? Math.round((mp - op) * 10) / 10 : null }
}

export { DAY_MS }
