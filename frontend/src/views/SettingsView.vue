<template>
  <div>
    <h1 class="page-title" style="margin-bottom: 0.25rem;">LLM Configuration</h1>
    <p class="text-muted" style="margin-bottom: 1.5rem;">Configure API keys, verify connectivity, and view available models</p>

    <!-- API Keys -->
    <div class="glass-card">
      <div class="section-title"><i class="fas fa-key"></i> API Keys</div>
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
            placeholder="..."
            style="flex: 1;"
          />
          <button class="btn btn-secondary btn-sm" @click="showTogether = !showTogether" style="white-space: nowrap;">
            <i :class="showTogether ? 'fas fa-eye-slash' : 'fas fa-eye'"></i>
            {{ showTogether ? 'Hide' : 'Show' }}
          </button>
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

    <!-- Available Models — 2x2 Glass Cards -->
    <div class="glass-card">
      <div class="section-title"><i class="fas fa-robot"></i> Available Models</div>
      <div v-if="loadingModels" class="text-muted" style="padding: 1rem 0;">Loading models...</div>
      <div v-else class="model-grid">
        <div
          v-for="m in models"
          :key="m.model_id"
          class="model-card"
        >
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
      <div class="section-title"><i class="fas fa-sliders-h"></i> Inference Configuration</div>
      <div style="display: flex; gap: 0.75rem; flex-wrap: wrap; margin-top: 0.5rem;">
        <span class="badge badge-unclear">temperature = 0.0</span>
        <span class="badge badge-unclear">seed = 42</span>
        <span class="badge badge-unclear">timeout = 120s</span>
        <span class="badge badge-unclear">max_retries = 3</span>
      </div>
      <p class="text-muted" style="margin-top: 1rem; font-size: 0.85rem;">
        All inference parameters are fixed for reproducibility (TRIPOD-LLM compliance).
        Temperature=0.0 ensures deterministic outputs.
      </p>
    </div>
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
const clearing = ref(false)

const testingOR = ref(false)
const orTestResult = ref('')
const orTestOk = ref(false)

const models = ref<ModelInfo[]>([])
const loadingModels = ref(true)

// Local model logos from /public/model_icon/
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

    // Auto-verify the OpenRouter key after saving
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
    settings.value.api_keys = { openrouter: '', together: '' }
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

/* ── Model Grid — 2x2 Glass Cards ───────────────────── */
.model-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
}

.model-card {
  padding: 20px;
  border-radius: 16px;
  background: linear-gradient(
    145deg,
    var(--btn-frost-bg-strong) 0%,
    var(--btn-frost-bg-soft) 100%
  );
  border: 1px solid var(--btn-frost-border);
  -webkit-backdrop-filter: blur(14px) saturate(145%);
  backdrop-filter: blur(14px) saturate(145%);
  box-shadow:
    0 6px 18px var(--btn-frost-shadow),
    inset 0 1px 0 rgba(255,255,255,0.75);
  transition: all 0.25s ease;
}

.model-card:hover {
  transform: translateY(-3px);
  box-shadow:
    0 10px 28px rgba(15, 23, 42, 0.1),
    inset 0 1.5px 0 rgba(255,255,255,0.85);
  border-color: rgba(129, 216, 208, 0.5);
}

.model-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
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

.model-name {
  font-size: 1.05rem;
  font-weight: 650;
  color: var(--text-primary);
  letter-spacing: -0.01em;
  margin-bottom: 2px;
}

.model-full-name {
  font-size: 0.75rem;
  color: var(--text-secondary);
  margin-bottom: 10px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.model-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.model-meta span {
  font-size: 0.7rem;
  color: var(--text-secondary);
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.model-meta i {
  font-size: 0.65rem;
  opacity: 0.7;
}

@media (max-width: 640px) {
  .model-grid {
    grid-template-columns: 1fr;
  }
}
</style>
