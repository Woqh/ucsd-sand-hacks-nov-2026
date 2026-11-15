import { describe, expect, it } from 'vitest'
import { detectAlert, messageFor, NUDGE_MESSAGES, type Watched } from './alertRules'

const w = (state: Watched['state'], alertsSent: number): Watched => ({ state, alertsSent })

describe('detectAlert: when the server has just nudged you', () => {
  it('fires on the first nudge of a slouch, and on each escalation', () => {
    expect(detectAlert(w('SLOUCHING', 0), w('SLOUCHING', 1))).toBe(1)
    expect(detectAlert(w('SLOUCHING', 1), w('SLOUCHING', 2))).toBe(2)
    expect(detectAlert(w('SLOUCHING', 2), w('SLOUCHING', 3))).toBe(3)
  })

  it('also fires when the nudge arrives in the same poll that first shows the slouch', () => {
    expect(detectAlert(w('DEVIATING', 0), w('SLOUCHING', 1))).toBe(1)
  })

  it('never fires on the first look, even if you are already slouching', () => {
    expect(detectAlert(null, w('SLOUCHING', 2))).toBeNull()
  })

  it('stays quiet when nothing new was sent', () => {
    expect(detectAlert(w('SLOUCHING', 1), w('SLOUCHING', 1))).toBeNull()
    expect(detectAlert(w('GOOD', 0), w('GOOD', 0))).toBeNull()
    expect(detectAlert(w('DEVIATING', 0), w('DEVIATING', 0))).toBeNull()
  })

  it('stays quiet when you recover (the count resets to 0)', () => {
    expect(detectAlert(w('SLOUCHING', 2), w('GOOD', 0))).toBeNull()
  })

  it('does not fire for a rise that is not a slouch (e.g. you left the chair)', () => {
    expect(detectAlert(w('SLOUCHING', 1), w('AWAY', 2))).toBeNull()
  })

  it('fires for a new slouch after a recovery', () => {
    const afterRecovery = w('GOOD', 0)
    expect(detectAlert(afterRecovery, w('SLOUCHING', 1))).toBe(1)
  })

  it('clamps a level above 3', () => {
    expect(detectAlert(w('SLOUCHING', 3), w('SLOUCHING', 4))).toBe(3)
  })
})

describe('messageFor', () => {
  it('uses the chosen tone and level', () => {
    expect(messageFor('direct', 1).title).toBe('Sit up.')
    expect(messageFor('neutral', 3).title).toBe('Time for a break')
  })
  it('falls back to gentle for an unknown or missing tone, and clamps the level', () => {
    expect(messageFor(undefined, 1)).toEqual(NUDGE_MESSAGES.gentle[1])
    expect(messageFor('shouty' as never, 2)).toEqual(NUDGE_MESSAGES.gentle[2])
    expect(messageFor('gentle', 0)).toEqual(NUDGE_MESSAGES.gentle[1])
    expect(messageFor('gentle', 9)).toEqual(NUDGE_MESSAGES.gentle[3])
  })
  it('has distinct wording per level in every tone', () => {
    for (const tone of Object.values(NUDGE_MESSAGES)) expect(new Set([1, 2, 3].map((l) => tone[l as 1 | 2 | 3].title)).size).toBe(3)
  })
})
