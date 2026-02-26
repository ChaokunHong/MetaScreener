import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import './styles/aurora.css'
import './styles/glass.css'
import { Sidebar } from './components/layout/Sidebar'
import { PageContainer } from './components/layout/PageContainer'
import { Dashboard } from './pages/Dashboard'
import { Screening } from './pages/Screening'
import { Evaluation } from './pages/Evaluation'
import { Extraction } from './pages/Extraction'
import { Quality } from './pages/Quality'
import { Settings } from './pages/Settings'

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
              <Routes>
                <Route path="/" element={<Dashboard />} />
                <Route path="/screening" element={<Screening />} />
                <Route path="/evaluation" element={<Evaluation />} />
                <Route path="/extraction" element={<Extraction />} />
                <Route path="/quality" element={<Quality />} />
                <Route path="/settings" element={<Settings />} />
              </Routes>
            </PageContainer>
          </div>
        </div>
      </BrowserRouter>
    </QueryClientProvider>
  )
}

export default App
