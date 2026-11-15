// Notifications the dashboard shows by itself while it is open: no push keys, no server round trip. The server
// still decides WHEN to nudge (threshold, cooldown, quiet hours, focus mode); this only displays it. For
// notifications when the tab is closed, use Web Push instead (push.ts, "Enable on this computer").

const FLAG = 'sitwise.localAlerts'
export const ALERTS_EVENT = 'sitwise:local-alerts'
const swScope = () => import.meta.env.BASE_URL
const swUrl = () => `${import.meta.env.BASE_URL}sw.js`

export type LocalAlertState = 'unsupported' | 'denied' | 'off' | 'on'

// Remembered in localStorage; if storage is blocked, for this page load only.
let memory = false
function readFlag(): boolean {
  try {
    const v = localStorage.getItem(FLAG)
    return v == null ? memory : v === 'on'
  } catch {
    return memory
  }
}
function writeFlag(on: boolean): void {
  memory = on
  try {
    localStorage.setItem(FLAG, on ? 'on' : 'off')
  } catch {
    /* blocked: keep it in memory */
  }
  window.dispatchEvent(new Event(ALERTS_EVENT))
}

/** `unsupported` where there is no Notification API (e.g. an iPhone Safari tab), `denied` if the user blocked
 *  them, `on` only when permission is granted AND they have not switched it off. */
export function localAlertState(): LocalAlertState {
  if (typeof Notification === 'undefined') return 'unsupported'
  if (Notification.permission === 'denied') return 'denied'
  return Notification.permission === 'granted' && readFlag() ? 'on' : 'off'
}

/** Whether it is worth asking: supported and the browser has not been asked yet. */
export function canAskForAlerts(): boolean {
  return typeof Notification !== 'undefined' && Notification.permission === 'default'
}

/** Must be called from a click: browsers only show the permission prompt for a user gesture. */
export async function enableLocalAlerts(): Promise<void> {
  if (typeof Notification === 'undefined') throw new Error("This browser can't show notifications.")
  if (Notification.permission !== 'granted') {
    const perm = await Notification.requestPermission()
    if (perm !== 'granted') throw new Error('Notifications were blocked. Allow them in your browser settings for this site.')
  }
  try {
    // A registration lets the notification show even when the tab is in the background (and on Android).
    if ('serviceWorker' in navigator) {
      await navigator.serviceWorker.register(swUrl(), { scope: swScope() })
      await navigator.serviceWorker.ready
    }
  } catch {
    /* fine: falls back to a plain Notification */
  }
  writeFlag(true)
}

export function disableLocalAlerts(): void {
  writeFlag(false)
}

/** Show a notification now. Uses the service worker when there is one; the shared `posture` tag makes a Web Push
 *  notification for the same nudge replace this one instead of stacking. */
export async function showAlert(title: string, body: string): Promise<void> {
  const options = { body, tag: 'posture', renotify: true, vibrate: [200, 100, 200], data: { url: swScope() } } as NotificationOptions
  try {
    const reg = 'serviceWorker' in navigator ? await navigator.serviceWorker.getRegistration(swScope()) : undefined
    if (reg?.active) {
      await reg.showNotification(title, options)
      return
    }
  } catch {
    /* fall through to a plain Notification */
  }
  const n = new Notification(title, options)
  n.onclick = () => {
    window.focus()
    n.close()
  }
}
