import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import { useToken } from './hooks'
import Calibration from './pages/Calibration'
import Live from './pages/Live'
import Pair from './pages/Pair'
import Settings from './pages/Settings'

// Analytics pulls in the charting library, so it loads on demand and keeps the Live page light.
const Analytics = lazy(() => import('./pages/Analytics'))

export default function App() {
  const token = useToken()
  return (
    <Suspense fallback={<p className="p-6 text-ink-2">Loading…</p>}>
    <Routes>
      <Route element={<Layout signedIn={!!token} />}>
        <Route path="/pair" element={<Pair />} />
        {token ? (
          <>
            <Route index element={<Live />} />
            <Route path="/analytics" element={<Analytics />} />
            <Route path="/calibration" element={<Calibration />} />
            <Route path="/settings" element={<Settings />} />
          </>
        ) : null}
        <Route path="*" element={<Navigate to={token ? '/' : '/pair'} replace />} />
      </Route>
    </Routes>
    </Suspense>
  )
}
