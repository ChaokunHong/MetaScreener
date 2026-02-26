import { Header } from '../components/layout/Header'
import { GlassCard } from '../components/glass/GlassCard'

export function Screening() {
  return (
    <>
      <Header title="Screening" description="Title/abstract and full-text screening with the Hierarchical Consensus Network" />
      <GlassCard>
        <p className="text-white/70">Upload your search results to begin AI-assisted screening.</p>
      </GlassCard>
    </>
  )
}
