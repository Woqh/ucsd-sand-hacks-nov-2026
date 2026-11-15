import type { PostureState, Tone } from './types'

// The wording of a nudge by tone and level (1 = first nudge, 2 and 3 = gentle escalations). Mirrors
// api/push/dispatch.py MESSAGES_BY_TONE: change both together. The server picks the wording for pushes it
// sends; the dashboard uses this for the notification it shows itself while the page is open.
export const NUDGE_MESSAGES: Record<Tone, Record<1 | 2 | 3, { title: string; body: string }>> = {
  gentle: {
    1: { title: 'Sit up tall', body: "You've been slouching a little. Roll your shoulders back and reset." },
    2: { title: 'Still slouching', body: 'Quick fix: chin tuck, shoulders down, feet flat.' },
    3: { title: 'Take a stretch break?', body: 'Stand up for a minute. Your back will thank you.' },
  },
  neutral: {
    1: { title: 'Posture check', body: "You've been slouching for a bit. Time to sit back up." },
    2: { title: 'Still slouching', body: "You're still out of your goal posture." },
    3: { title: 'Time for a break', body: "You've been slouching for a while. Stand up and move." },
  },
  direct: {
    1: { title: 'Sit up.', body: 'Slouching. Back straight, shoulders down.' },
    2: { title: 'Sit up now.', body: 'Still slouching. Reset your posture.' },
    3: { title: 'Break.', body: 'Stand up and walk. Now.' },
  },
}

export function messageFor(tone: Tone | undefined, level: number): { title: string; body: string } {
  const table = NUDGE_MESSAGES[tone ?? 'gentle'] ?? NUDGE_MESSAGES.gentle
  return table[Math.min(3, Math.max(1, Math.round(level))) as 1 | 2 | 3]
}

export interface Watched {
  state: PostureState
  alertsSent: number
}

/** Did the server just send a nudge? `alertsSent` counts the nudges of the current slouch (1, 2, 3, back to 0
 *  once you recover), so a rise while SLOUCHING is a new nudge, and its new value is the nudge's level. The server
 *  already applied the threshold, cooldown, quiet hours and focus mode, so this adds no rules of its own.
 *  The first look (`prev` null) never fires: something that happened before this page was open isn't news. */
export function detectAlert(prev: Watched | null, cur: Watched): 1 | 2 | 3 | null {
  if (!prev) return null
  if (cur.state !== 'SLOUCHING' || cur.alertsSent <= prev.alertsSent) return null
  return Math.min(3, Math.max(1, cur.alertsSent)) as 1 | 2 | 3
}
