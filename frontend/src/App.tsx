import { Suspense, lazy } from 'react'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import './styles/aurora.css'
import './styles/glass.css'
import brandIcon from './assets/brand/meta-screener-icon.svg'
import { Sidebar } from './components/layout/Sidebar'
import { PageContainer } from './components/layout/PageContainer'

const Dashboard = lazy(() =>
  import('./pages/Dashboard').then((m) => ({ default: m.Dashboard })),
)
const Screening = lazy(() =>
  import('./pages/Screening').then((m) => ({ default: m.Screening })),
)
const Evaluation = lazy(() =>
  import('./pages/Evaluation').then((m) => ({ default: m.Evaluation })),
)
const Extraction = lazy(() =>
  import('./pages/Extraction').then((m) => ({ default: m.Extraction })),
)
const Quality = lazy(() =>
  import('./pages/Quality').then((m) => ({ default: m.Quality })),
)
const Settings = lazy(() =>
  import('./pages/Settings').then((m) => ({ default: m.Settings })),
)

const queryClient = new QueryClient()

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <div className="min-h-screen text-white flex">
          <div className="aurora-background">
            <div className="aurora-orb" />
            <div className="aurora-orb" />
            <div className="aurora-orb" />
            <div className="aurora-orb" />
            <div className="aurora-orb" />
            <div className="aurora-orb" />
          </div>
          <div className="relative z-10 flex w-full">
            <Sidebar />
            <PageContainer>
              <Suspense
                fallback={
                  <div className="min-h-[40vh] flex items-center justify-center">
                    <div className="glass-subtle rounded-2xl px-5 py-4 border border-white/10 flex items-center gap-3">
                      <img
                        src={brandIcon}
                        alt=""
                        aria-hidden="true"
                        className="w-8 h-8 object-contain animate-pulse"
                      />
                      <div>
                        <p className="text-white/80 text-sm font-medium">Meta Screener</p>
                        <p className="text-white/45 text-xs">Loading workspace...</p>
                      </div>
                    </div>
                  </div>
                }
              >
                <Routes>
                  <Route path="/" element={<Dashboard />} />
                  <Route path="/screening" element={<Screening />} />
                  <Route path="/evaluation" element={<Evaluation />} />
                  <Route path="/extraction" element={<Extraction />} />
                  <Route path="/quality" element={<Quality />} />
                  <Route path="/settings" element={<Settings />} />
                </Routes>
              </Suspense>
            </PageContainer>
          </div>
        </div>
      </BrowserRouter>
    </QueryClientProvider>
  )
}

export default App
