import { useState } from 'react'
import { api } from '../../api'
import { overlapWithPosture, parseMeetings, type Overlap } from '../../coach/ics'
import type { SegmentsResponse, SettingsProposal } from '../../types'
import { Banner, Button } from '../ui'
import { ConsentBox, NotEnough, Section } from './shared'

const FIELD_LABEL: Record<string, string> = {
  slouchThresholdSec: 'Slouch threshold (seconds)',
  sensitivity: 'Sensitivity (0 forgiving, 1 strict)',
  cooldownSec: 'Cooldown between nudges (seconds)',
  nudgeTone: 'Nudge wording',
  'alertChannels.phone': 'iPhone alerts',
  'alertChannels.desktop': 'Desktop alerts',
  'quietHours.enabled': 'Quiet hours',
  'quietHours.start': 'Quiet hours start',
  'quietHours.end': 'Quiet hours end',
  'focus.onlyDuringFocus': 'Only nudge during focus sessions',
}
const fmt = (v: unknown): string => (typeof v === 'boolean' ? (v ? 'On' : 'Off') : v == null ? '–' : String(v))

/** Free-text questions about your own habits. Needs a fresh opt-in each time; nothing is stored. */
function AskCard() {
  const [q, setQ] = useState('')
  const [consent, setConsent] = useState(false)
  const [busy, setBusy] = useState(false)
  const [out, setOut] = useState<{ answer: string; basedOn: string[]; outOfScope: boolean } | null>(null)
  const [err, setErr] = useState<string | null>(null)

  async function ask() {
    setBusy(true)
    setErr(null)
    setOut(null)
    try {
      setOut(await api('/coach/ask', { method: 'POST', body: { question: q.trim(), consent: true } }))
      setConsent(false)
    } catch (e) {
      setErr((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const valid = q.trim().length >= 3 && q.trim().length <= 300
  return (
    <Section title="Ask about your habits" hint="uses Gemini">
      <p className="mb-3 text-sm text-ink-2">For example: "When do I slouch most, and what should I change?" Gemini answers only from your de-identified habit numbers and the cited research; it won't give medical advice.</p>
      <label className="block text-sm text-ink">
        <span className="sr-only">Your question</span>
        <textarea value={q} onChange={(e) => setQ(e.target.value)} maxLength={300} rows={2} placeholder="Ask a question about your sitting habits"
          className="w-full rounded-xl border border-axis bg-surface p-3 text-ink" />
      </label>
      <div className="mt-3 space-y-3">
        <ConsentBox checked={consent} onChange={setConsent}>
          Send my question and my de-identified habit numbers (the same ones shown in the profile preview) to Google's Gemini, this once.
        </ConsentBox>
        <Button disabled={!valid || !consent || busy} onClick={ask}>{busy ? 'Asking…' : 'Ask'}</Button>
      </div>
      {err && <div className="mt-3"><Banner tone="warn">{err}</Banner></div>}
      {out && (
        <div className="mt-4 rounded-xl bg-line/40 p-3 text-sm" role="status">
          <p className="text-ink">{out.answer}</p>
          {out.outOfScope && <p className="mt-2 text-xs text-ink-2">That's outside what your data and the cited research can answer.</p>}
          {out.basedOn.length > 0 && (
            <ul className="mt-2 list-disc space-y-0.5 pl-5 text-xs text-ink-2">
              {out.basedOn.map((b, i) => (
                <li key={i}>{b}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </Section>
  )
}

/** Describe your day in a sentence; get a PROPOSED settings change you can review. Nothing is applied until you confirm. */
function SettingsFromText({ onChanged }: { onChanged: () => void }) {
  const [text, setText] = useState('')
  const [consent, setConsent] = useState(false)
  const [busy, setBusy] = useState(false)
  const [prop, setProp] = useState<SettingsProposal | null>(null)
  const [msg, setMsg] = useState<{ tone: 'info' | 'warn' | 'error'; text: string } | null>(null)

  async function propose() {
    setBusy(true)
    setMsg(null)
    setProp(null)
    try {
      setProp(await api<SettingsProposal>('/coach/settings-from-text', { method: 'POST', body: { text: text.trim(), consent: true } }))
      setConsent(false)
    } catch (e) {
      setMsg({ tone: 'warn', text: (e as Error).message })
    } finally {
      setBusy(false)
    }
  }

  async function apply() {
    if (!prop) return
    setBusy(true)
    try {
      await api('/settings', { method: 'PUT', body: prop.patch })
      setProp(null)
      setText('')
      setMsg({ tone: 'info', text: 'Settings updated.' })
      onChanged()
    } catch (e) {
      setMsg({ tone: 'error', text: (e as Error).message })
    } finally {
      setBusy(false)
    }
  }

  const valid = text.trim().length >= 3 && text.trim().length <= 400
  return (
    <Section title="Set it up by describing your day" hint="uses Gemini">
      <p className="mb-3 text-sm text-ink-2">For example: "I work 9 to 6, hate being nudged in meetings, and want a firmer tone." You'll see exactly what would change, and nothing changes until you confirm.</p>
      <label className="block text-sm text-ink">
        <span className="sr-only">Describe your day</span>
        <textarea value={text} onChange={(e) => setText(e.target.value)} maxLength={400} rows={2} placeholder="Describe your day and how you like to be nudged"
          className="w-full rounded-xl border border-axis bg-surface p-3 text-ink" />
      </label>
      <div className="mt-3 space-y-3">
        <ConsentBox checked={consent} onChange={setConsent}>
          Send this sentence and my current nudge settings (no posture data) to Google's Gemini, this once.
        </ConsentBox>
        <Button disabled={!valid || !consent || busy} onClick={propose}>{busy && !prop ? 'Thinking…' : 'Propose changes'}</Button>
      </div>
      {msg && <div className="mt-3"><Banner tone={msg.tone}>{msg.text}</Banner></div>}
      {prop && (
        <div className="mt-4 space-y-3 rounded-xl border border-line p-3 text-sm">
          <p className="text-ink">{prop.explanation}</p>
          {prop.changes.length === 0 ? (
            <p className="text-ink-2">That already matches your current settings.</p>
          ) : (
            <table className="w-full text-left text-sm">
              <caption className="sr-only">Proposed settings changes</caption>
              <thead className="text-xs text-ink-2">
                <tr>
                  <th scope="col" className="py-1 font-medium">Setting</th>
                  <th scope="col" className="py-1 font-medium">Now</th>
                  <th scope="col" className="py-1 font-medium">Proposed</th>
                </tr>
              </thead>
              <tbody>
                {prop.changes.map((c) => (
                  <tr key={c.field} className="border-t border-line">
                    <td className="py-1.5 text-ink">{FIELD_LABEL[c.field] ?? c.field}</td>
                    <td className="py-1.5 text-ink-2">{fmt(c.from)}</td>
                    <td className="py-1.5 font-medium text-ink">{fmt(c.to)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <div className="flex flex-wrap gap-2">
            {prop.changes.length > 0 && <Button disabled={busy} onClick={apply}>Apply these changes</Button>}
            <Button variant="ghost" onClick={() => setProp(null)}>Discard</Button>
          </div>
        </div>
      )}
    </Section>
  )
}

/** Compare your posture in meetings vs the rest of the day, using a calendar file you pick. Read in this
 *  browser only: times are parsed, titles and attendees never are, and the file is not uploaded. */
function CalendarOverlay() {
  const [result, setResult] = useState<{ o: Overlap; meetings: number; skippedRecurring: number; skippedAllDay: number } | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  async function onFile(file: File | undefined) {
    if (!file) return
    setBusy(true)
    setErr(null)
    setResult(null)
    try {
      const [ics, seg] = await Promise.all([file.text(), api<SegmentsResponse>('/segments?days=14')])
      if (!/BEGIN:VCALENDAR/i.test(ics)) throw new Error("That doesn't look like a calendar (.ics) file.")
      const parsed = parseMeetings(ics, seg.since, seg.until)
      setResult({ o: overlapWithPosture(parsed.meetings, seg.segments), meetings: parsed.meetings.length, skippedRecurring: parsed.skippedRecurring, skippedAllDay: parsed.skippedAllDay })
    } catch (e) {
      setErr((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Section title="Meetings vs the rest of your day" hint="stays in this browser">
      <p className="mb-3 text-sm text-ink-2">
        Export your calendar as an .ics file and choose it here. Only start and end times are read (no titles, people or locations), and the file never leaves this page.
      </p>
      <label className="inline-flex min-h-11 cursor-pointer items-center rounded-xl border border-axis px-4 text-sm font-medium text-ink hover:bg-line/50 focus-within:outline focus-within:outline-2">
        {busy ? 'Reading…' : 'Choose a calendar file'}
        <input type="file" accept=".ics,text/calendar" className="sr-only" disabled={busy} onChange={(e) => { void onFile(e.target.files?.[0]); e.target.value = '' }} />
      </label>
      {err && <div className="mt-3"><Banner tone="error">{err}</Banner></div>}
      {result && (
        <div className="mt-4 text-sm" role="status">
          {result.o.diffPoints == null ? (
            <NotEnough>
              {result.meetings === 0
                ? 'No meetings from that file fall in the last 14 days.'
                : `Only ${result.o.meetingSeatedMin} minutes of seated meeting time so far; at least 60 are needed for a fair comparison.`}
            </NotEnough>
          ) : (
            <div className="rounded-xl bg-line/40 p-3">
              <p className="text-ink">
                In meetings you slouched <strong>{result.o.meetingSlouchPct}%</strong> of the time you were sitting, compared with <strong>{result.o.otherSlouchPct}%</strong> the rest of the day
                ({result.o.diffPoints > 0 ? `${result.o.diffPoints} points worse` : result.o.diffPoints < 0 ? `${Math.abs(result.o.diffPoints)} points better` : 'about the same'}).
              </p>
              <p className="mt-1 text-xs text-ink-2">{result.o.meetingSeatedMin} min seated in meetings vs {result.o.otherSeatedMin} min otherwise, last 14 days.</p>
            </div>
          )}
          {(result.skippedRecurring > 0 || result.skippedAllDay > 0) && (
            <p className="mt-2 text-xs text-ink-2">
              Skipped {result.skippedAllDay} all-day event{result.skippedAllDay === 1 ? '' : 's'} and {result.skippedRecurring} monthly or yearly recurring series (not supported).
            </p>
          )}
        </div>
      )}
    </Section>
  )
}

export default function ToolsPanel({ onChanged, aiConfigured }: { onChanged: () => void; aiConfigured: boolean }) {
  return (
    <div className="space-y-4">
      {aiConfigured ? (
        <>
          <AskCard />
          <SettingsFromText onChanged={onChanged} />
        </>
      ) : (
        <Section title="Gemini tools">
          <NotEnough>Asking questions and describing your day in words need Gemini, which isn't switched on for this server. Everything else on this page works without it.</NotEnough>
        </Section>
      )}
      <CalendarOverlay />
    </div>
  )
}
