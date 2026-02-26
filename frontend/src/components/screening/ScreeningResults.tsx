import { GlassCard } from '../glass/GlassCard'
import { GlassButton } from '../glass/GlassButton'
import { useScreeningResults } from '../../api/queries'
import { useScreeningStore } from '../../stores/screening'
import { Download, CheckCircle, XCircle, HelpCircle } from 'lucide-react'

export function ScreeningResults() {
  const { sessionId } = useScreeningStore()
  const { data, isLoading } = useScreeningResults(sessionId)

  if (isLoading) {
    return (
      <GlassCard>
        <p className="text-white/50">Loading results...</p>
      </GlassCard>
    )
  }

  if (!data || data.results.length === 0) {
    return (
      <GlassCard>
        <p className="text-white/50">No results yet. Run screening to see results here.</p>
      </GlassCard>
    )
  }

  const decisionIcon = (decision: string) => {
    switch (decision.toUpperCase()) {
      case 'INCLUDE':
        return <CheckCircle size={16} className="text-green-400" />
      case 'EXCLUDE':
        return <XCircle size={16} className="text-red-400" />
      default:
        return <HelpCircle size={16} className="text-amber-400" />
    }
  }

  return (
    <GlassCard>
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-white">
          Results ({data.completed}/{data.total})
        </h3>
        <GlassButton variant="outline" size="sm">
          <span className="flex items-center gap-2">
            <Download size={14} /> Export
          </span>
        </GlassButton>
      </div>

      <div className="space-y-2">
        {data.results.map((r) => (
          <div
            key={r.record_id}
            className="flex items-center gap-3 p-3 rounded-xl bg-white/5"
          >
            {decisionIcon(r.decision)}
            <div className="flex-1 min-w-0">
              <p className="text-sm text-white truncate">{r.title}</p>
              <p className="text-xs text-white/40">
                Tier {r.tier} · Score {r.score.toFixed(2)} · Confidence {r.confidence.toFixed(2)}
              </p>
            </div>
            <span
              className={`text-xs px-2 py-0.5 rounded-full ${
                r.decision === 'INCLUDE'
                  ? 'bg-green-500/20 text-green-300'
                  : r.decision === 'EXCLUDE'
                    ? 'bg-red-500/20 text-red-300'
                    : 'bg-amber-500/20 text-amber-300'
              }`}
            >
              {r.decision}
            </span>
          </div>
        ))}
      </div>
    </GlassCard>
  )
}
