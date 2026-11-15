// The seam between the camera feed and the posture model (laptop/browser path; the iPhone app has
// its own Swift `PostureModel`). The Camera page grabs a frame about once a second and hands it to
// `model.analyze`. Whatever comes back is shown on the page and, if enabled, posted to
// /posture/ingest exactly like the phone would.
//
// Two models, picked automatically when the camera starts:
//   * `pythonModel`: sends the frame to scripts/model_server.py on THIS computer (127.0.0.1), which
//     runs the real model (the teammate's MediaPipe pipeline, via scripts/posture_model.py) with the
//     facing direction and the user's goal posture. Used whenever that server is running.
//   * `stubModel`: fixed mock data from the API, used otherwise (and on the hosted site, where no
//     local server exists; the hosted API takes no images).
import { api } from './api'
import type { PostureFeatures, PostureLabel } from './types'

export interface ModelOutput {
  label: PostureLabel
  /** 0 = on the goal posture; ~1 = far off it. */
  deviation: number
  /** 0..1 */
  confidence: number
  /** torsoAngle convention: degrees from vertical, + = leaning forward (docs/api.md). */
  features: PostureFeatures
  /** True when this is not a real posture reading (mock data or a placeholder model). */
  stub?: boolean
  /** How long the model took, when it reports it. */
  inferenceMs?: number
  /** Which model measured it (stored with the reading), e.g. posture-pipeline/side-angle-rule@0.1.0. */
  source?: string
  /** A short reason when the model can't give a reading (shown on the page, never stored). */
  note?: string
}

/** What the model needs to know beyond the picture. */
export interface AnalyzeOptions {
  /** Where the person's nose points in the picture. `auto` lets the model guess from face and feet. */
  facing?: 'left' | 'right' | 'auto'
  /** The user's calibrated torso angle in degrees (null = not calibrated yet, so vertical). */
  goal?: number | null
}

export interface PostureModel {
  name: string
  /** One-time setup (find the server, download weights, warm up). Called when the camera starts. */
  load?(): Promise<void>
  /** `frame` is the current vertical camera view the page shows (RGBA, longest side at most FRAME_MAX_SIDE); `t` is epoch ms. */
  analyze(frame: ImageData, t: number, opts?: AnalyzeOptions): Promise<ModelOutput>
}

/** Frames are downscaled so their longest side is this many pixels before the model sees them. */
export const FRAME_MAX_SIDE = 640

/** Vite proxies this to scripts/model_server.py (web/vite.config.ts). */
const LOCAL_MODEL = `${import.meta.env.BASE_URL}local-model`

/** Ignores the frame and returns the server's fixed mock reading (/model/analyze). */
export const stubModel: PostureModel = {
  name: 'Stub (fixed mock data)',
  async analyze(_frame, t) {
    const r = await api<ModelOutput>('/model/analyze', { method: 'POST', body: { t } })
    return { label: r.label, deviation: r.deviation, confidence: r.confidence, features: r.features, stub: true }
  },
}

async function toJpeg(frame: ImageData): Promise<Blob> {
  const canvas = document.createElement('canvas')
  canvas.width = frame.width
  canvas.height = frame.height
  canvas.getContext('2d')?.putImageData(frame, 0, 0)
  return new Promise((resolve, reject) =>
    canvas.toBlob((b) => (b ? resolve(b) : reject(new Error('Could not encode the frame'))), 'image/jpeg', 0.85),
  )
}

/** The Python model on this computer. The frame goes to 127.0.0.1 only and is not stored. */
export const pythonModel: PostureModel = {
  name: 'Local Python model',
  async analyze(frame, _t, opts) {
    const query = new URLSearchParams({ facing: opts?.facing ?? 'auto' })
    if (opts?.goal != null) query.set('goal', String(opts.goal))
    let res: Response
    try {
      res = await fetch(`${LOCAL_MODEL}/analyze?${query}`, { method: 'POST', headers: { 'Content-Type': 'image/jpeg' }, body: await toJpeg(frame) })
    } catch {
      throw new Error("Can't reach the local model server. Is `python scripts/model_server.py` still running?")
    }
    const data = (await res.json().catch(() => null)) as (ModelOutput & { error?: string }) | null
    if (!res.ok || !data) {
      throw new Error(data?.error ?? (res.status >= 500 ? 'The local model server stopped responding. Is `python scripts/model_server.py` still running?' : `Local model server error (${res.status})`))
    }
    return data
  },
}

/** Is scripts/model_server.py up? Returns its model's name, or null. */
async function probeLocalModel(): Promise<string | null> {
  try {
    const res = await fetch(`${LOCAL_MODEL}/health`)
    if (!res.ok) return null
    const h = (await res.json()) as { ready?: boolean; name?: string }
    return h.ready ? (h.name ?? 'unnamed') : null
  } catch {
    return null // not running, or (hosted site) the path served HTML instead of JSON
  }
}

let active: PostureModel = stubModel
let activeName = stubModel.name

/** What the Camera page uses: the local Python model when its server is running, else the stub. */
export const model: PostureModel = {
  get name() {
    return activeName
  },
  async load() {
    const local = await probeLocalModel()
    active = local ? pythonModel : stubModel
    activeName = local ? `${pythonModel.name}: ${local}` : stubModel.name
    await active.load?.()
  },
  analyze: (frame, t, opts) => active.analyze(frame, t, opts),
}
