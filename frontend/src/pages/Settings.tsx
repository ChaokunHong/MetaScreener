import { useState, useEffect } from 'react'
import { Header } from '../components/layout/Header.tsx'
import { GlassCard } from '../components/glass/GlassCard.tsx'
import { GlassButton } from '../components/glass/GlassButton.tsx'
import {
  useSettings,
  useModels,
  useUpdateSettings,
  useTestKey,
} from '../api/queries.ts'
import { Key, Cpu, Sliders, Check, X, Loader2 } from 'lucide-react'

export function Settings() {
  const { data: settings, isLoading } = useSettings()
  const { data: models } = useModels()
  const updateSettings = useUpdateSettings()
  const testKey = useTestKey()

  const [openrouterKey, setOpenrouterKey] = useState('')
  const [togetherKey, setTogetherKey] = useState('')
  const [saved, setSaved] = useState(false)

  // Initialize form values when settings load
  useEffect(() => {
    if (settings) {
      setOpenrouterKey(settings.api_keys.openrouter)
      setTogetherKey(settings.api_keys.together)
    }
  }, [settings])

  const handleSave = () => {
    updateSettings.mutate(
      {
        api_keys: { openrouter: openrouterKey, together: togetherKey },
      },
      {
        onSuccess: () => {
          setSaved(true)
          setTimeout(() => setSaved(false), 2000)
        },
      },
    )
  }

  const handleTestKey = (provider: string, key: string) => {
    testKey.mutate({ provider, api_key: key })
  }

  if (isLoading) {
    return (
      <>
        <Header
          title="Settings"
          description="Configure models, API keys, and preferences"
        />
        <div className="flex items-center gap-2 text-white/50">
          <Loader2 className="animate-spin" size={18} />
          Loading settings...
        </div>
      </>
    )
  }

  return (
    <>
      <Header
        title="Settings"
        description="Configure models, API keys, and preferences"
      />

      <div className="space-y-6">
        {/* API Keys Section */}
        <GlassCard>
          <div className="flex items-center gap-2 mb-4">
            <Key size={20} className="text-purple-400" />
            <h3 className="text-lg font-semibold text-white">API Keys</h3>
          </div>

          <div className="space-y-4">
            <div>
              <label className="block text-sm text-white/70 mb-1.5">
                OpenRouter API Key
              </label>
              <div className="flex gap-2">
                <input
                  type="password"
                  value={openrouterKey}
                  onChange={(e) => setOpenrouterKey(e.target.value)}
                  placeholder="sk-or-v1-..."
                  className="glass-input flex-1"
                />
                <GlassButton
                  variant="outline"
                  size="sm"
                  onClick={() =>
                    handleTestKey('openrouter', openrouterKey)
                  }
                  disabled={testKey.isPending}
                >
                  Test
                </GlassButton>
              </div>
              {testKey.data && (
                <p
                  className={`text-xs mt-1 flex items-center gap-1 ${testKey.data.valid ? 'text-green-400' : 'text-red-400'}`}
                >
                  {testKey.data.valid ? (
                    <Check size={12} />
                  ) : (
                    <X size={12} />
                  )}
                  {testKey.data.message}
                </p>
              )}
            </div>

            <div>
              <label className="block text-sm text-white/70 mb-1.5">
                Together AI API Key
              </label>
              <input
                type="password"
                value={togetherKey}
                onChange={(e) => setTogetherKey(e.target.value)}
                placeholder="tog-..."
                className="glass-input w-full"
              />
            </div>
          </div>
        </GlassCard>

        {/* Models Section */}
        <GlassCard>
          <div className="flex items-center gap-2 mb-4">
            <Cpu size={20} className="text-purple-400" />
            <h3 className="text-lg font-semibold text-white">Models</h3>
          </div>

          <div className="space-y-2">
            {models?.map((model) => (
              <div
                key={model.model_id}
                className="flex items-center justify-between p-3 rounded-xl bg-white/5"
              >
                <div>
                  <p className="text-sm font-medium text-white">
                    {model.name}
                  </p>
                  <p className="text-xs text-white/50">
                    {model.provider} &middot; {model.version} &middot;{' '}
                    {model.license}
                  </p>
                </div>
                <div
                  className={`text-xs ${model.enabled ? 'text-green-400' : 'text-white/30'}`}
                >
                  {model.enabled ? 'Active' : 'Disabled'}
                </div>
              </div>
            ))}
          </div>
        </GlassCard>

        {/* Inference Section */}
        <GlassCard>
          <div className="flex items-center gap-2 mb-4">
            <Sliders size={20} className="text-purple-400" />
            <h3 className="text-lg font-semibold text-white">Inference</h3>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-white/70 mb-1.5">
                Temperature
              </label>
              <input
                type="number"
                value={settings?.inference.temperature ?? 0}
                disabled
                className="glass-input w-full opacity-60"
              />
              <p className="text-xs text-white/40 mt-1">
                Locked at 0.0 for reproducibility
              </p>
            </div>
            <div>
              <label className="block text-sm text-white/70 mb-1.5">
                Seed
              </label>
              <input
                type="number"
                value={settings?.inference.seed ?? 42}
                className="glass-input w-full"
                readOnly
              />
            </div>
            <div>
              <label className="block text-sm text-white/70 mb-1.5">
                Timeout (seconds)
              </label>
              <input
                type="number"
                value={settings?.inference.timeout_s ?? 120}
                className="glass-input w-full"
                readOnly
              />
            </div>
            <div>
              <label className="block text-sm text-white/70 mb-1.5">
                Max Retries
              </label>
              <input
                type="number"
                value={settings?.inference.max_retries ?? 3}
                className="glass-input w-full"
                readOnly
              />
            </div>
          </div>
        </GlassCard>

        {/* Save Button */}
        <div className="flex justify-end">
          <GlassButton
            onClick={handleSave}
            disabled={updateSettings.isPending}
          >
            {saved ? (
              <span className="flex items-center gap-2">
                <Check size={16} /> Saved
              </span>
            ) : updateSettings.isPending ? (
              <span className="flex items-center gap-2">
                <Loader2 className="animate-spin" size={16} /> Saving...
              </span>
            ) : (
              'Save Settings'
            )}
          </GlassButton>
        </div>
      </div>
    </>
  )
}
