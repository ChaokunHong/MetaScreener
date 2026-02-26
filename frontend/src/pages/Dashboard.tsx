import { Header } from '../components/layout/Header'
import { GlassCard } from '../components/glass/GlassCard'

export function Dashboard() {
  return (
    <>
      <Header title="Dashboard" description="Overview of your systematic review workflow" />
      <GlassCard>
        <p className="text-white/70">Welcome to MetaScreener. Select a step to begin.</p>
      </GlassCard>
    </>
  )
}
