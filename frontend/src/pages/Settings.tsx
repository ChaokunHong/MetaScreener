import { Header } from '../components/layout/Header'
import { GlassCard } from '../components/glass/GlassCard'

export function Settings() {
  return (
    <>
      <Header title="Settings" description="Configure models, API keys, and project preferences" />
      <GlassCard>
        <p className="text-white/70">Manage your MetaScreener configuration and API credentials.</p>
      </GlassCard>
    </>
  )
}
