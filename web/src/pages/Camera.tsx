import { useCallback, useEffect, useRef, useState } from 'react'
import DataConsent from '../components/DataConsent'
import { api, ApiError } from '../api'
import { Banner, Button, Card, CardTitle, Meter, Segmented, STATE_META, StatePill, Toggle } from '../components/ui'
import { FRAME_MAX_SIDE, model, type ModelOutput } from '../model'
import type { PairCreateResponse, PostureState } from '../types'

// Laptop camera path: this browser tab reads a webcam (e.g. the iPhone through Camo), hands a frame
// to the model about once a second (web/src/model.ts) and can post the result to /posture/ingest,
// standing in for the phone. Frames go only to the local model; dashboard uploads contain readings.

const CAMERA_KEY = 'sitwise.cameraId'
const DEVICE_TOKEN_KEY = 'sitwise.cameraDeviceToken'
const FACING_KEY = 'sitwise.cameraFacing'
const INTERVAL_MS = 1000
type Facing = 'left' | 'right' | 'auto'

const load = (k: string): string | null => {
  try {
    return localStorage.getItem(k)
  } catch {
    return null
  }
}
const save = (k: string, v: string | null): void => {
  try {
    if (v == null) localStorage.removeItem(k)
    else localStorage.setItem(k, v)
  } catch {
    /* storage blocked: just not remembered */
  }
}

function cameraErrorMessage(e: unknown): string {
  const name = (e as { name?: string })?.name
  if (name === 'NotAllowedError') return 'Camera permission was denied. Allow the camera for this site in the address bar, then try again.'
  if (name === 'NotFoundError' || name === 'OverconstrainedError') return 'That camera was not found. Is Camo Studio running with the phone connected?'
  if (name === 'NotReadableError') return 'The camera is in use by another app (Zoom, Teams, the camera test script?). Close it and try again.'
  if (!navigator.mediaDevices) return 'This browser cannot open cameras here. Use http://localhost or https.'
  return `Could not open the camera: ${(e as Error)?.message ?? e}`
}

/** The part of the frame that holds the picture, as fractions of the frame (0..1). */
interface Crop {
  x0: number
  y0: number
  x1: number
  y1: number
}
const FULL: Crop = { x0: 0, y0: 0, x1: 1, y1: 1 }
const PROBE_WIDTH = 320
const BAR_LUMA = 28 // a pixel darker than this counts as bar; covers pure black and "video black" (16)
const LIT_SHARE = 0.25 // a column/row belongs to the picture when at least this share of it is lit
const CROP_MEMORY = 5 // detections kept; the crop is their union, so one dark frame can't clip the picture

/** Longest run of `true` in `on`, bridging gaps up to `gap` long. Returns [start, end). */
function longestRun(on: boolean[], gap: number): [number, number] {
  let best: [number, number] = [0, 0]
  let start = -1
  let last = -1
  for (let i = 0; i <= on.length; i++) {
    if (i < on.length && on[i]) {
      if (start < 0) start = i
      last = i
    } else if (start >= 0 && (i === on.length || i - last > gap)) {
      if (last + 1 - start > best[1] - best[0]) best = [start, last + 1]
      start = -1
    }
  }
  return best
}

/** Webcam feeds are always landscape, so a phone standing upright arrives as a tall picture with
 *  dark bars either side (Camo does this). Finds the picture inside the bars so the page can show,
 *  and the model can get, just the vertical picture. A column counts as picture only when a good
 *  share of it is lit, so a logo or watermark sitting in a bar doesn't make the bar look like
 *  picture. Null = nothing found (no feed yet, or a very dark scene). */
function findPicture(el: HTMLVideoElement, canvas: HTMLCanvasElement): Crop | null {
  const w = PROBE_WIDTH
  const h = Math.max(1, Math.round((PROBE_WIDTH * el.videoHeight) / el.videoWidth))
  canvas.width = w
  canvas.height = h
  const ctx = canvas.getContext('2d', { willReadFrequently: true })
  if (!ctx) return null
  ctx.drawImage(el, 0, 0, w, h)
  const px = ctx.getImageData(0, 0, w, h).data
  const lit = new Uint8Array(w * h)
  const cols = new Uint16Array(w)
  for (let y = 0, i = 0, p = 0; y < h; y++) {
    for (let x = 0; x < w; x++, i += 4, p++) {
      if (0.299 * px[i] + 0.587 * px[i + 1] + 0.114 * px[i + 2] > BAR_LUMA) {
        lit[p] = 1
        cols[x]++
      }
    }
  }
  const [x0, x1] = longestRun(Array.from(cols, (n) => n / h >= LIT_SHARE), Math.ceil(w * 0.02))
  if (x1 - x0 < w * 0.1) return null
  const rows: boolean[] = []
  for (let y = 0; y < h; y++) {
    let n = 0
    for (let x = x0; x < x1; x++) n += lit[y * w + x]
    rows.push(n / (x1 - x0) >= LIT_SHARE)
  }
  const [y0, y1] = longestRun(rows, Math.ceil(h * 0.02))
  if (y1 - y0 < h * 0.1) return null
  return { x0: x0 / w, y0: y0 / h, x1: x1 / w, y1: y1 / h }
}

const PORTRAIT = 9 / 16 // width / height of the view the page always shows

/** The page always shows a vertical view. If the picture (bars already trimmed) is still wider than
 *  tall, keep its full height and take the centred 9:16 strip of it. */
function toPortrait(c: Crop, vw: number, vh: number): Crop {
  const pw = (c.x1 - c.x0) * vw
  const ph = (c.y1 - c.y0) * vh
  if (pw <= ph) return c
  const half = (ph * PORTRAIT) / vw / 2
  const mid = (c.x0 + c.x1) / 2
  return { ...c, x0: mid - half, x1: mid + half }
}

export default function Camera() {
  const videoRef = useRef<HTMLVideoElement>(null)
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const probeRef = useRef<HTMLCanvasElement | null>(null)
  const cropsRef = useRef<Crop[]>([])
  const [crop, setCrop] = useState<Crop>(FULL)
  const streamRef = useRef<MediaStream | null>(null)
  const sessionRef = useRef<string>('')
  const busyRef = useRef(false)

  const [devices, setDevices] = useState<MediaDeviceInfo[]>([])
  const [deviceId, setDeviceId] = useState<string>(() => load(CAMERA_KEY) ?? '')
  const [running, setRunning] = useState(false)
  const [starting, setStarting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [info, setInfo] = useState<{ label: string; w: number; h: number } | null>(null)

  const [out, setOut] = useState<ModelOutput | null>(null)
  const [modelError, setModelError] = useState<string | null>(null)
  const [frames, setFrames] = useState(0)

  const [send, setSend] = useState(false)
  const [sendBusy, setSendBusy] = useState(false)
  const [sendError, setSendError] = useState<string | null>(null)
  const [serverState, setServerState] = useState<PostureState | null>(null)
  const sendRef = useRef(false)
  sendRef.current = send

  // Which way you face in the picture (where your nose points): the model can't guess it from a side view
  // without your feet in frame, and a wrong value flips forward and backward. Unset until you choose.
  const [facing, setFacing] = useState<Facing | ''>(() => (load(FACING_KEY) as Facing | null) ?? '')
  const facingRef = useRef<Facing | ''>(facing)
  facingRef.current = facing

  const stop = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop())
    streamRef.current = null
    if (videoRef.current) videoRef.current.srcObject = null
    setRunning(false)
    setInfo(null)
    setServerState(null)
  }, [])

  useEffect(() => stop, [stop]) // release the camera when leaving the page

  const start = useCallback(
    async (id: string) => {
      setStarting(true)
      setError(null)
      stop()
      try {
        if (!navigator.mediaDevices) throw new Error('no mediaDevices')
        const video: MediaTrackConstraints = { width: { ideal: 1280 }, height: { ideal: 720 } }
        if (id) video.deviceId = { exact: id }
        let stream: MediaStream
        try {
          stream = await navigator.mediaDevices.getUserMedia({ video, audio: false })
        } catch (e) {
          // A remembered camera that's gone (ids change, Camo closed): fall back to the default one.
          if (!id || (e as { name?: string }).name === 'NotAllowedError') throw e
          stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false })
        }
        // Labels are only readable once permission is granted, so list cameras after opening one.
        const cams = (await navigator.mediaDevices.enumerateDevices()).filter((d) => d.kind === 'videoinput')
        setDevices(cams)
        let track = stream.getVideoTracks()[0]
        // First run: prefer the Camo virtual camera over the built-in webcam.
        const camo = cams.find((d) => /camo/i.test(d.label))
        if (!id && camo && track.getSettings().deviceId !== camo.deviceId) {
          try {
            const s2 = await navigator.mediaDevices.getUserMedia({ video: { ...video, deviceId: { exact: camo.deviceId } }, audio: false })
            stream.getTracks().forEach((t) => t.stop())
            stream = s2
            track = stream.getVideoTracks()[0]
          } catch {
            /* keep the default camera */
          }
        }
        streamRef.current = stream
        const used = track.getSettings().deviceId ?? ''
        setDeviceId(used)
        save(CAMERA_KEY, used || null)
        const el = videoRef.current
        if (el) {
          el.srcObject = stream
          await el.play().catch(() => {})
          setInfo({ label: track.label || 'Camera', w: el.videoWidth, h: el.videoHeight })
        }
        track.addEventListener('ended', () => {
          setError('The camera feed ended (unplugged, or Camo Studio closed).')
          stop()
        })
        sessionRef.current = crypto.randomUUID()
        cropsRef.current = []
        setCrop(FULL)
        setFrames(0)
        setOut(null)
        setModelError(null)
        await model.load?.()
        setRunning(true)
      } catch (e) {
        stop()
        setError(cameraErrorMessage(e))
      } finally {
        setStarting(false)
      }
    },
    [stop],
  )

  // ~1 Hz: frame -> model -> (optionally) /posture/ingest. One at a time; a slow model skips ticks.
  useEffect(() => {
    if (!running) return
    const tick = async () => {
      const el = videoRef.current
      if (busyRef.current || !el || el.readyState < 2 || !el.videoWidth) return
      busyRef.current = true
      try {
        // Trim the black bars: the preview and the model both get only the picture.
        const found = findPicture(el, (probeRef.current ??= document.createElement('canvas')))
        if (found) cropsRef.current = [...cropsRef.current.slice(1 - CROP_MEMORY), found]
        const seen = cropsRef.current
        const picture: Crop = seen.length
          ? { x0: Math.min(...seen.map((s) => s.x0)), y0: Math.min(...seen.map((s) => s.y0)), x1: Math.max(...seen.map((s) => s.x1)), y1: Math.max(...seen.map((s) => s.y1)) }
          : FULL
        const c = toPortrait(picture, el.videoWidth, el.videoHeight)
        setCrop((p) => (Math.max(Math.abs(p.x0 - c.x0), Math.abs(p.y0 - c.y0), Math.abs(p.x1 - c.x1), Math.abs(p.y1 - c.y1)) > 0.004 ? c : p))

        const sx = c.x0 * el.videoWidth
        const sy = c.y0 * el.videoHeight
        const sw = (c.x1 - c.x0) * el.videoWidth
        const sh = (c.y1 - c.y0) * el.videoHeight
        const scale = Math.min(1, FRAME_MAX_SIDE / Math.max(sw, sh))
        const w = Math.max(1, Math.round(sw * scale))
        const h = Math.max(1, Math.round(sh * scale))
        const canvas = (canvasRef.current ??= document.createElement('canvas'))
        canvas.width = w
        canvas.height = h
        const ctx = canvas.getContext('2d', { willReadFrequently: true })
        if (!ctx) throw new Error('Canvas is unavailable')
        ctx.drawImage(el, sx, sy, sw, sh, 0, 0, w, h)
        const t = Date.now()
        const result = await model.analyze(ctx.getImageData(0, 0, w, h), t, { facing: facingRef.current || 'auto', goal: null })
        setOut(result)
        setModelError(null)
        setFrames((n) => n + 1)
        setInfo((i) => (i && (i.w !== el.videoWidth || i.h !== el.videoHeight) ? { ...i, w: el.videoWidth, h: el.videoHeight } : i))

        const token = load(DEVICE_TOKEN_KEY)
        if (sendRef.current && token) {
          try {
            const r = await api<{ state: PostureState }>('/posture/ingest', {
              method: 'POST',
              token,
              body: { schema: 1, sessionId: sessionRef.current, t, label: result.label, deviation: result.deviation, confidence: result.confidence, features: result.features, ...(result.source ? { source: result.source } : {}) },
            })
            setServerState(r.state)
            setSendError(null)
          } catch (e) {
            if (e instanceof ApiError && e.code === 'collection_consent_required') {
              sendRef.current = false
              setSend(false)
              setServerState(null)
              setSendError(e.message)
            } else if (e instanceof ApiError && e.status === 401) {
              // Another device was paired since; this tab is no longer "the phone".
              save(DEVICE_TOKEN_KEY, null)
              setSend(false)
              setServerState(null)
              setSendError('This computer is no longer the paired device (a phone was paired since). Turn sending on again to take over.')
            } else {
              setSendError((e as Error).message)
            }
          }
        }
      } catch (e) {
        setModelError((e as Error).message)
      } finally {
        busyRef.current = false
      }
    }
    tick() // straight away, so the bars are trimmed as soon as the picture appears
    const id = setInterval(tick, INTERVAL_MS)
    return () => clearInterval(id)
  }, [running])

  async function toggleSend(on: boolean) {
    setSendError(null)
    if (!on) {
      sendRef.current = false
      setSend(false)
      setServerState(null)
      return
    }
    const { settings } = await api<{ settings: { dataCollectionConsent: boolean } }>('/settings').catch(() => ({ settings: { dataCollectionConsent: false } }))
    if (!settings.dataCollectionConsent) {
      setSendError('Please allow data collection above before sending readings.')
      return
    }
    if (load(DEVICE_TOKEN_KEY)) {
      setSend(true)
      return
    }
    // Pair this tab as the device, the same two calls a phone makes with the on-screen code.
    setSendBusy(true)
    try {
      const { pairingCode } = await api<PairCreateResponse>('/pair/create', { method: 'POST' })
      const { deviceToken } = await api<{ deviceToken: string }>('/pair/claim', { method: 'POST', auth: false, body: { code: pairingCode } })
      save(DEVICE_TOKEN_KEY, deviceToken)
      setSend(true)
    } catch (e) {
      setSendError((e as Error).message)
    } finally {
      setSendBusy(false)
    }
  }

  function changeFacing(f: Facing) {
    setFacing(f)
    save(FACING_KEY, f)
  }

  // The preview box takes the shape of the picture inside the frame (bars trimmed), so an upright
  // phone shows as a tall portrait view. (cw x ch) is that picture in feed pixels.
  const vw = info?.w || 16
  const vh = info?.h || 9
  // Before the first frame is measured, assume a landscape feed and show the centred portrait strip.
  const shown = running ? crop : toPortrait(crop, vw, vh)
  const fx = shown.x1 - shown.x0
  const fy = shown.y1 - shown.y0
  const cw = Math.round(vw * fx)
  const ch = Math.round(vh * fy)

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-ink">Camera</h1>
        <p className="mt-1 text-sm text-ink-2">
          Use a camera on this computer (for example your iPhone through Camo) instead of the iPhone app. Frames are processed by the local model on this computer and are not stored. Allow data collection below to save posture readings to your dashboard.
        </p>
      </div>

      {error && <Banner tone="error">{error}</Banner>}

      <div className="grid gap-3 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <Card>
          <CardTitle hint={info ? `showing ${cw}×${ch} of ${vw}×${vh}` : undefined}>{info?.label ?? 'Camera feed'}</CardTitle>
          <div>
            {/* Capped at 75% of the window height so a tall portrait feed fits on screen head to chair base. */}
            <div className="relative mx-auto overflow-hidden rounded-xl bg-black" style={{ aspectRatio: `${cw} / ${ch}`, width: `min(100%, calc(75vh * ${cw / ch}))` }}>
              {/* The video is oversized and shifted so only the picture (not the bars) is inside the box. */}
              <video
                ref={videoRef}
                muted
                playsInline
                aria-label="Live camera preview"
                className="absolute max-w-none object-fill"
                style={{ width: `${100 / fx}%`, height: `${100 / fy}%`, left: `${(-shown.x0 / fx) * 100}%`, top: `${(-shown.y0 / fy) * 100}%` }}
              />
              {!running && (
                <div className="absolute inset-0 flex items-center justify-center p-4 text-center text-sm text-white/80">
                  {starting ? 'Opening the camera…' : 'Camera is off'}
                </div>
              )}
            </div>
          </div>

          <div className="mt-3 flex flex-wrap items-center gap-2">
            {running ? (
              <Button variant="secondary" onClick={stop}>Stop camera</Button>
            ) : (
              <Button onClick={() => start(deviceId)} disabled={starting}>Start camera</Button>
            )}
            {devices.length > 0 && (
              <label className="flex min-w-0 flex-1 items-center gap-2 text-sm text-ink-2">
                <span className="shrink-0">Source</span>
                <select
                  value={deviceId}
                  onChange={(e) => start(e.target.value)}
                  disabled={starting}
                  className="min-h-11 min-w-0 flex-1 rounded-xl border border-axis bg-surface px-3 text-sm text-ink"
                >
                  {devices.map((d, i) => (
                    <option key={d.deviceId} value={d.deviceId}>
                      {d.label || `Camera ${i + 1}`}
                    </option>
                  ))}
                </select>
              </label>
            )}
          </div>
          <p className="mt-3 text-xs text-ink-2">
            Black picture from Camo? Keep Camo Studio open with the phone connected. The view is always vertical: black bars are trimmed, and a wide picture is cropped to its centre.
          </p>
        </Card>

        <div className="space-y-3">
          <Card>
            <CardTitle hint={running ? `${frames} frame${frames === 1 ? '' : 's'} analysed` : undefined}>Model reading</CardTitle>
            <p className="mb-3 text-xs text-ink-2">Model: {model.name}</p>
            {out?.stub && (
              <div className="mb-3">
                <Banner tone="warn">Placeholder model: this is not a real posture reading yet.</Banner>
              </div>
            )}
            {modelError && (
              <div className="mb-3">
                <Banner tone="error">Model error: {modelError}</Banner>
              </div>
            )}
            {out && running ? (
              <div className="space-y-3 text-sm">
                <div className="flex items-center justify-between gap-3">
                  <span className="text-lg font-semibold text-ink">{out.label}</span>
                  <span className="text-ink-2">
                    {Math.round(out.confidence * 100)}% confidence{out.inferenceMs != null ? ` · ${Math.round(out.inferenceMs)} ms` : ''}
                  </span>
                </div>
                {out.note && <p className="text-xs text-ink-2">{out.note}</p>}
                <div>
                  <div className="mb-1 flex justify-between text-ink-2">
                    <span>Deviation from upright posture</span>
                    <span className="text-ink">{out.deviation.toFixed(2)}</span>
                  </div>
                  <Meter value={Math.min(1, out.deviation)} max={1} label="Deviation from upright posture" />
                </div>
                <dl className="grid grid-cols-3 gap-2 text-center">
                  {Object.entries(out.features).map(([k, v]) => (
                    <div key={k} className="rounded-xl bg-line/40 px-2 py-2">
                      <dt className="truncate text-xs text-ink-2">{k}</dt>
                      <dd className="font-medium text-ink">{v ?? '–'}</dd>
                    </div>
                  ))}
                </dl>
              </div>
            ) : (
              <p className="text-sm text-ink-2">{running ? 'Waiting for the first frame…' : 'Start the camera to run the model on the feed.'}</p>
            )}
          </Card>

          <Card>
            <CardTitle>Which way do you face?</CardTitle>
            <p className="mb-3 text-xs text-ink-2">
              Where your nose points in the picture above. The model needs this to tell leaning forward from leaning back; a wrong choice flips
              them. Auto only works when your feet are in view.
            </p>
            <Segmented<Facing>
              label="Which way you face in the picture"
              value={facing || 'auto'}
              onChange={changeFacing}
              options={[{ value: 'left', label: 'Left' }, { value: 'right', label: 'Right' }, { value: 'auto', label: 'Auto' }]}
            />
            {!facing && <p className="mt-2 text-xs text-ink-2">Not chosen yet, so the model is guessing (Auto). Pick Left or Right.</p>}
          </Card>

          <DataConsent onChange={(allowed) => { if (!allowed) { sendRef.current = false; setSend(false) } }} />

          <Card>
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 className="text-base font-semibold text-ink">Send readings to the dashboard</h2>
                <p className="mt-1 text-xs text-ink-2">
                  This computer acts as the phone, so Live, alerts and analytics run off this feed. Turning it on for the first time replaces any
                  phone that is paired now.
                </p>
              </div>
              <Toggle checked={send} onChange={(v) => !sendBusy && toggleSend(v)} label="Send readings to the dashboard" />
            </div>
            {sendError && (
              <div className="mt-3">
                <Banner tone="error">{sendError}</Banner>
              </div>
            )}
            {send && (
              <div className="mt-3 flex items-center gap-2 text-sm text-ink-2">
                {!running ? (
                  'Start the camera to begin sending.'
                ) : serverState ? (
                  <>
                    Dashboard state: <StatePill state={serverState} />
                    <span className="sr-only">{STATE_META[serverState].blurb}</span>
                  </>
                ) : (
                  'Sending…'
                )}
              </div>
            )}
          </Card>
        </div>
      </div>
    </div>
  )
}
