import { useEffect, useRef } from 'react'
import type { CoachPack } from '../../types'
import { Button } from '../ui'

// A shareable image drawn locally on a canvas. It carries only a few of the person's own numbers and the
// app name: no account, device, dates, times or pain data. Fixed light colours so it looks the same wherever
// it is posted, independent of the viewer's dark mode.
const SIZE = 1080
const C = { page: '#f9f9f7', ink: '#0b0b0b', ink2: '#52514e', line: '#e1e0d9', accent: '#2a78d6' }

function draw(canvas: HTMLCanvasElement, pack: CoachPack) {
  const ctx = canvas.getContext('2d')
  if (!ctx) return
  const h = pack.habits
  const font = 'system-ui, -apple-system, "Segoe UI", sans-serif'
  ctx.fillStyle = C.page
  ctx.fillRect(0, 0, SIZE, SIZE)

  ctx.fillStyle = C.accent
  ctx.fillRect(80, 100, 64, 8)
  ctx.fillStyle = C.ink
  ctx.font = `600 44px ${font}`
  ctx.fillText('Sitwise', 80, 170)
  ctx.fillStyle = C.ink2
  ctx.font = `400 32px ${font}`
  ctx.fillText(`My last ${pack.window.days} days of sitting`, 80, 220)

  const consistency = h.strength.consistencyPct
  const big = consistency == null ? '–' : `${Math.round(consistency)}%`
  ctx.fillStyle = C.ink
  ctx.font = `700 220px ${font}`
  ctx.fillText(big, 80, 520)
  ctx.fillStyle = C.ink2
  ctx.font = `400 38px ${font}`
  ctx.fillText(`of days at my ${h.strength.targetPct}% good-posture goal`, 80, 580)

  const rows: [string, string][] = [
    ['Day streak', `${h.strength.forgivingStreak}`],
    ['Best day score', h.bests.bestDayScore == null ? '–' : `${Math.round(h.bests.bestDayScore)}`],
    ['Longest good stretch', `${h.bests.longestGoodStretchMin} min`],
  ]
  rows.forEach(([label, value], i) => {
    const y = 700 + i * 100
    ctx.strokeStyle = C.line
    ctx.lineWidth = 2
    ctx.beginPath()
    ctx.moveTo(80, y - 52)
    ctx.lineTo(SIZE - 80, y - 52)
    ctx.stroke()
    ctx.fillStyle = C.ink2
    ctx.font = `400 36px ${font}`
    ctx.fillText(label, 80, y)
    ctx.fillStyle = C.ink
    ctx.font = `600 44px ${font}`
    ctx.textAlign = 'right'
    ctx.fillText(value, SIZE - 80, y)
    ctx.textAlign = 'left'
  })

  ctx.fillStyle = C.ink2
  ctx.font = `400 28px ${font}`
  ctx.fillText('Posture coaching that learns how I sit.', 80, SIZE - 70)
}

export default function ShareCard({ pack }: { pack: CoachPack }) {
  const ref = useRef<HTMLCanvasElement>(null)
  useEffect(() => {
    if (ref.current) draw(ref.current, pack)
  }, [pack])

  function download() {
    ref.current?.toBlob((blob) => {
      if (!blob) return
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'sitwise-progress.png'
      a.click()
      URL.revokeObjectURL(url)
    }, 'image/png')
  }

  return (
    <div>
      <canvas ref={ref} width={SIZE} height={SIZE} className="w-full max-w-xs rounded-xl border border-line" role="img" aria-label="Share card showing your good-posture consistency, day streak, best day score and longest good stretch" />
      <div className="mt-3">
        <Button variant="secondary" onClick={download}>Download image</Button>
      </div>
      <p className="mt-2 text-xs text-ink-2">Made on this device. It shows only the numbers above: no name, dates or pain data.</p>
    </div>
  )
}
