import { Header } from '../components/layout/Header'
import { GlassCard } from '../components/glass/GlassCard'

export function Evaluation() {
  return (
    <>
      <Header title="Evaluation" description="Performance metrics, calibration, and threshold optimization" />
      <GlassCard>
        <p className="text-white/70">Evaluate screening performance against gold-standard labels.</p>
      </GlassCard>
    </>
  )
}
