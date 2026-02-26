import { useState } from 'react'
import { GlassCard } from '../glass/GlassCard'
import { GlassButton } from '../glass/GlassButton'
import { apiPost } from '../../api/client'
import { useScreeningStore } from '../../stores/screening'
import { Play, Loader2 } from 'lucide-react'

interface ScreeningRunnerProps {
  onComplete: () => void
}

export function ScreeningRunner({ onComplete }: ScreeningRunnerProps) {
  const [running, setRunning] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const { sessionId, recordCount } = useScreeningStore()

  const handleRun = async () => {
    if (!sessionId) return
    setRunning(true)
    setMessage(null)

    try {
      const resp = await apiPost<{ status: string; message: string }>(
        `/screening/run/${sessionId}`,
        { session_id: sessionId, seed: 42 },
      )
      setMessage(resp.message)
      if (resp.status === 'completed') {
        onComplete()
      }
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'Screening failed')
    } finally {
      setRunning(false)
    }
  }

  return (
    <GlassCard>
      <h3 className="text-lg font-semibold text-white mb-4">Run Screening</h3>

      <div className="space-y-4">
        <div className="p-4 rounded-xl bg-white/5">
          <p className="text-white/70 text-sm">
            <span className="text-white font-medium">{recordCount}</span> records ready for screening
          </p>
          <p className="text-white/40 text-xs mt-1">
            Using 4 open-source LLMs with Hierarchical Consensus Network
          </p>
        </div>

        {message && (
          <div className="p-3 rounded-xl bg-amber-500/10 border border-amber-500/20">
            <p className="text-amber-300 text-sm">{message}</p>
          </div>
        )}

        <div className="flex justify-end">
          <GlassButton onClick={() => void handleRun()} disabled={running}>
            {running ? (
              <span className="flex items-center gap-2">
                <Loader2 className="animate-spin" size={16} /> Running...
              </span>
            ) : (
              <span className="flex items-center gap-2">
                <Play size={16} /> Start Screening
              </span>
            )}
          </GlassButton>
        </div>
      </div>
    </GlassCard>
  )
}
