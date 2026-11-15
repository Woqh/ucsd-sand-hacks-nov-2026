import { describe, expect, it } from 'vitest'
import { mergeIntervals, overlapWithPosture, parseIcsDate, parseMeetings } from './ics'

const FROM = new Date(2024, 9, 1).getTime()
const TO = new Date(2024, 11, 31).getTime()
const wrap = (...events: string[]) => `BEGIN:VCALENDAR\r\nVERSION:2.0\r\n${events.join('\r\n')}\r\nEND:VCALENDAR`
const ev = (...lines: string[]) => ['BEGIN:VEVENT', ...lines, 'END:VEVENT'].join('\r\n')
const local = (y: number, m: number, d: number, h = 0, mi = 0) => new Date(y, m - 1, d, h, mi).getTime()
const starts = (ics: string) => parseMeetings(ics, FROM, TO).meetings.map((m) => m.start)

describe('parseIcsDate', () => {
  it('reads UTC, floating and all-day values', () => {
    expect(parseIcsDate('20241115T150000Z')).toEqual({ ms: Date.UTC(2024, 10, 15, 15), allDay: false })
    expect(parseIcsDate('20241115T090000')).toEqual({ ms: local(2024, 11, 15, 9), allDay: false })
    expect(parseIcsDate('20241115', 'VALUE=DATE')?.allDay).toBe(true)
    expect(parseIcsDate('nonsense')).toBeNull()
  })
})

describe('single events', () => {
  const ics = wrap(
    ev('UID:a', 'DTSTART:20241115T150000Z', 'DTEND:20241115T160000Z', 'SUMMARY:Secret board meeting', 'LOCATION:Room 5', 'ATTENDEE:mailto:boss@example.com'),
    ev('UID:b', 'DTSTART:20241115T090000', 'DTEND:20241115T093000'),
    ev('UID:c', 'DTSTART;VALUE=DATE:20241115', 'DTEND;VALUE=DATE:20241116'),
    ev('UID:d', 'DTSTART:20241115T120000Z', 'DTEND:20241115T130000Z', 'TRANSP:TRANSPARENT'),
    ev('UID:e', 'DTSTART:20241115T170000Z', 'DTEND:20241115T180000Z', 'STATUS:CANCELLED'),
    ev('UID:f', 'DTSTART:20241115T200000Z', 'DURATION:PT1H30M'),
    ev('UID:g', 'DTSTART:20241115T210000Z'), // no end and no duration: unusable
  )

  it('keeps timed, busy, confirmed events and reports what it skipped', () => {
    const r = parseMeetings(ics, FROM, TO)
    expect(r.skippedAllDay).toBe(1)
    const got = r.meetings.map((m) => [m.start, m.end])
    expect(got).toContainEqual([Date.UTC(2024, 10, 15, 15), Date.UTC(2024, 10, 15, 16)])
    expect(got).toContainEqual([local(2024, 11, 15, 9), local(2024, 11, 15, 9, 30)])
    expect(got).toContainEqual([Date.UTC(2024, 10, 15, 20), Date.UTC(2024, 10, 15, 21, 30)]) // DURATION
    expect(got).toHaveLength(3) // not the all-day, "free", cancelled or end-less ones
  })

  it('never exposes titles, locations or attendees', () => {
    const text = JSON.stringify(parseMeetings(ics, FROM, TO))
    for (const secret of ['Secret', 'Room 5', 'boss@example.com']) expect(text).not.toContain(secret)
  })

  it('handles folded lines and ignores events outside the range', () => {
    const folded = wrap(ev('UID:z', 'DTSTART:2024111\r\n 5T150000Z', 'DTEND:20241115T160000Z'), ev('UID:y', 'DTSTART:20200101T100000Z', 'DTEND:20200101T110000Z'))
    expect(parseMeetings(folded, FROM, TO).meetings).toHaveLength(1)
  })
})

describe('recurrence', () => {
  const series = (...extra: string[]) => wrap(ev('UID:s', 'DTSTART:20241104T100000', 'DTEND:20241104T110000', ...extra)) // a Monday

  it('expands weekly BYDAY with COUNT', () => {
    expect(starts(series('RRULE:FREQ=WEEKLY;BYDAY=MO,WE;COUNT=4'))).toEqual([
      local(2024, 11, 4, 10), local(2024, 11, 6, 10), local(2024, 11, 11, 10), local(2024, 11, 13, 10)])
  })

  it('honours INTERVAL, UNTIL and EXDATE', () => {
    expect(starts(series('RRULE:FREQ=WEEKLY;BYDAY=MO;INTERVAL=2;COUNT=3'))).toEqual([local(2024, 11, 4, 10), local(2024, 11, 18, 10), local(2024, 12, 2, 10)])
    expect(starts(series('RRULE:FREQ=WEEKLY;BYDAY=MO,WE;UNTIL=20241112T000000Z'))).toEqual([local(2024, 11, 4, 10), local(2024, 11, 6, 10), local(2024, 11, 11, 10)])
    expect(starts(series('RRULE:FREQ=WEEKLY;BYDAY=MO,WE;COUNT=4', 'EXDATE:20241106T100000'))).toEqual([local(2024, 11, 4, 10), local(2024, 11, 11, 10), local(2024, 11, 13, 10)])
  })

  it('defaults a weekly rule to the start weekday, and expands daily rules', () => {
    expect(starts(series('RRULE:FREQ=WEEKLY;COUNT=3'))).toEqual([local(2024, 11, 4, 10), local(2024, 11, 11, 10), local(2024, 11, 18, 10)])
    expect(starts(series('RRULE:FREQ=DAILY;COUNT=3'))).toEqual([local(2024, 11, 4, 10), local(2024, 11, 5, 10), local(2024, 11, 6, 10)])
  })

  it('replaces one occurrence with its RECURRENCE-ID override', () => {
    const ics = wrap(
      ev('UID:s', 'DTSTART:20241104T100000', 'DTEND:20241104T110000', 'RRULE:FREQ=WEEKLY;COUNT=3'),
      ev('UID:s', 'RECURRENCE-ID:20241111T100000', 'DTSTART:20241111T140000', 'DTEND:20241111T150000'))
    expect(starts(ics)).toEqual([local(2024, 11, 4, 10), local(2024, 11, 11, 14), local(2024, 11, 18, 10)])
  })

  it('counts monthly/yearly series as skipped and keeps only their first occurrence', () => {
    const r = parseMeetings(series('RRULE:FREQ=MONTHLY;COUNT=5'), FROM, TO)
    expect(r.skippedRecurring).toBe(1)
    expect(r.meetings).toHaveLength(1)
  })

  it('does not run away on an endless old series', () => {
    const t0 = Date.now()
    const r = parseMeetings(wrap(ev('UID:old', 'DTSTART:20150105T100000', 'DTEND:20150105T110000', 'RRULE:FREQ=DAILY')), FROM, TO)
    expect(Date.now() - t0).toBeLessThan(2000)
    expect(r.meetings.length).toBeLessThanOrEqual(4001)
  })
})

describe('mergeIntervals', () => {
  it('merges overlapping and touching intervals', () => {
    expect(mergeIntervals([{ start: 10, end: 20 }, { start: 0, end: 5 }, { start: 15, end: 30 }, { start: 30, end: 40 }])).toEqual([
      { start: 0, end: 5 }, { start: 10, end: 40 }])
  })
})

describe('overlapWithPosture', () => {
  const MIN = 60_000
  type Seg = [number, number, string]

  it('compares slouch share in meetings with the rest of the seated time', () => {
    const segs: Seg[] = [[0, 60 * MIN, 'G'], [60 * MIN, 120 * MIN, 'S'], [120 * MIN, 200 * MIN, 'A']]
    const o = overlapWithPosture([{ start: 60 * MIN, end: 120 * MIN }], segs)
    expect(o).toEqual({ meetingSeatedMin: 60, meetingSlouchPct: 100, otherSeatedMin: 60, otherSlouchPct: 0, diffPoints: 100 })
  })

  it('splits segments that straddle a meeting edge and ignores away time', () => {
    const segs: Seg[] = [[0, 120 * MIN, 'S']]
    const o = overlapWithPosture([{ start: 30 * MIN, end: 90 * MIN }, { start: 60 * MIN, end: 100 * MIN }], segs) // overlapping meetings merge
    expect(o.meetingSeatedMin).toBe(70)
    expect(o.otherSeatedMin).toBe(50)
    expect(overlapWithPosture([{ start: 0, end: 60 * MIN }], [[0, 60 * MIN, 'A']]).meetingSeatedMin).toBe(0)
  })

  it('stays quiet until there are 60 minutes of meetings to learn from', () => {
    const o = overlapWithPosture([{ start: 0, end: 30 * MIN }], [[0, 120 * MIN, 'S']])
    expect(o.meetingSlouchPct).toBeNull()
    expect(o.diffPoints).toBeNull()
    expect(o.otherSlouchPct).toBe(100)
  })

  it('treats the grace window (D) as not slouching', () => {
    const o = overlapWithPosture([{ start: 0, end: 60 * MIN }], [[0, 60 * MIN, 'D']])
    expect(o.meetingSlouchPct).toBe(0)
  })
})
