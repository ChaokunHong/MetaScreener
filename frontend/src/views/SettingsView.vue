<template>
  <div>
    <h1 class="page-title" style="margin-bottom: 0.25rem;">LLM Configuration</h1>
    <p class="text-muted" style="margin-bottom: 1.5rem;">Configure API keys, verify connectivity, and view available models</p>

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

      <div style="display: flex; gap: 0.75rem; align-items: center;">
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
    </div>

    <!-- Available Models -->
    <div class="glass-card">
      <div class="section-title">
        <i class="fas fa-robot"></i> Available Models
        <button class="info-btn" @click="activeModal = 'models'" title="About Models">
          <i class="fas fa-circle-info"></i>
        </button>
      </div>
      <div v-if="loadingModels" class="text-muted" style="padding: 1rem 0;">Loading models...</div>
      <div v-else class="model-grid">
        <div v-for="m in models" :key="m.model_id" class="model-card">
          <div class="model-card-header">
            <img :src="getModelLogo(m.model_id)" :alt="m.name" class="model-logo" />
            <span class="badge badge-include">active</span>
          </div>
          <div class="model-name">{{ getShortName(m.model_id) }}</div>
          <div class="model-full-name">{{ m.name }}</div>
          <div class="model-meta">
            <span><i class="fas fa-server"></i> {{ m.provider }}</span>
            <span><i class="fas fa-code-branch"></i> v{{ m.version }}</span>
            <span><i class="fas fa-scale-balanced"></i> {{ m.license }}</span>
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

    <!-- ═══════════ Glass Modals ═══════════ -->
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
                <h2 class="modal-title">Available Models</h2>
              </div>
              <div class="modal-body-scroll">
                <div class="modal-sub-glass">
                  <h3><i class="fas fa-layer-group"></i> Hierarchical Consensus Network</h3>
                  <p>MetaScreener uses <strong>4 diverse open-source LLMs</strong> to form an ensemble. Each model independently screens every paper. Their outputs are aggregated through calibrated confidence scoring to produce reliable decisions.</p>
                </div>
                <div class="modal-sub-glass">
                  <h3><i class="fas fa-puzzle-piece"></i> Why 4 models?</h3>
                  <p>Model diversity reduces individual bias. When 4 models with different architectures, training data, and parameter counts agree, the decision is far more reliable than any single model.</p>
                </div>
                <div class="modal-sub-glass modal-model-card">
                  <img src="/model_icon/qwen2.png" class="modal-model-logo" alt="Qwen" />
                  <div class="modal-model-name">Qwen 3</div>
                  <div class="modal-model-params">235B MoE</div>
                  <p>Alibaba's largest MoE model. Excellent multilingual &amp; reasoning capability.</p>
                </div>
                <div class="modal-sub-glass modal-model-card">
                  <img src="/model_icon/deepseek.png" class="modal-model-logo" alt="DeepSeek" />
                  <div class="modal-model-name">DeepSeek V3.2</div>
                  <div class="modal-model-params">685B MoE</div>
                  <p>Strong in scientific text comprehension and structured output.</p>
                </div>
                <div class="modal-sub-glass modal-model-card">
                  <img src="/model_icon/llama.png" class="modal-model-logo" alt="Llama" />
                  <div class="modal-model-name">Llama 4 Scout</div>
                  <div class="modal-model-params">17B 16E MoE</div>
                  <p>Meta's efficient MoE. Fast inference with strong instruction following.</p>
                </div>
                <div class="modal-sub-glass modal-model-card">
                  <img src="/model_icon/mistralai.png" class="modal-model-logo" alt="Mistral" />
                  <div class="modal-model-name">Mistral Small 3.1</div>
                  <div class="modal-model-params">24B Dense</div>
                  <p>Compact but capable. Good balance of speed and accuracy.</p>
                </div>
                <div class="modal-sub-glass">
                  <h3><i class="fas fa-lock-open"></i> All Open-Source</h3>
                  <p>Every model is open-weight (Apache-2.0, MIT, or Llama license). No proprietary models are used, ensuring full reproducibility and transparency for publication.</p>
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
}

interface ModelInfo {
  model_id: string
  name: string
  provider?: string
  version?: string
  license?: string
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

const activeModal = ref<string | null>(null)

const modelLogos: Record<string, string> = {
  qwen3: '/model_icon/qwen2.png',
  deepseek: '/model_icon/deepseek.png',
  llama: '/model_icon/llama.png',
  mistral: '/model_icon/mistralai.png',
}

function getModelLogo(modelId: string): string {
  return modelLogos[modelId] || ''
}

function getShortName(modelId: string): string {
  const names: Record<string, string> = {
    qwen3: 'Qwen 3',
    deepseek: 'DeepSeek V3',
    llama: 'Llama 4 Scout',
    mistral: 'Mistral Small',
  }
  return names[modelId] || modelId
}

onMounted(async () => {
  try {
    const data = await apiGet<Settings>('/settings')
    settings.value = { api_keys: data.api_keys || {} }
  } catch { /* no settings yet */ }
  try {
    models.value = await apiGet<ModelInfo[]>('/settings/models')
  } catch { /* no models */ }
  loadingModels.value = false
})

async function doSave() {
  saving.value = true
  saveSuccess.value = false
  saveError.value = ''
  try {
    await apiPut('/settings', { api_keys: settings.value.api_keys })
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

/* info-btn styles are in main.css (global) */

/* ── Model Grid — 2x2 Glass Cards ───────────────────── */
.model-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
}

.model-card {
  padding: 20px;
  border-radius: 16px;
  background: linear-gradient(145deg, var(--btn-frost-bg-strong) 0%, var(--btn-frost-bg-soft) 100%);
  border: 1px solid var(--btn-frost-border);
  -webkit-backdrop-filter: blur(14px) saturate(145%);
  backdrop-filter: blur(14px) saturate(145%);
  box-shadow: 0 6px 18px var(--btn-frost-shadow), inset 0 1px 0 rgba(255,255,255,0.75);
  transition: all 0.25s ease;
}
.model-card:hover {
  transform: translateY(-3px);
  box-shadow: 0 10px 28px rgba(15,23,42,0.1), inset 0 1.5px 0 rgba(255,255,255,0.85);
  border-color: rgba(129, 216, 208, 0.5);
}
.model-card-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.model-logo { width: 36px; height: 36px; border-radius: 10px; object-fit: contain; background: rgba(255,255,255,0.6); padding: 4px; border: 1px solid rgba(255,255,255,0.7); }
.model-name { font-size: 1.05rem; font-weight: 650; color: var(--text-primary); letter-spacing: -0.01em; margin-bottom: 2px; }
.model-full-name { font-size: 0.75rem; color: var(--text-secondary); margin-bottom: 10px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.model-meta { display: flex; flex-wrap: wrap; gap: 8px; }
.model-meta span { font-size: 0.7rem; color: var(--text-secondary); display: inline-flex; align-items: center; gap: 4px; }
.model-meta i { font-size: 0.65rem; opacity: 0.7; }

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

/* Model cards in modal — individual 2x2 glass cards */
.modal-model-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  padding: 22px 16px 18px;
}
.modal-model-card .modal-model-logo {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  object-fit: contain;
  background: rgba(248, 250, 252, 0.9);
  border: 1px solid rgba(226, 232, 240, 0.7);
  padding: 6px;
  margin-bottom: 12px;
}
.modal-model-card .modal-model-name {
  font-size: 0.95rem;
  font-weight: 650;
  color: var(--text-primary);
  letter-spacing: -0.01em;
  margin-bottom: 2px;
}
.modal-model-card .modal-model-params {
  font-size: 0.7rem;
  font-weight: 600;
  color: #0e7490;
  background: rgba(224, 247, 250, 0.6);
  border: 1px solid rgba(178, 235, 242, 0.5);
  padding: 2px 10px;
  border-radius: 999px;
  margin-bottom: 10px;
}
.modal-model-card p {
  font-size: 0.78rem;
  line-height: 1.55;
  color: rgba(71, 85, 105, 0.85);
  margin: 0;
}

/* ── Modal transition ───────────────────────────────── */
.modal-enter-active { transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); }
.modal-leave-active { transition: all 0.2s ease; }
.modal-enter-from { opacity: 0; }
.modal-enter-from .modal-glass-panel { transform: scale(0.92) translateY(20px); opacity: 0; }
.modal-leave-to { opacity: 0; }
.modal-leave-to .modal-glass-panel { transform: scale(0.95); opacity: 0; }

@media (max-width: 640px) {
  .model-grid { grid-template-columns: 1fr; }
  .modal-glass-panel { padding: 24px 20px; max-height: 88vh; max-width: 100%; }
  .modal-body-scroll { grid-template-columns: 1fr; }
  .modal-model-list { grid-template-columns: 1fr; }
}
</style>
