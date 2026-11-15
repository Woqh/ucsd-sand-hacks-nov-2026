import { api } from './api'

export type PushState = 'unsupported' | 'denied' | 'off' | 'on'

const swUrl = () => `${import.meta.env.BASE_URL}sw.js`

function supported(): boolean {
  return 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window
}

export async function getPushState(): Promise<PushState> {
  if (!supported()) return 'unsupported'
  if (Notification.permission === 'denied') return 'denied'
  if (Notification.permission !== 'granted') return 'off'
  const reg = await navigator.serviceWorker.getRegistration(import.meta.env.BASE_URL)
  const sub = await reg?.pushManager.getSubscription()
  return sub ? 'on' : 'off'
}

function urlBase64ToUint8Array(b64: string): Uint8Array<ArrayBuffer> {
  const padded = (b64 + '='.repeat((4 - (b64.length % 4)) % 4)).replace(/-/g, '+').replace(/_/g, '/')
  const raw = atob(padded)
  const out = new Uint8Array(new ArrayBuffer(raw.length))
  for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i)
  return out
}

/** Ask permission, register /sw.js, subscribe with the server's VAPID key, send it to the API. */
export async function enableDesktopPush(): Promise<void> {
  if (!supported()) throw new Error("This browser doesn't support web push")
  const perm = await Notification.requestPermission()
  if (perm !== 'granted') throw new Error('Notifications were blocked. Allow them in your browser settings.')

  const { publicKey } = await api<{ publicKey: string | null }>('/push/web/public-key', { auth: false })
  if (!publicKey) throw new Error('The server has no VAPID key configured yet (see .env.example).')

  const reg = await navigator.serviceWorker.register(swUrl(), { scope: import.meta.env.BASE_URL })
  await navigator.serviceWorker.ready
  const sub =
    (await reg.pushManager.getSubscription()) ??
    (await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: urlBase64ToUint8Array(publicKey) }))
  await api('/push/web/subscribe', { method: 'POST', body: { subscription: sub.toJSON() } })
}
