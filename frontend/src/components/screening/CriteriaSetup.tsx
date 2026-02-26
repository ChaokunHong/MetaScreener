import { useState } from 'react'
import { GlassCard } from '../glass/GlassCard'
import { GlassButton } from '../glass/GlassButton'
import { apiPost } from '../../api/client'
import { useScreeningStore } from '../../stores/screening'

interface CriteriaSetupProps {
  onComplete: () => void
}

type TabMode = 'topic' | 'upload' | 'manual'

export function CriteriaSetup({ onComplete }: CriteriaSetupProps) {
  const [mode, setMode] = useState<TabMode>('topic')
  const [topic, setTopic] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const { sessionId } = useScreeningStore()

  const handleSubmit = async () => {
    if (!sessionId) return
    setError(null)
    setSaving(true)

    try {
      await apiPost(`/screening/criteria/${sessionId}`, {
        mode,
        text: topic,
      })
      onComplete()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to set criteria')
    } finally {
      setSaving(false)
    }
  }

  return (
    <GlassCard>
      <h3 className="text-lg font-semibold text-white mb-4">Screening Criteria</h3>

      {/* Tab selector */}
      <div className="flex gap-2 mb-4">
        {([
          ['topic', 'Generate from Topic'],
          ['upload', 'Upload YAML'],
          ['manual', 'Manual Entry'],
        ] as const).map(([key, label]) => (
          <button
            key={key}
            onClick={() => setMode(key)}
            className={`px-3 py-1.5 rounded-lg text-sm transition-colors ${
              mode === key
                ? 'bg-purple-500/20 text-purple-300 border border-purple-500/30'
                : 'text-white/50 hover:text-white/70'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {mode === 'topic' && (
        <div>
          <label className="block text-sm text-white/70 mb-1.5">Research Topic</label>
          <textarea
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            placeholder="e.g., Effect of antimicrobial stewardship programs on AMR in ICU patients"
            className="glass-input w-full h-24 resize-none"
            rows={3}
          />
        </div>
      )}

      {mode === 'upload' && (
        <div>
          <label className="block text-sm text-white/70 mb-1.5">Upload YAML criteria file</label>
          <input type="file" accept=".yaml,.yml" className="text-white/50 text-sm" />
        </div>
      )}

      {mode === 'manual' && (
        <div>
          <label className="block text-sm text-white/70 mb-1.5">Criteria JSON</label>
          <textarea
            className="glass-input w-full h-32 resize-none font-mono text-sm"
            placeholder='{"framework": "pico", "elements": {...}}'
          />
        </div>
      )}

      {error && <p className="text-red-400 text-sm mt-2">{error}</p>}

      <div className="mt-4 flex justify-end">
        <GlassButton onClick={() => void handleSubmit()} disabled={saving || (!topic && mode === 'topic')}>
          {saving ? 'Setting up...' : 'Set Criteria'}
        </GlassButton>
      </div>
    </GlassCard>
  )
}
