import { useState } from 'react'
import { api, tzOffsetMin } from '../api'
import CoachingPanel from '../components/coach/CoachingPanel'
import HabitsPanel from '../components/coach/HabitsPanel'
import PatternsPanel from '../components/coach/PatternsPanel'
import ProfilePanel from '../components/coach/ProfilePanel'
import ToolsPanel from '../components/coach/ToolsPanel'
import { Banner, Segmented } from '../components/ui'
import { usePoll } from '../hooks'
import type { CoachInsights } from '../types'

type Tab = 'profile' | 'patterns' | 'coaching' | 'habits' | 'tools'
const TABS: { value: Tab; label: string }[] = [
  { value: 'profile', label: 'Profile' },
  { value: 'patterns', label: 'Patterns' },
  { value: 'coaching', label: 'Coaching' },
  { value: 'habits', label: 'Habits' },
  { value: 'tools', label: 'Tools' },
]

export default function Coach() {
  const [tab, setTab] = useState<Tab>('profile')
  // Fetched once (it is a 6-week analysis, not a live feed); refreshed after the person changes a setting.
  const ins = usePoll(() => api<CoachInsights>(`/coach/insights?tzOffsetMin=${tzOffsetMin()}`), 0)
  const data = ins.data

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-ink">Coach</h1>
        <p className="mt-1 text-sm text-ink-2">What your own sitting habits say about how you respond and what will help most.</p>
      </div>

      <div className="-mx-1 overflow-x-auto px-1 pb-1">
        <Segmented<Tab> dense label="Coach sections" value={tab} options={TABS} onChange={setTab} />
      </div>

      {ins.error && !data && <Banner tone="error">{ins.error.message}</Banner>}
      {!data && !ins.error && <p className="text-ink-2">Working out your patterns…</p>}

      {data && (
        <div className={ins.loading ? 'opacity-60 transition-opacity' : 'transition-opacity'}>
          {tab === 'profile' && <ProfilePanel insights={data} onToneApplied={ins.refresh} />}
          {tab === 'patterns' && <PatternsPanel pack={data.pack} library={data.library} />}
          {tab === 'coaching' && <CoachingPanel pack={data.pack} onChanged={ins.refresh} />}
          {tab === 'habits' && <HabitsPanel pack={data.pack} />}
          {tab === 'tools' && <ToolsPanel onChanged={ins.refresh} aiConfigured={data.ai.configured} />}
        </div>
      )}
    </div>
  )
}
