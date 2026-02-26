import { Header } from '../components/layout/Header'
import { GlassCard } from '../components/glass/GlassCard'

export function Quality() {
  return (
    <>
      <Header title="Quality Assessment" description="Risk of bias assessment using RoB 2, ROBINS-I, and QUADAS-2" />
      <GlassCard>
        <p className="text-white/70">Assess risk of bias for included studies with multi-LLM consensus.</p>
      </GlassCard>
    </>
  )
}
