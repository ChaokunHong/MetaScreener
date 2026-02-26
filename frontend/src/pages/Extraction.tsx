import { Header } from '../components/layout/Header'
import { GlassCard } from '../components/glass/GlassCard'

export function Extraction() {
  return (
    <>
      <Header title="Data Extraction" description="Structured data extraction from included studies" />
      <GlassCard>
        <p className="text-white/70">Define your extraction form and run multi-LLM parallel extraction.</p>
      </GlassCard>
    </>
  )
}
