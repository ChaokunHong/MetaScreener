<template>
  <div>
    <h1 class="page-title" style="margin-bottom: 0.25rem;">LLM Configuration</h1>
    <p class="text-muted" style="margin-bottom: 1.5rem;">Configure API keys, verify connectivity, and select models for screening</p>

    <!-- API Keys -->
    <div class="glass-card">
      <div class="section-title">
        <i class="fas fa-key"></i> API Keys
        <button class="info-btn" @click="activeModal = 'apikeys'" title="About API Keys">
          <i class="fas fa-circle-info"></i>
        </button>
      </div>
      <div v-if="saveSuccess" class="alert alert-success">
        <i class="fas fa-check-circle"></i> {{ saveSuccessMsg }}
      </div>
      <div v-if="saveError" class="alert alert-danger">{{ saveError }}</div>

      <div class="form-group">
        <label class="form-label">OpenRouter API Key</label>
        <div style="display: flex; gap: 0.5rem;">
          <input
            v-model="settings.api_keys.openrouter"
            :type="showOpenRouter ? 'text' : 'password'"
            class="form-control"
            placeholder="sk-or-..."
            style="flex: 1;"
          />
          <button class="btn btn-secondary btn-sm" @click="showOpenRouter = !showOpenRouter" style="white-space: nowrap;">
            <i :class="showOpenRouter ? 'fas fa-eye-slash' : 'fas fa-eye'"></i>
            {{ showOpenRouter ? 'Hide' : 'Show' }}
          </button>
          <button class="btn btn-secondary btn-sm" :disabled="testingOR" @click="testKey('openrouter')" style="white-space: nowrap;">
            <i v-if="testingOR" class="fas fa-spinner fa-spin"></i>
            <i v-else class="fas fa-plug"></i>
            {{ testingOR ? 'Verifying...' : 'Verify' }}
          </button>
        </div>
        <div v-if="orTestResult" class="test-result" :class="orTestOk ? 'test-ok' : 'test-fail'">
          <i :class="orTestOk ? 'fas fa-circle-check' : 'fas fa-circle-xmark'"></i>
          {{ orTestResult }}
        </div>
      </div>

      <div class="form-group">
        <label class="form-label">Together AI API Key</label>
        <div style="display: flex; gap: 0.5rem;">
          <input
            v-model="settings.api_keys.together"
            :type="showTogether ? 'text' : 'password'"
            class="form-control"
            placeholder="Optional — not currently used"
            style="flex: 1;"
          />
          <button class="btn btn-secondary btn-sm" @click="showTogether = !showTogether" style="white-space: nowrap;">
            <i :class="showTogether ? 'fas fa-eye-slash' : 'fas fa-eye'"></i>
            {{ showTogether ? 'Hide' : 'Show' }}
          </button>
        </div>
      </div>

      <div class="form-group">
        <label class="form-label">NCBI API Key <span style="font-weight: 400; color: var(--text-secondary);">(optional)</span></label>
        <div style="display: flex; gap: 0.5rem;">
          <input
            v-model="settings.api_keys.ncbi"
            :type="showNCBI ? 'text' : 'password'"
            class="form-control"
            placeholder="Optional — improves NCBI rate limit"
            style="flex: 1;"
          />
          <button class="btn btn-secondary btn-sm" @click="showNCBI = !showNCBI" style="white-space: nowrap;">
            <i :class="showNCBI ? 'fas fa-eye-slash' : 'fas fa-eye'"></i>
            {{ showNCBI ? 'Hide' : 'Show' }}
          </button>
        </div>
        <div style="font-size: 0.75rem; color: var(--text-secondary); margin-top: 4px;">
          <i class="fas fa-circle-info" style="font-size: 0.7rem;"></i>
          Without a key, NCBI limits requests to 3/second. With a key, the limit increases to 10/second — recommended for pilot searches.
        </div>
      </div>

    </div>

    <!-- Model Selection -->
    <div class="glass-card">
      <div class="section-title">
        <i class="fas fa-robot"></i> Model Selection
        <button class="info-btn" @click="activeModal = 'models'" title="About Models">
          <i class="fas fa-circle-info"></i>
        </button>
        <span v-if="enabledModels.length > 0" class="model-count-badge">{{ enabledModels.length }} selected</span>
      </div>

      <!-- Quick Setup — Presets -->
      <div v-if="presets.length > 0" style="margin-bottom: 1.5rem;">
        <div style="font-size: 0.82rem; font-weight: 600; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.04em; margin-bottom: 0.6rem;">
          <i class="fas fa-wand-magic-sparkles" style="font-size: 0.75rem; margin-right: 4px;"></i>
          Preset Combinations
          <button class="info-btn" @click="activeModal = 'presets'" title="About Presets" style="margin-left: 4px;">
            <i class="fas fa-circle-info"></i>
          </button>
        </div>
        <div class="preset-grid">
          <div
            v-for="p in presets"
            :key="p.preset_id"
            class="preset-card"
            :class="{ 'preset-active': isActivePreset(p) }"
            @click="applyPreset(p)"
          >
            <div class="preset-icon">
              <i :class="presetIcon(p.preset_id)"></i>
            </div>
            <div class="preset-name">{{ p.name }}</div>
            <div class="preset-desc">{{ p.description }}</div>
            <div class="preset-meta">
              <span class="preset-count-chip">{{ p.models.length }} models</span>
              <span v-if="isActivePreset(p)" class="preset-active-chip">Active</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Minimum validation warning -->
      <div v-if="enabledModels.length > 0 && enabledModels.length < 2" class="alert alert-danger" style="margin-bottom: 1rem;">
        <i class="fas fa-triangle-exclamation"></i> At least 2 models must be enabled for ensemble screening.
      </div>

      <!-- Model Grid -->
      <div v-if="loadingModels" class="text-muted" style="padding: 1rem 0;">Loading models...</div>
      <div v-else class="model-grid">
        <div
          v-for="m in models"
          :key="m.model_id"
          class="model-card"
          :class="{ 'model-card-disabled': !isModelEnabled(m.model_id) }"
          @click="toggleModel(m.model_id)"
        >
          <div class="model-card-header">
            <div v-if="hasIcon(m.model_id)" class="model-logo-wrap">
              <img :src="iconPath(m.model_id)" :alt="m.name" class="model-logo" />
            </div>
            <div v-else class="model-logo-fallback" :style="{ background: tierColor(m.tier) }">
              {{ m.name.charAt(0) }}
            </div>
            <div style="display: flex; align-items: center; gap: 6px;">
              <span class="tier-badge" :style="{ background: tierBg(m.tier), color: tierColor(m.tier) }">
                Tier {{ m.tier }}
              </span>
              <div class="model-toggle" :class="{ 'model-toggle-on': isModelEnabled(m.model_id) }">
                <div class="model-toggle-knob"></div>
              </div>
            </div>
          </div>
          <div class="model-name">{{ m.name }}</div>
          <div class="model-badges">
            <span v-if="m.thinking" class="thinking-badge">Thinking</span>
            <span class="cost-badge"><i class="fas fa-coins"></i> ${{ m.cost_per_1m_tokens?.toFixed(2) ?? '?' }}/1M</span>
          </div>
          <div class="model-description">{{ m.description }}</div>
          <div class="model-meta">
            <span><i class="fas fa-server"></i> {{ m.provider }}</span>
            <span v-if="m.version"><i class="fas fa-code-branch"></i> v{{ m.version }}</span>
            <span v-if="m.license"><i class="fas fa-scale-balanced"></i> {{ m.license }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Inference Config -->
    <div class="glass-card">
      <div class="section-title">
        <i class="fas fa-sliders-h"></i> Inference Configuration
        <button class="info-btn" @click="activeModal = 'inference'" title="About Inference">
          <i class="fas fa-circle-info"></i>
        </button>
      </div>
      <div class="inference-grid">
        <div class="inference-param">
          <div class="inference-icon"><i class="fas fa-temperature-low"></i></div>
          <div class="inference-detail">
            <div class="inference-label">Temperature</div>
            <div class="inference-value">0.0</div>
          </div>
          <div class="inference-lock"><i class="fas fa-lock"></i></div>
        </div>
        <div class="inference-param">
          <div class="inference-icon"><i class="fas fa-seedling"></i></div>
          <div class="inference-detail">
            <div class="inference-label">Random Seed</div>
            <div class="inference-value">42</div>
          </div>
          <div class="inference-lock"><i class="fas fa-lock"></i></div>
        </div>
        <div class="inference-param">
          <div class="inference-icon"><i class="fas fa-clock"></i></div>
          <div class="inference-detail">
            <div class="inference-label">Timeout</div>
            <div class="inference-value">120s</div>
          </div>
          <div class="inference-lock"><i class="fas fa-lock"></i></div>
        </div>
        <div class="inference-param">
          <div class="inference-icon"><i class="fas fa-rotate"></i></div>
          <div class="inference-detail">
            <div class="inference-label">Max Retries</div>
            <div class="inference-value">3</div>
          </div>
          <div class="inference-lock"><i class="fas fa-lock"></i></div>
        </div>
      </div>
      <div class="inference-footer">
        <i class="fas fa-certificate"></i>
        All parameters locked for TRIPOD-LLM reproducibility compliance.
      </div>
    </div>

    <!-- Action Buttons — at the very bottom after all settings -->
    <div style="display: flex; gap: 0.75rem; align-items: center; justify-content: center; margin-top: 0.5rem;">
      <button class="btn btn-primary" :disabled="saving" @click="doSave">
        <i v-if="saving" class="fas fa-spinner fa-spin"></i>
        <i v-else class="fas fa-save"></i>
        {{ saving ? 'Saving...' : 'Save & Continue' }}
      </button>
      <button class="btn btn-danger" @click="clearKeys" :disabled="clearing">
        <i v-if="clearing" class="fas fa-spinner fa-spin"></i>
        <i v-else class="fas fa-trash-can"></i>
        {{ clearing ? 'Clearing...' : 'Clear All Keys' }}
      </button>
    </div>

    <!-- Glass Modals -->
    <Teleport to="body">
      <Transition name="modal">
        <div v-if="activeModal" class="modal-overlay" @click.self="activeModal = null">
          <div class="modal-glass-panel">
            <!-- Decorative refraction line -->
            <div class="modal-refraction"></div>

            <!-- Close -->
            <button class="modal-close" @click="activeModal = null">
              <i class="fas fa-times"></i>
            </button>

            <!-- API Keys Info -->
            <template v-if="activeModal === 'apikeys'">
              <div class="modal-header-row">
                <div class="modal-icon-wrap modal-icon-purple"><i class="fas fa-key"></i></div>
                <h2 class="modal-title">API Keys</h2>
              </div>
              <div class="modal-body-scroll">
                <div class="modal-sub-glass">
                  <h3><i class="fas fa-question-circle"></i> What is this?</h3>
                  <p>MetaScreener uses open-source LLMs hosted on <strong>OpenRouter</strong> — a unified API gateway for 200+ models. You need an API key to access the models.</p>
                </div>
                <div class="modal-sub-glass">
                  <h3><i class="fas fa-shoe-prints"></i> How to get a key</h3>
                  <ol>
                    <li>Visit <a href="https://openrouter.ai" target="_blank" rel="noopener">openrouter.ai</a> and create a free account</li>
                    <li>Go to <a href="https://openrouter.ai/keys" target="_blank" rel="noopener">Keys</a> section and click <strong>Create Key</strong></li>
                    <li>Copy the key (starts with <code>sk-or-</code>) and paste it above</li>
                  </ol>
                </div>
                <div class="modal-sub-glass">
                  <h3><i class="fas fa-coins"></i> Cost</h3>
                  <p>OpenRouter offers <strong>free credits</strong> for new accounts. Screening 1000 papers with 4 models costs approximately <strong>$2–5 USD</strong> depending on abstract length.</p>
                </div>
                <div class="modal-sub-glass">
                  <h3><i class="fas fa-shield-halved"></i> Security</h3>
                  <p>Your API keys are stored <strong>locally</strong> on your machine at <code>~/.metascreener/config.yaml</code>. They are never sent to any server other than their respective providers.</p>
                </div>
                <div class="modal-sub-glass full-width">
                  <h3><i class="fas fa-database"></i> NCBI API Key (Optional)</h3>
                  <p>MetaScreener uses NCBI E-utilities for <strong>MeSH term validation</strong> and <strong>PubMed pilot search</strong>. These features work without a key, but with reduced rate limits (3 requests/second vs 10/second).</p>
                  <ol>
                    <li>Visit <a href="https://www.ncbi.nlm.nih.gov/account/" target="_blank" rel="noopener">ncbi.nlm.nih.gov/account</a> and sign in or create a free account</li>
                    <li>Go to <a href="https://www.ncbi.nlm.nih.gov/account/settings/" target="_blank" rel="noopener">Settings → API Key Management</a></li>
                    <li>Click <strong>Create an API Key</strong> and copy it</li>
                  </ol>
                  <p style="margin-top:0.5rem;font-size:0.82rem;opacity:0.8;">Without a key, MeSH validation and Pilot Search still work — they just run slower when validating many terms.</p>
                </div>
              </div>
            </template>

            <!-- Models Info -->
            <template v-if="activeModal === 'models'">
              <div class="modal-header-row">
                <div class="modal-icon-wrap modal-icon-cyan"><i class="fas fa-robot"></i></div>
                <h2 class="modal-title">Model Selection</h2>
              </div>
              <div class="modal-body-scroll">
                <div class="modal-sub-glass full-width">
                  <h3><i class="fas fa-layer-group"></i> Hierarchical Consensus Network</h3>
                  <p>MetaScreener uses <strong>multiple diverse open-source LLMs</strong> to form an ensemble. Each model independently screens every paper. Their outputs are aggregated through calibrated confidence scoring to produce reliable decisions.</p>
                </div>
                <div class="modal-sub-glass">
                  <h3><i class="fas fa-puzzle-piece"></i> Why multiple models?</h3>
                  <p>Model diversity reduces individual bias. When models with different architectures, training data, and parameter counts agree, the decision is far more reliable than any single model.</p>
                </div>
                <div class="modal-sub-glass">
                  <h3><i class="fas fa-sliders-h"></i> Tier System</h3>
                  <p><strong>Tier 1</strong> (Flagship): Largest, most capable models with best accuracy. <strong>Tier 2</strong> (Strong): Excellent balance of performance and cost. <strong>Tier 3</strong> (Lightweight): Fast and affordable, good for budget setups.</p>
                </div>
                <div class="modal-sub-glass">
                  <h3><i class="fas fa-brain"></i> Thinking Models</h3>
                  <p>Models marked as "Thinking" use internal chain-of-thought reasoning before answering. They tend to be more accurate on complex eligibility decisions but cost more tokens.</p>
                </div>
                <div class="modal-sub-glass">
                  <h3><i class="fas fa-lock-open"></i> All Open-Source</h3>
                  <p>Every model is open-weight (Apache-2.0, MIT, or Llama license). No proprietary models are used, ensuring full reproducibility and transparency for publication.</p>
                </div>
              </div>
            </template>

            <!-- Presets Info -->
            <template v-if="activeModal === 'presets'">
              <div class="modal-header-row">
                <div class="modal-icon-wrap modal-icon-purple"><i class="fas fa-wand-magic-sparkles"></i></div>
                <h2 class="modal-title">Preset Combinations</h2>
              </div>
              <div class="modal-body-scroll">
                <div class="modal-sub-glass full-width">
                  <h3><i class="fas fa-lightbulb"></i> What are presets?</h3>
                  <p>Presets are <strong>recommended model combinations</strong> curated for different use cases. Click a preset to instantly configure your model selection. You can always customise further by toggling individual models.</p>
                </div>
                <div class="modal-sub-glass">
                  <h3><i class="fas fa-balance-scale"></i> Balanced (Recommended)</h3>
                  <p>4 models from <strong>4 different vendors</strong> — DeepSeek, Qwen, Kimi, and Llama. This maximises diversity of training data and architecture, which is the most important factor for ensemble quality. Best for most systematic reviews.</p>
                </div>
                <div class="modal-sub-glass">
                  <h3><i class="fas fa-crosshairs"></i> Maximum Precision</h3>
                  <p>2 <strong>thinking models</strong> (Qwen3 235B, Kimi K2.5) + 2 large non-thinking (DeepSeek V3.2, Nous Hermes4 405B). Combines Chinese and Western training data for diverse perspectives. The thinking models provide deeper reasoning while the 405B Nous model adds massive parameter count. ~$0.009/paper.</p>
                </div>
                <div class="modal-sub-glass">
                  <h3><i class="fas fa-piggy-bank"></i> Budget Friendly</h3>
                  <p>Optimised for <strong>lowest cost</strong> while maintaining quality. Uses DeepSeek V3.2 (strong + cheap) with Llama Maverick, Mistral Small 4, and MiniMax M1. Ideal for large-scale screening with thousands of papers where API costs matter.</p>
                </div>
                <div class="modal-sub-glass">
                  <h3><i class="fas fa-expand"></i> Comprehensive (8 models)</h3>
                  <p>Maximum consensus strength with <strong>8 models (4 thinking + 4 fast)</strong>. More models = more robust consensus, but also more API calls per paper (~$0.019/paper). Use for critical reviews where accuracy is paramount and cost is not a concern.</p>
                </div>
                <div class="modal-sub-glass full-width">
                  <h3><i class="fas fa-user-gear"></i> Custom Selection</h3>
                  <p>You can also build your own combination by toggling individual models below the presets. Minimum <strong>2 models</strong> required for ensemble voting. We recommend at least <strong>3-4 models</strong> from different vendors for reliable consensus.</p>
                </div>
              </div>
            </template>

            <!-- Inference Info -->
            <template v-if="activeModal === 'inference'">
              <div class="modal-header-row">
                <div class="modal-icon-wrap modal-icon-green"><i class="fas fa-sliders-h"></i></div>
                <h2 class="modal-title">Inference Configuration</h2>
              </div>
              <div class="modal-body-scroll">
                <div class="modal-sub-glass">
                  <h3><i class="fas fa-temperature-low"></i> Temperature = 0.0</h3>
                  <p>Setting temperature to zero makes the model output <strong>deterministic</strong> — the same input always produces the same output. This is essential for reproducible screening.</p>
                </div>
                <div class="modal-sub-glass">
                  <h3><i class="fas fa-seedling"></i> Seed = 42</h3>
                  <p>A fixed random seed ensures that any stochastic operations (e.g., tie-breaking) are reproducible. The seed <code>42</code> is used across all MetaScreener operations.</p>
                </div>
                <div class="modal-sub-glass">
                  <h3><i class="fas fa-clock"></i> Timeout = 120s</h3>
                  <p>Each LLM call has a <strong>2-minute timeout</strong>. If a model doesn't respond in time, it's treated as an error and the remaining models continue. This prevents one slow model from blocking the entire pipeline.</p>
                </div>
                <div class="modal-sub-glass">
                  <h3><i class="fas fa-rotate"></i> Max Retries = 3</h3>
                  <p>Failed API calls are retried up to 3 times with exponential backoff. This handles transient network issues without manual intervention.</p>
                </div>
                <div class="modal-sub-glass">
                  <h3><i class="fas fa-certificate"></i> TRIPOD-LLM Compliance</h3>
                  <p>These parameters are <strong>locked by design</strong> and cannot be changed through the UI. This ensures every screening run meets the TRIPOD-LLM reporting standard for AI-assisted systematic reviews, as required for publication in journals like <em>Lancet Digital Health</em>.</p>
                </div>
              </div>
            </template>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { apiGet, apiPut, apiPost, apiDelete } from '@/api'

const router = useRouter()

interface ApiKeys {
  openrouter?: string
  together?: string
  ncbi?: string
}

interface Settings {
  api_keys: ApiKeys
  enabled_models?: string[]
}

interface ModelInfo {
  model_id: string
  name: string
  provider?: string
  version?: string
  license?: string
  tier?: number
  thinking?: boolean
  cost_per_1m_tokens?: number
  description?: string
}

interface PresetInfo {
  preset_id: string
  name: string
  description: string
  models: string[]
}

const settings = ref<Settings>({ api_keys: {} })
const saving = ref(false)
const saveSuccess = ref(false)
const saveSuccessMsg = ref('')
const saveError = ref('')
const showOpenRouter = ref(false)
const showTogether = ref(false)
const showNCBI = ref(false)
const clearing = ref(false)

const testingOR = ref(false)
const orTestResult = ref('')
const orTestOk = ref(false)

const models = ref<ModelInfo[]>([])
const loadingModels = ref(true)
const enabledModels = ref<string[]>([])
const presets = ref<PresetInfo[]>([])

const activeModal = ref<string | null>(null)

/* ── Icon mapping ──────────────────────────────────── */
const iconMap: Record<string, string> = {
  'deepseek-v3': '/model_icon/deepseek.png',
  'qwen3': '/model_icon/qwen2.png',
  'kimi-k2.5': '/model_icon/moonshot.png',
  'kimi-k2': '/model_icon/moonshot.png',
  'llama4-maverick': '/model_icon/llama.png',
  'glm5-turbo': '/model_icon/chatglm-color.png',
  'mimo-v2-pro': '/model_icon/xiaomimimo.png',
  'minimax-m2.7': '/model_icon/minimax-color.png',
  'nous-hermes4': '/model_icon/nousresearch.png',
  'nvidia-nemotron': '/model_icon/nvidia-color.png',
  'cogito-671b': '/model_icon/deepcogito-color.png',
  'ai21-jamba': '/model_icon/ai21-brand-color.png',
  'gemma3-27b': '/model_icon/gemma-color.png',
  'mistral-small4': '/model_icon/mistralai.png',
  'phi4': '/model_icon/copilot-color.png',
}

function hasIcon(modelId: string): boolean {
  return !!iconMap[modelId] && iconMap[modelId].length > 0
}

function iconPath(modelId: string): string {
  return iconMap[modelId] || ''
}

/* ── Tier colors ───────────────────────────────────── */
function tierColor(tier?: number): string {
  if (tier === 1) return '#059669'
  if (tier === 2) return '#2563eb'
  return '#64748b'
}

function tierBg(tier?: number): string {
  if (tier === 1) return 'rgba(5,150,105,0.1)'
  if (tier === 2) return 'rgba(37,99,235,0.1)'
  return 'rgba(100,116,139,0.1)'
}

function presetIcon(presetId: string): string {
  const icons: Record<string, string> = {
    balanced: 'fas fa-balance-scale',
    precision: 'fas fa-crosshairs',
    budget: 'fas fa-piggy-bank',
    comprehensive: 'fas fa-expand',
  }
  return icons[presetId] || 'fas fa-layer-group'
}

/* ── Model toggle ──────────────────────────────────── */
function isModelEnabled(modelId: string): boolean {
  return enabledModels.value.includes(modelId)
}

function toggleModel(modelId: string): void {
  const idx = enabledModels.value.indexOf(modelId)
  if (idx >= 0) {
    // Don't allow disabling if it would drop below 2
    if (enabledModels.value.length <= 2) return
    enabledModels.value.splice(idx, 1)
  } else {
    enabledModels.value.push(modelId)
  }
  saveEnabledModels()
}

async function saveEnabledModels(): Promise<void> {
  try {
    await apiPut('/settings', { enabled_models: enabledModels.value })
  } catch {
    // silently handle — will be saved with next full save
  }
}

/* ── Presets ────────────────────────────────────────── */
function applyPreset(preset: PresetInfo): void {
  enabledModels.value = [...preset.models]
  saveEnabledModels()
}

function isActivePreset(preset: PresetInfo): boolean {
  return preset.models.length === enabledModels.value.length &&
    preset.models.every(m => enabledModels.value.includes(m))
}

/* ── Lifecycle ─────────────────────────────────────── */
onMounted(async () => {
  try {
    const data = await apiGet<Settings>('/settings')
    settings.value = { api_keys: data.api_keys || {} }
    if (data.enabled_models && data.enabled_models.length > 0) {
      enabledModels.value = data.enabled_models
    }
  } catch { /* no settings yet */ }
  try {
    const [modelsData, presetsData] = await Promise.all([
      apiGet<ModelInfo[]>('/settings/models'),
      apiGet<PresetInfo[]>('/settings/presets'),
    ])
    models.value = modelsData
    presets.value = presetsData
    // If no models were previously selected, apply the first preset as default
    if (enabledModels.value.length === 0 && presetsData.length > 0) {
      enabledModels.value = [...presetsData[0].models]
    }
  } catch { /* no models/presets */ }
  loadingModels.value = false
})

/* ── Save & Continue ───────────────────────────────── */
async function doSave() {
  saving.value = true
  saveSuccess.value = false
  saveError.value = ''
  try {
    await apiPut('/settings', {
      api_keys: settings.value.api_keys,
      enabled_models: enabledModels.value,
    })
    if (settings.value.api_keys.openrouter) {
      saveSuccessMsg.value = 'Settings saved. Verifying API key...'
      saveSuccess.value = true
      testingOR.value = true
      try {
        const data = await apiPost<{ valid: boolean; message: string }>('/settings/test-key', {
          provider: 'openrouter',
          api_key: settings.value.api_keys.openrouter,
        })
        orTestOk.value = data.valid
        orTestResult.value = data.message
        if (data.valid) {
          saveSuccessMsg.value = 'Settings saved & key verified! Redirecting to Criteria...'
          setTimeout(() => { router.push('/criteria') }, 1500)
        } else {
          saveSuccessMsg.value = ''
          saveSuccess.value = false
          saveError.value = `Key verification failed: ${data.message}`
        }
      } catch (e: unknown) {
        orTestOk.value = false
        orTestResult.value = `Verification error: ${(e as Error).message}`
      } finally {
        testingOR.value = false
      }
    } else {
      saveSuccessMsg.value = 'Settings saved successfully'
      saveSuccess.value = true
      setTimeout(() => { saveSuccess.value = false }, 3000)
    }
  } catch (e: unknown) {
    saveError.value = `Save failed: ${(e as Error).message}`
  } finally {
    saving.value = false
  }
}

async function testKey(provider: string) {
  testingOR.value = true
  orTestResult.value = ''
  try {
    const data = await apiPost<{ valid: boolean; message: string }>('/settings/test-key', {
      provider,
      api_key: provider === 'openrouter' ? settings.value.api_keys.openrouter : settings.value.api_keys.together,
    })
    orTestOk.value = data.valid
    orTestResult.value = data.message
  } catch (e: unknown) {
    orTestOk.value = false
    orTestResult.value = `Test failed: ${(e as Error).message}`
  } finally {
    testingOR.value = false
  }
}

async function clearKeys() {
  clearing.value = true
  try {
    await apiDelete('/settings/keys')
    settings.value.api_keys = { openrouter: '', together: '', ncbi: '' }
    orTestResult.value = ''
    saveSuccess.value = false
    saveError.value = ''
  } catch (e: unknown) {
    saveError.value = `Clear failed: ${(e as Error).message}`
  } finally {
    clearing.value = false
  }
}
</script>

<style scoped>
.test-result {
  margin-top: 6px;
  font-size: 0.8rem;
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: 6px;
}
.test-ok { color: #0f766e; }
.test-fail { color: #b91c1c; }

/* ── Section title with info button ─────────────────── */
.section-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.model-count-badge {
  margin-left: auto;
  font-size: 0.72rem;
  font-weight: 600;
  color: #0e7490;
  background: rgba(224, 247, 250, 0.6);
  border: 1px solid rgba(178, 235, 242, 0.5);
  padding: 2px 10px;
  border-radius: 999px;
}

/* ── Preset Grid ───────────────────────────────────── */
.preset-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 0.75rem;
}

.preset-card {
  cursor: pointer;
  padding: 1rem 1rem 0.85rem;
  border-radius: 14px;
  background: linear-gradient(145deg, rgba(255,255,255,0.35) 0%, rgba(255,255,255,0.18) 100%);
  -webkit-backdrop-filter: blur(12px) saturate(130%);
  backdrop-filter: blur(12px) saturate(130%);
  border: 1.5px solid rgba(148, 163, 184, 0.2);
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.5), 0 2px 8px rgba(15,23,42,0.04);
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  position: relative;
}
.preset-card:hover {
  background: linear-gradient(145deg, rgba(255,255,255,0.5) 0%, rgba(255,255,255,0.3) 100%);
  border-color: rgba(129, 216, 208, 0.4);
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.7), 0 6px 18px rgba(15,23,42,0.07);
  transform: translateY(-2px);
}
.preset-active {
  border-color: rgba(129, 216, 208, 0.5) !important;
  background: linear-gradient(145deg, rgba(129,216,208,0.12) 0%, rgba(139,92,246,0.06) 100%) !important;
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.6), 0 4px 14px rgba(129,216,208,0.12),
              0 0 0 1px rgba(129, 216, 208, 0.2);
}

.preset-icon {
  width: 32px;
  height: 32px;
  border-radius: 10px;
  background: linear-gradient(135deg, rgba(129,216,208,0.15), rgba(139,92,246,0.1));
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.85rem;
  color: #64748b;
  margin-bottom: 0.5rem;
}
.preset-active .preset-icon {
  background: linear-gradient(135deg, rgba(129,216,208,0.25), rgba(139,92,246,0.18));
  color: #0d9488;
}

.preset-name {
  font-weight: 650;
  font-size: 0.85rem;
  color: var(--text-primary);
  letter-spacing: -0.01em;
}
.preset-desc {
  font-size: 0.73rem;
  opacity: 0.65;
  margin-top: 0.3rem;
  color: var(--text-secondary);
  line-height: 1.35;
}
.preset-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 0.5rem;
}
.preset-count-chip {
  font-size: 0.65rem;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 999px;
  background: rgba(100, 116, 139, 0.08);
  color: var(--text-secondary);
}
.preset-active-chip {
  font-size: 0.6rem;
  font-weight: 650;
  padding: 2px 8px;
  border-radius: 999px;
  background: rgba(129, 216, 208, 0.15);
  color: #0d9488;
  letter-spacing: 0.03em;
}

/* ── Model Grid — 3x3 Glass Cards ──────────────────── */
.model-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 14px;
}

.model-card {
  padding: 18px;
  border-radius: 16px;
  background: linear-gradient(145deg, var(--btn-frost-bg-strong) 0%, var(--btn-frost-bg-soft) 100%);
  border: 2px solid rgba(129, 216, 208, 0.45);
  -webkit-backdrop-filter: blur(14px) saturate(145%);
  backdrop-filter: blur(14px) saturate(145%);
  box-shadow: 0 6px 18px var(--btn-frost-shadow), inset 0 1px 0 rgba(255,255,255,0.75),
              0 0 0 1px rgba(129, 216, 208, 0.15);
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  cursor: pointer;
  user-select: none;
  position: relative;
  overflow: hidden;
}
/* Selected glow ring */
.model-card::before {
  content: '';
  position: absolute;
  inset: -1px;
  border-radius: 17px;
  background: linear-gradient(135deg, rgba(129,216,208,0.35), rgba(139,92,246,0.25));
  z-index: -1;
  opacity: 1;
  transition: opacity 0.3s ease;
}
.model-card:hover {
  transform: translateY(-3px);
  box-shadow: 0 10px 28px rgba(15,23,42,0.1), inset 0 1.5px 0 rgba(255,255,255,0.85),
              0 0 20px rgba(129, 216, 208, 0.15);
  border-color: rgba(129, 216, 208, 0.6);
}

.model-card-disabled {
  opacity: 0.45;
  border-color: rgba(148, 163, 184, 0.2);
  background: linear-gradient(145deg, rgba(255,255,255,0.15) 0%, rgba(255,255,255,0.08) 100%);
  filter: grayscale(0.5);
}
.model-card-disabled::before {
  opacity: 0;
}
.model-card-disabled:hover {
  opacity: 0.7;
  filter: grayscale(0.2);
  border-color: rgba(148, 163, 184, 0.35);
}

.model-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.model-logo-wrap {
  width: 36px;
  height: 36px;
  flex-shrink: 0;
}
.model-logo {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  object-fit: contain;
  background: rgba(255,255,255,0.6);
  padding: 4px;
  border: 1px solid rgba(255,255,255,0.7);
}

.model-logo-fallback {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 0.8rem;
  color: white;
  flex-shrink: 0;
}

.model-name {
  font-size: 0.95rem;
  font-weight: 650;
  color: var(--text-primary);
  letter-spacing: -0.01em;
  margin-bottom: 6px;
}

/* ── Tier badge ────────────────────────────────────── */
.tier-badge {
  font-size: 0.62rem;
  font-weight: 650;
  padding: 2px 8px;
  border-radius: 999px;
  letter-spacing: 0.02em;
}

/* ── Toggle switch ─────────────────────────────────── */
.model-toggle {
  width: 32px;
  height: 18px;
  border-radius: 999px;
  background: rgba(148, 163, 184, 0.35);
  position: relative;
  transition: background 0.2s ease;
  flex-shrink: 0;
}
.model-toggle-on {
  background: #81d8d0;
}
.model-toggle-knob {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: white;
  position: absolute;
  top: 2px;
  left: 2px;
  transition: transform 0.2s ease;
  box-shadow: 0 1px 3px rgba(0,0,0,0.15);
}
.model-toggle-on .model-toggle-knob {
  transform: translateX(14px);
}

/* ── Badges row ────────────────────────────────────── */
.model-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
}

.thinking-badge {
  font-size: 0.65rem;
  font-weight: 600;
  color: #7c3aed;
  background: rgba(124, 58, 237, 0.08);
  border: 1px solid rgba(124, 58, 237, 0.2);
  padding: 1px 8px;
  border-radius: 999px;
}

.cost-badge {
  font-size: 0.65rem;
  font-weight: 500;
  color: var(--text-secondary);
  display: inline-flex;
  align-items: center;
  gap: 3px;
}
.cost-badge i {
  font-size: 0.6rem;
  opacity: 0.6;
}

.model-description {
  font-size: 0.72rem;
  color: var(--text-secondary);
  line-height: 1.45;
  margin-bottom: 8px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.model-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.model-meta span {
  font-size: 0.65rem;
  color: var(--text-secondary);
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.model-meta i {
  font-size: 0.6rem;
  opacity: 0.7;
}

/* ── Inference Config Grid ───────────────────────────── */
.inference-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
  margin-top: 12px;
}

.inference-param {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  border-radius: 14px;
  background: linear-gradient(145deg, var(--btn-frost-bg-strong) 0%, var(--btn-frost-bg-soft) 100%);
  border: 1px solid var(--btn-frost-border);
  -webkit-backdrop-filter: blur(12px) saturate(140%);
  backdrop-filter: blur(12px) saturate(140%);
  box-shadow: 0 3px 10px var(--btn-frost-shadow), inset 0 1px 0 rgba(255,255,255,0.7);
}

.inference-icon {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.85rem;
  color: #0e7490;
  background: rgba(224, 247, 250, 0.5);
  border: 1px solid rgba(178, 235, 242, 0.4);
  flex-shrink: 0;
}

.inference-detail {
  flex: 1;
  min-width: 0;
}

.inference-label {
  font-size: 0.72rem;
  font-weight: 500;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.inference-value {
  font-size: 1.1rem;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.02em;
}

.inference-lock {
  font-size: 0.65rem;
  color: rgba(148, 163, 184, 0.6);
}

.inference-footer {
  margin-top: 14px;
  padding: 10px 14px;
  border-radius: 10px;
  background: rgba(248, 250, 252, 0.6);
  border: 1px solid rgba(226, 232, 240, 0.6);
  font-size: 0.78rem;
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  gap: 8px;
}
.inference-footer i {
  color: #0e7490;
  font-size: 0.75rem;
}

/* ═══════════ Glass Modal System ═══════════ */

/* Overlay */
.modal-overlay {
  position: fixed;
  inset: 0;
  z-index: 9000;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(15, 23, 42, 0.25);
  -webkit-backdrop-filter: blur(6px) saturate(120%);
  backdrop-filter: blur(6px) saturate(120%);
  padding: 24px;
}

/* Outer glass panel — wide, translucent */
.modal-glass-panel {
  position: relative;
  width: 100%;
  max-width: 820px;
  max-height: 82vh;
  display: flex;
  flex-direction: column;
  border-radius: 28px;
  background: linear-gradient(
    145deg,
    rgba(255,255,255,0.58) 0%,
    rgba(255,255,255,0.42) 40%,
    rgba(255,255,255,0.50) 100%
  );
  -webkit-backdrop-filter: blur(40px) saturate(200%) brightness(1.15);
  backdrop-filter: blur(40px) saturate(200%) brightness(1.15);
  border: 1px solid rgba(255,255,255,0.55);
  box-shadow:
    0 32px 80px rgba(15,23,42,0.18),
    0 12px 32px rgba(6,182,212,0.08),
    inset 0 1px 0 rgba(255,255,255,0.7),
    inset 0 -1px 0 rgba(255,255,255,0.2);
  overflow: hidden;
  padding: 36px 40px;
}

/* Top refraction highlight */
.modal-refraction {
  position: absolute;
  top: 0;
  left: 8%;
  right: 8%;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(255,255,255,0.95) 40%, rgba(255,255,255,0.95) 60%, transparent);
  pointer-events: none;
}

/* Close button */
.modal-close {
  position: absolute;
  top: 16px;
  right: 16px;
  width: 30px;
  height: 30px;
  border-radius: 50%;
  border: 1px solid rgba(0, 0, 0, 0.06);
  background: rgba(255, 255, 255, 0.85);
  color: rgba(51, 65, 85, 0.45);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.75rem;
  transition: transform 0.35s cubic-bezier(0.34, 1.56, 0.64, 1), color 0.2s, background 0.2s, box-shadow 0.2s;
  z-index: 10;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
  outline: none;
}
.modal-close:hover {
  color: rgba(51, 65, 85, 0.8);
  background: rgba(255, 255, 255, 1);
  transform: rotate(90deg);
  box-shadow: 0 3px 12px rgba(0, 0, 0, 0.08);
}
.modal-close:active {
  transform: rotate(90deg) scale(0.9);
}

/* Header row with icon */
.modal-header-row {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 24px;
}
.modal-icon-wrap {
  width: 44px;
  height: 44px;
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.1rem;
  border: 1px solid rgba(255,255,255,0.5);
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.5), 0 2px 6px rgba(0,0,0,0.04);
  flex-shrink: 0;
}
.modal-icon-purple { background: rgba(139,92,246,0.12); color: #8b5cf6; }
.modal-icon-cyan { background: rgba(6,182,212,0.12); color: #06b6d4; }
.modal-icon-green { background: rgba(16,185,129,0.12); color: #10b981; }

.modal-title {
  font-size: 1.25rem;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.02em;
}

/* Scrollable body — 2-column grid for sub-glass cards */
.modal-body-scroll {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 14px;
  overflow-y: auto;
  padding: 20px 14px 24px 2px;
}

/* Full-width card when it's the only one or needs emphasis */
.modal-sub-glass:first-child:nth-last-child(1),
.modal-sub-glass.full-width {
  grid-column: 1 / -1;
}

/* ── Sub-glass cards (inner glass) — bright ─────────── */
.modal-sub-glass {
  padding: 18px 20px;
  border-radius: 16px;
  background: #fff;
  border: 1px solid rgba(235, 238, 242, 0.9);
  box-shadow:
    0 2px 8px rgba(15,23,42,0.05);
}

.modal-sub-glass h3 {
  font-size: 0.88rem;
  font-weight: 650;
  color: var(--text-primary);
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  gap: 7px;
}
.modal-sub-glass h3 i {
  font-size: 0.78rem;
  color: #0ea5e9;
  width: 16px;
  text-align: center;
}
.modal-sub-glass p {
  font-size: 0.82rem;
  line-height: 1.6;
  color: rgba(51,65,85,0.88);
  margin: 0;
}
.modal-sub-glass ol {
  font-size: 0.82rem;
  line-height: 1.7;
  color: rgba(51,65,85,0.88);
  padding-left: 1.2rem;
  margin: 0;
}
.modal-sub-glass a {
  color: #0ea5e9;
  text-decoration: none;
  font-weight: 550;
  transition: color 0.15s;
}
.modal-sub-glass a:hover {
  color: #0284c7;
  text-decoration: underline;
}
.modal-sub-glass code {
  background: rgba(255,255,255,0.5);
  border: 1px solid rgba(255,255,255,0.6);
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 0.78rem;
}
.modal-sub-glass strong {
  color: var(--text-primary);
}
.modal-sub-glass em {
  color: #0e7490;
}

/* ── Modal transition ───────────────────────────────── */
.modal-enter-active { transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); }
.modal-leave-active { transition: all 0.2s ease; }
.modal-enter-from { opacity: 0; }
.modal-enter-from .modal-glass-panel { transform: scale(0.92) translateY(20px); opacity: 0; }
.modal-leave-to { opacity: 0; }
.modal-leave-to .modal-glass-panel { transform: scale(0.95); opacity: 0; }

@media (max-width: 900px) {
  .model-grid { grid-template-columns: repeat(2, 1fr); }
}

@media (max-width: 640px) {
  .model-grid { grid-template-columns: 1fr; }
  .preset-grid { grid-template-columns: 1fr; }
  .modal-glass-panel { padding: 24px 20px; max-height: 88vh; max-width: 100%; }
  .modal-body-scroll { grid-template-columns: 1fr; }
}
</style>
